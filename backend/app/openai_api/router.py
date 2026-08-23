"""Authenticated, metered OpenAI-compatible facade over the internal LiteLLM gateway."""

from __future__ import annotations

import asyncio
import json
import math
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response, StreamingResponse

from app.core.config import ModelConfig, get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.db.types import Bucket, Tier, UsageType
from app.gateway.metering import record_usage
from app.gateway.ratelimit import RateLimitResult, check_and_consume
from app.gateway.registry import ModelNotFoundError, get_registry
from app.gateway.safety import estimate_tokens, moderate_input
from app.models import ApiContentRecord
from app.openai_api.auth import APIPrincipal, require_api_key
from app.openai_api.errors import OpenAIAPIError
from app.openai_api.schemas import ChatCompletionIn
from app.services.data_policy import FREE_DATA_POLICY

router = APIRouter(prefix="/v1", tags=["OpenAI compatible"])
log = get_logger(__name__)

_UPSTREAM_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
    TimeoutError,
)


def _rate_headers(result: RateLimitResult) -> dict[str, str]:
    settings = get_settings()
    reset = result.retry_after
    if reset == 0 and result.remaining < 1 and settings.rl_user_chat > 0:
        reset = math.ceil((1 - max(0.0, result.remaining)) / (settings.rl_user_chat / 3600.0))
    return {
        "x-ratelimit-limit-requests": str(settings.rl_user_chat),
        "x-ratelimit-remaining-requests": str(max(0, int(result.remaining))),
        "x-ratelimit-reset-requests": f"{reset}s",
    }


async def _consume_limit(request: Request, principal: APIPrincipal) -> dict[str, str]:
    result = await check_and_consume(
        request.app.state.redis,
        Bucket.CHAT,
        Tier.REGISTERED,
        str(principal.user_id),
    )
    headers = _rate_headers(result)
    if not result.allowed:
        headers["Retry-After"] = str(result.retry_after)
        raise OpenAIAPIError(
            429,
            "Rate limit reached for this account. Please retry later.",
            type="rate_limit_error",
            code="rate_limit_exceeded",
            headers=headers,
        )
    return headers


def _service_unavailable(headers: dict[str, str]) -> OpenAIAPIError:
    return OpenAIAPIError(
        503,
        "The model is temporarily unavailable. Please retry shortly.",
        type="server_error",
        code="service_unavailable",
        headers={**headers, "Retry-After": "2"},
    )


def _usage(
    messages: list[dict[str, str]],
    completion_chars: int,
    upstream: dict[str, Any] | None,
) -> dict[str, int]:
    raw = upstream or {}
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    if prompt is None:
        prompt = sum(estimate_tokens(message["content"]) for message in messages)
    if completion is None:
        completion = max(0, completion_chars // 4)

    prompt_details = raw.get("prompt_tokens_details") or {}
    completion_details = raw.get("completion_tokens_details") or {}
    cached = prompt_details.get("cached_tokens", raw.get("cache_read_input_tokens", 0)) or 0
    reasoning = completion_details.get("reasoning_tokens", 0) or 0
    return {
        "prompt_tokens": int(prompt),
        "completion_tokens": int(completion),
        "total_tokens": int(raw.get("total_tokens") or (int(prompt) + int(completion))),
        "cached_input_tokens": int(cached),
        "reasoning_tokens": int(reasoning),
    }


async def _persist_api_request(
    *,
    principal: APIPrincipal,
    model_id: str,
    request_id: str,
    usage: dict[str, int],
    started: float,
    status_code: int,
    request_body: dict[str, Any],
    response_body: dict[str, Any],
) -> None:
    async with SessionLocal() as db:
        try:
            await record_usage(
                db,
                type=UsageType.CHAT,
                model=model_id,
                identity=principal.identity,
                input_tokens=usage["prompt_tokens"],
                output_tokens=usage["completion_tokens"],
                cached_input_tokens=usage["cached_input_tokens"],
                reasoning_tokens=usage["reasoning_tokens"],
                source="api",
                api_key_id=principal.api_key_id,
                request_id=request_id,
                latency_ms=int((time.monotonic() - started) * 1000),
                status_code=status_code,
                data_policy=FREE_DATA_POLICY,
                commit=False,
            )
            db.add(
                ApiContentRecord(
                    user_id=principal.user_id,
                    api_key_id=principal.api_key_id,
                    request_id=request_id,
                    model=model_id,
                    request_body=request_body,
                    response_body=response_body,
                    status_code=status_code,
                    data_policy=FREE_DATA_POLICY,
                    expires_at=datetime.now(UTC)
                    + timedelta(days=get_settings().api_content_retention_days),
                )
            )
            await db.commit()
        except Exception:  # noqa: BLE001 - completion delivery must not be lost
            await db.rollback()
            log.exception("api_request_persistence_failed", request_id=request_id)


def _upstream_body(payload: ChatCompletionIn, cfg: ModelConfig) -> dict[str, Any]:
    body = payload.model_dump(exclude_none=True)
    body["model"] = cfg.served_model_name
    if cfg.supports_thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}

    # Accurate streaming metering requires the terminal usage event. It is removed
    # from the public stream below when the caller did not request include_usage.
    if payload.stream:
        body["stream_options"] = {**body.get("stream_options", {}), "include_usage": True}
    return body


