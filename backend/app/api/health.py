"""Health endpoints.

- ``/api/health`` liveness — no dependencies, always cheap.
- ``/api/health/inference`` — sends a tiny completion through every enabled model route.
- ``/api/health/ready`` — combines storage checks with active inference checks.

Listing LiteLLM's configured models is not a sufficient readiness check: LiteLLM can return its
catalogue while every raw worker is unreachable. The active probe deliberately spends one output
token per model so a green result proves that the complete gateway-to-worker path is usable.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.core.config import ModelConfig, get_settings
from app.db.session import SessionLocal
from app.gateway.registry import get_registry

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _probe_model(request: Request, mid: str, cfg: ModelConfig) -> tuple[str, str]:
    try:
        api_key = cfg.resolved_api_key()
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        body: dict[str, object] = {
            "model": cfg.served_model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1,
            "temperature": 0,
            "stream": False,
        }
        if cfg.supports_thinking:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        resp = await request.app.state.http.post(
            f"{cfg.endpoint.rstrip('/')}/chat/completions",
            headers=headers,
            json=body,
            timeout=httpx.Timeout(8.0, connect=3.0),
        )
        if resp.status_code != 200:
            return mid, f"http {resp.status_code}"
        payload = resp.json()
        if payload.get("object") != "chat.completion" or not payload.get("choices"):
            return mid, "invalid-response"
        return mid, "ok"
    except Exception as exc:  # noqa: BLE001
        return mid, f"error: {type(exc).__name__}"


async def _probe_inference(
    request: Request, *, force: bool
) -> tuple[dict[str, str], str, bool]:
    """Return active model status, caching only orchestrator readiness polls."""
    settings = get_settings()
    now = time.monotonic()
    cached = getattr(request.app.state, "inference_health_cache", None)
    if (
        not force
        and cached is not None
        and now - cached["recorded_at"] < settings.inference_health_cache_s
    ):
        return cached["models"], cached["checked_at"], True

    lock = getattr(request.app.state, "inference_health_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.inference_health_lock = lock

    async with lock:
        now = time.monotonic()
        cached = getattr(request.app.state, "inference_health_cache", None)
        if (
            not force
            and cached is not None
            and now - cached["recorded_at"] < settings.inference_health_cache_s
        ):
            return cached["models"], cached["checked_at"], True

        enabled = get_registry().list_enabled()
        probes = await asyncio.gather(*[_probe_model(request, mid, cfg) for mid, cfg in enabled])
        models = dict(probes)
        checked_at = datetime.now(UTC).isoformat()
        request.app.state.inference_health_cache = {
            "models": models,
            "checked_at": checked_at,
            "recorded_at": time.monotonic(),
        }
        return models, checked_at, False


def _inference_status(models: dict[str, str]) -> str:
    available = sum(value == "ok" for value in models.values())
    if available == 0:
        return "unavailable"
    if available < len(models):
        return "degraded"
    return "ready"


@router.get("/health/inference")
async def health_inference(request: Request) -> JSONResponse:
    models, checked_at, _cached = await _probe_inference(request, force=True)
    status = _inference_status(models)
    return JSONResponse(
        {"status": status, "models": models, "checked_at": checked_at, "cached": False},
        status_code=503 if status == "unavailable" else 200,
    )


@router.get("/health/ready")
async def health_ready(request: Request) -> JSONResponse:
    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["postgres"] = f"error: {exc}"

    try:
        await request.app.state.redis.ping()
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc}"

    try:
        minio = request.app.state.minio
        exists = await run_in_threadpool(minio.bucket_exists, settings.minio_bucket)
        checks["minio"] = "ok" if exists else "missing-bucket"
    except Exception as exc:  # noqa: BLE001
        checks["minio"] = f"error: {exc}"

    models, checked_at, cached = await _probe_inference(request, force=False)
    inference = _inference_status(models)
    checks["inference"] = inference

    core_storage_ready = checks["postgres"] == "ok" and checks["redis"] == "ok"
    minio_ready = checks["minio"] == "ok"
    if not core_storage_ready or inference == "unavailable":
        status = "unavailable"
        status_code = 503
    elif inference == "degraded" or not minio_ready:
        status = "degraded"
        status_code = 200
    else:
        status = "ready"
        status_code = 200
    return JSONResponse(
        {
            "status": status,
            "checks": checks,
            "models": models,
            "inference_checked_at": checked_at,
            "inference_cached": cached,
        },
        status_code=status_code,
    )
