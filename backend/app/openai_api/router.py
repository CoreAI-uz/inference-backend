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
from app.openai_api.schemas import ChatCompletionIn, ReasoningEffort
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
    if principal.unlimited:
        return {}
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
    request_body: dict[str, Any],
    completion_chars: int,
    upstream: dict[str, Any] | None,
) -> dict[str, int]:
    raw = upstream or {}
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    if prompt is None:
        prompt = estimate_tokens(json.dumps(request_body, ensure_ascii=False, default=str))
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
    if principal.no_retention:
        return
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
    body = payload.model_dump(
        exclude_none=True, exclude={"reasoning", "reasoning_effort", "max_completion_tokens"}
    )
    body["model"] = cfg.served_model_name
    body["messages"] = [message.upstream() for message in payload.messages]
    if payload.max_completion_tokens is not None:
        body["max_tokens"] = payload.max_completion_tokens
    body.update(cfg.reasoning_body(
        payload.resolved_reasoning_effort(cfg.default_reasoning_effort),
        thinking=bool(payload.reasoning and payload.reasoning.enabled),
    ))

    # Accurate streaming metering requires the terminal usage event. It is removed
    # from the public stream below when the caller did not request include_usage.
    if payload.stream:
        body["stream_options"] = {**body.get("stream_options", {}), "include_usage": True}
    return body


def _normalize_reasoning_fields(value: Any) -> Any:
    """Expose one stable reasoning field across compatible upstreams."""
    if isinstance(value, list):
        return [_normalize_reasoning_fields(item) for item in value]
    if not isinstance(value, dict):
        return value

    normalized = {key: _normalize_reasoning_fields(item) for key, item in value.items()}
    if "reasoning_content" in normalized:
        normalized.setdefault("reasoning", normalized["reasoning_content"])
        normalized.pop("reasoning_content", None)
    return normalized