def _upstream_headers(cfg: ModelConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key := cfg.resolved_api_key():
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _public_headers(rate_headers: dict[str, str], upstream: httpx.Response) -> dict[str, str]:
    headers = dict(rate_headers)
    content_type = upstream.headers.get("content-type")
    if content_type:
        headers["Content-Type"] = content_type
    return headers


async def _send_upstream(
    request: Request,
    cfg: ModelConfig,
    body: dict[str, Any],
    *,
    stream: bool,
) -> httpx.Response:
    upstream_request = request.app.state.http.build_request(
        "POST",
        f"{cfg.endpoint.rstrip('/')}/chat/completions",
        headers=_upstream_headers(cfg),
        json=body,
    )
    async with asyncio.timeout(get_settings().max_queue_wait_s):
        return await request.app.state.http.send(upstream_request, stream=stream)


@router.get("/models")
async def list_models(_principal: APIPrincipal = Depends(require_api_key)) -> dict:
    # CoreAI owns the public catalog and may expose only a subset of LiteLLM routes.
    return {
        "object": "list",
        "data": [
            {"id": model_id, "object": "model", "created": 0, "owned_by": "coreai"}
            for model_id, _cfg in get_registry().list_enabled()
        ],
    }


@router.post("/chat/completions")
async def chat_completions(
    payload: ChatCompletionIn,
    request: Request,
    principal: APIPrincipal = Depends(require_api_key),
):
    started = time.monotonic()
    request_id = getattr(request.state, "request_id", uuid.uuid4().hex[:12])
    rate_headers = await _consume_limit(request, principal)

    try:
        model_id, cfg = get_registry().get(payload.model)
    except ModelNotFoundError:
        raise OpenAIAPIError(
            404,
            f"The model '{payload.model}' does not exist or is not available.",
            param="model",
            code="model_not_found",
            headers=rate_headers,
        ) from None

    messages = [message.model_dump() for message in payload.messages]
    retained_request = payload.model_dump(mode="json", exclude_none=True)
    moderation = await moderate_input(messages, principal.identity)
    if not moderation.allowed:
        raise OpenAIAPIError(
            400,
            moderation.reason or "The request was blocked by the safety policy.",
            param="messages",
            code="content_policy_violation",
            headers=rate_headers,
        )

    try:
        upstream = await _send_upstream(
            request,
            cfg,
            _upstream_body(payload, cfg),
            stream=payload.stream,
        )
    except _UPSTREAM_ERRORS:
        raise _service_unavailable(rate_headers) from None

    if upstream.status_code >= 400:
        try:
            content = await upstream.aread()
        finally:
            await upstream.aclose()
        return Response(
            content=content,
            status_code=upstream.status_code,
            headers=_public_headers(rate_headers, upstream),
        )

    if payload.stream:
        return StreamingResponse(
            _stream_response(
                request=request,
                upstream=upstream,
                model_id=model_id,
                principal=principal,
                include_usage=bool(payload.stream_options and payload.stream_options.include_usage),
                messages=messages,
                request_id=request_id,
                started=started,
                request_body=retained_request,
            ),
            status_code=upstream.status_code,
            media_type="text/event-stream",
            headers={
                **rate_headers,
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        content = await upstream.aread()
        raw = upstream.json()
    finally:
        await upstream.aclose()
    normalized = _usage(messages, 0, raw.get("usage") if isinstance(raw, dict) else None)
    retained_response = raw if isinstance(raw, dict) else {"body": content.decode(errors="replace")}
    await _persist_api_request(
        principal=principal,
        model_id=model_id,
        request_id=request_id,
        usage=normalized,
        started=started,
        status_code=upstream.status_code,
        request_body=retained_request,
        response_body=retained_response,
    )
    return Response(
        content=content,
        status_code=upstream.status_code,
        headers=_public_headers(rate_headers, upstream),
    )


def _sse_data(lines: list[str]) -> str | None:
    data = [line[5:].lstrip() for line in lines if line.startswith("data:")]
    return "\n".join(data) if data else None


async def _stream_response(
    *,
    request: Request,
    upstream: httpx.Response,
    model_id: str,
    principal: APIPrincipal,
    include_usage: bool,
    messages: list[dict[str, str]],
    request_id: str,
    started: float,
    request_body: dict[str, Any],
) -> AsyncGenerator[bytes, None]:
    usage_raw: dict[str, Any] | None = None
    completion_chars = 0
    completed = False
    event_lines: list[str] = []
    done_frame: bytes | None = None
    completion_parts: list[str] = []
    finish_reason: str | None = None

    async def emit(lines: list[str]) -> AsyncGenerator[bytes, None]:
        nonlocal usage_raw, completion_chars, completed, done_frame, finish_reason
        data = _sse_data(lines)
        usage_only = False
        if data == "[DONE]":
            completed = True
            # Official SDKs stop consuming as soon as they receive [DONE]. Hold the
            # terminal frame until the durable usage write below has completed, or
            # Starlette may cancel this generator (and its DB transaction) early.
            done_frame = ("\n".join(lines) + "\n\n").encode()
            return
        elif data:
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                event = None
            if isinstance(event, dict):
                if isinstance(event.get("usage"), dict):
                    usage_raw = event["usage"]
                    usage_only = event.get("choices") == []
                for choice in event.get("choices") or []:
                    content = (choice.get("delta") or {}).get("content")
                    if isinstance(content, str):
                        completion_chars += len(content)
                        completion_parts.append(content)
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])

        if not (usage_only and not include_usage):
            yield ("\n".join(lines) + "\n\n").encode()

    try:
        async for line in upstream.aiter_lines():
            if await request.is_disconnected():
                break
            if line:
                event_lines.append(line)
                continue
            async for frame in emit(event_lines):
                yield frame
            event_lines = []
        if event_lines:
            async for frame in emit(event_lines):
                yield frame
    except _UPSTREAM_ERRORS:
        completed = False
    finally:
        await upstream.aclose()
        normalized = _usage(messages, completion_chars, usage_raw)
        await _persist_api_request(
            principal=principal,
            model_id=model_id,
            request_id=request_id,
            usage=normalized,
            started=started,
            status_code=200 if completed else 499,
            request_body=request_body,
            response_body={
                "object": "chat.completion.stream",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "".join(completion_parts),
                        },
                        "finish_reason": finish_reason,
                    }
                ],
                "usage": normalized,
                "completed": completed,
            },
        )
    if completed and done_frame is not None:
        yield done_frame