def _exclude_reasoning(value: Any) -> Any:
    if isinstance(value, list):
        return [_exclude_reasoning(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _exclude_reasoning(item)
            for key, item in value.items()
            if key not in {"reasoning", "reasoning_content", "reasoning_details"}
        }
    return value


def _reasoning_metadata(cfg: ModelConfig) -> dict[str, Any]:
    if cfg.supports_thinking and cfg.reasoning_mode == "toggle":
        return {"supported": True, "mode": "toggle", "default_enabled": False}
    return {
        "supported": cfg.supports_thinking,
        "efforts": cfg.reasoning_efforts,
        "default_effort": cfg.default_reasoning_effort,
    }


def _tool_metadata(cfg: ModelConfig) -> dict[str, Any]:
    return {
        "supported": cfg.supports_tools,
        "tool_choice": ["none", "auto", "required"] if cfg.supports_tools else [],
        "parallel_tool_calls": cfg.supports_tools,
    }


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
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "coreai",
                "aliases": cfg.aliases,
                "capabilities": {
                    "reasoning": _reasoning_metadata(cfg),
                    "tools": _tool_metadata(cfg),
                },
            }
            for model_id, cfg in get_registry().list_enabled()
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

    effort: ReasoningEffort = payload.resolved_reasoning_effort(
        cfg.default_reasoning_effort
    )
    if cfg.supports_thinking and cfg.reasoning_mode == "toggle":
        if payload.reasoning_effort is not None or (payload.reasoning and payload.reasoning.effort is not None):
            raise OpenAIAPIError(
                400,
                "This model supports thinking on/off. Use reasoning.enabled; effort levels are not supported.",
                param="reasoning_effort" if payload.reasoning_effort is not None else "reasoning.effort",
                code="unsupported_value",
                headers=rate_headers,
            )
    elif effort not in (cfg.reasoning_efforts or ["none"]):
        raise OpenAIAPIError(
            400,
            f"Reasoning effort '{effort}' is not supported by model '{model_id}'.",
            param="reasoning_effort",
            code="unsupported_value",
            headers=rate_headers,
        )

    if payload.uses_tools() and not cfg.supports_tools:
        raise OpenAIAPIError(
            400,
            f"Tool calling is not supported by model '{model_id}'.",
            param="tools",
            code="unsupported_value",
            headers=rate_headers,
        )

    messages = [message.upstream() for message in payload.messages]
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
                request_id=request_id,
                started=started,
                request_body=retained_request,
                exclude_reasoning=bool(payload.reasoning and payload.reasoning.exclude),
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
    public_raw = _normalize_reasoning_fields(raw) if isinstance(raw, dict) else raw
    if payload.reasoning and payload.reasoning.exclude:
        public_raw = _exclude_reasoning(public_raw)
    normalized = _usage(
        retained_request,
        0,
        raw.get("usage") if isinstance(raw, dict) else None,
    )
    retained_response = (
        public_raw if isinstance(public_raw, dict) else {"body": content.decode(errors="replace")}
    )
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
        content=(
            json.dumps(public_raw, ensure_ascii=False, separators=(",", ":")).encode()
            if isinstance(public_raw, dict)
            else content
        ),
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
    request_id: str,
    started: float,
    request_body: dict[str, Any],
    exclude_reasoning: bool = False,
) -> AsyncGenerator[bytes, None]:
    usage_raw: dict[str, Any] | None = None
    completion_chars = 0
    completed = False
    event_lines: list[str] = []
    done_frame: bytes | None = None
    completion_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls: dict[int, dict[str, Any]] = {}
    finish_reason: str | None = None

    async def emit(lines: list[str]) -> AsyncGenerator[bytes, None]:
        nonlocal usage_raw, completion_chars, completed, done_frame, finish_reason
        data = _sse_data(lines)
        usage_only = False
        public_lines = lines
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
                event = _normalize_reasoning_fields(event)
                if isinstance(event.get("usage"), dict):
                    usage_raw = event["usage"]
                    usage_only = event.get("choices") == []
                for choice in event.get("choices") or []:
                    content = (choice.get("delta") or {}).get("content")
                    if isinstance(content, str):
                        completion_chars += len(content)
                        completion_parts.append(content)
                    reasoning = (choice.get("delta") or {}).get("reasoning")
                    if isinstance(reasoning, str):
                        completion_chars += len(reasoning)
                        reasoning_parts.append(reasoning)
                    for tool_delta in (choice.get("delta") or {}).get("tool_calls") or []:
                        if not isinstance(tool_delta, dict):
                            continue
                        index = int(tool_delta.get("index", 0))
                        accumulated = tool_calls.setdefault(
                            index,
                            {
                                "id": "",
                                "type": "function",
                                "function": {"name": "", "arguments": ""},
                            },
                        )
                        if isinstance(tool_delta.get("id"), str):
                            accumulated["id"] = tool_delta["id"]
                        if isinstance(tool_delta.get("type"), str):
                            accumulated["type"] = tool_delta["type"]
                        function = tool_delta.get("function") or {}
                        if isinstance(function.get("name"), str):
                            accumulated["function"]["name"] = function["name"]
                            completion_chars += len(function["name"])
                        if isinstance(function.get("arguments"), str):
                            accumulated["function"]["arguments"] += function["arguments"]
                            completion_chars += len(function["arguments"])
                    if choice.get("finish_reason") is not None:
                        finish_reason = str(choice["finish_reason"])
                if exclude_reasoning:
                    event = _exclude_reasoning(event)
                encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
                public_lines = [
                    f"data: {encoded}" if line.startswith("data:") else line for line in lines
                ]

        if not (usage_only and not include_usage):
            yield ("\n".join(public_lines) + "\n\n").encode()

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
        normalized = _usage(request_body, completion_chars, usage_raw)
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
                            **(
                                {"reasoning": "".join(reasoning_parts)}
                                if reasoning_parts
                                else {}
                            ),
                            **(
                                {"tool_calls": [tool_calls[index] for index in sorted(tool_calls)]}
                                if tool_calls
                                else {}
                            ),
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
