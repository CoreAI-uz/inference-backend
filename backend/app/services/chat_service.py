"""Chat stream orchestration (complete).

Flow: moderation hook → context trim → stream from vLLM (with a queued/retry loop for
pre-stream capacity failures) → re-frame deltas as SSE → capture usage → persist the
  turn (own transaction) → meter best-effort (separate transaction) → usage + done.

Degraded-path contract:
- Pre-stream capacity failure (connect refused / 503): emit ``queued`` and retry with
  backoff up to ``MAX_QUEUE_WAIT_S``, then a terminal ``error``. Never a fake error.
- Mid-stream drop (preemption): vLLM cannot resume — persist the partial with
  ``finish_reason="stopped"``; the user re-sends.
- Client abort: stop, persist the partial as ``stopped``.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator

import httpx
from sqlalchemy import update

from app.auth.dependencies import Identity
from app.core.config import ModelConfig, get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.db.types import UsageType
from app.gateway.client import VLLMClient
from app.gateway.errors import ErrorCode
from app.gateway.events import StreamEvent, sse
from app.gateway.metering import record_usage
from app.gateway.registry import ModelNotFoundError, get_registry
from app.gateway.safety import estimate_tokens, moderate_input, trim_to_context
from app.models.conversation import Conversation
from app.schemas.chat import ReasoningEffort
from app.services.conversations import NotOwnedError, persist_branch_turn
from app.services.titles import generate_title

log = get_logger(__name__)

_RETRYABLE = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.RemoteProtocolError,
    httpx.PoolTimeout,
)

# Legacy reasoning streams may contain chain-of-thought followed by this marker.
# Current vLLM reasoning parsers expose thinking as a separate ``reasoning`` delta,
# but the marker path remains as a compatibility fallback for unparsed workers.
_THINK_CLOSE = "</think>"


def _error_event(code: ErrorCode, message: str) -> str:
    return sse(StreamEvent.ERROR, {"code": code.value, "message": message})


def _queued_event(position: int) -> str:
    log.info("chat_queued", position=position)
    return sse(
        StreamEvent.QUEUED, {"message": "High demand — you're in the queue", "position": position}
    )


async def stream_chat_completion(
    *,
    request,
    http: httpx.AsyncClient,
    identity: Identity,
    cfg: ModelConfig,
    model_id: str,
    messages: list[dict],
    conversation_id: uuid.UUID | None,
    mode: str,
    attach_parent_id: uuid.UUID | None,
    new_user_content: str | None,
    reasoning_effort: ReasoningEffort,
) -> AsyncGenerator[str, None]:
    settings = get_settings()

    mod = await moderate_input(messages, identity)
    if not mod.allowed:
        yield _error_event(ErrorCode.CONTENT_BLOCKED, mod.reason or "content blocked")
        return

    outbound = trim_to_context(messages, cfg.max_context)

    # Chain-of-thought: only for models that support it. Parsed reasoning is shown
    # collapsibly and kept out of the persisted context. Raw marker-delimited output is
    # supported below for older workers.
    extra: dict | None = None
    expect_reasoning = False
    if cfg.supports_thinking:
        enabled = reasoning_effort != "none"
        extra = {
            "chat_template_kwargs": {
                "enable_thinking": enabled,
                "preserve_thinking": enabled,
            }
        }
        if enabled:
            extra["reasoning_effort"] = reasoning_effort
        expect_reasoning = enabled

    upstream_headers: dict[str, str] = {}

    client = VLLMClient(http)
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []
    in_reasoning = expect_reasoning  # legacy content before </think> is reasoning
    structured_reasoning_seen = False
    split_buf = ""  # holds a tail that might be a partial </think>
    answer_started = False  # trim leading whitespace until the answer begins
    usage: dict | None = None
    saw_finish = False
    finish_reason = "stop"
    first_delta = True
    client_gone = False

    deadline = time.monotonic() + settings.max_queue_wait_s
    req_start = time.monotonic()
    first_token_at: float | None = None
    reason_start_at: float | None = None  # first reasoning token
    reason_ms: int | None = None  # reasoning wall-clock (→ </think>)
    attempt = 0

    while True:
        stream_began = False
        try:
            async for chunk in client.stream_chat(
                cfg, outbound, extra=extra, headers=upstream_headers or None
            ):
                stream_began = True
                if await request.is_disconnected():
                    client_gone = True
                    finish_reason = "stopped"
                    break
                if chunk.reasoning:
                    structured_reasoning_seen = True
                    in_reasoning = False
                    if first_token_at is None:
                        first_token_at = round(time.monotonic() - req_start, 3)
                    if reason_start_at is None:
                        reason_start_at = time.monotonic()
                    reasoning_parts.append(chunk.reasoning)
                    yield sse(StreamEvent.REASONING, {"content": chunk.reasoning})
                if chunk.content:
                    if first_token_at is None:
                        first_token_at = round(time.monotonic() - req_start, 3)
                        if in_reasoning:
                            reason_start_at = time.monotonic()
                    piece = ""
                    if structured_reasoning_seen:
                        # A reasoning parser already separated the two channels, so
                        # content is the user-visible answer even though it contains no
                        # literal </think> boundary.
                        if reason_ms is None and reason_start_at is not None:
                            reason_ms = int((time.monotonic() - reason_start_at) * 1000)
                        piece = chunk.content
                    elif in_reasoning:
                        # Route content into the reasoning channel until </think>.
                        split_buf += chunk.content
                        cut = split_buf.find(_THINK_CLOSE)
                        if cut != -1:
                            head = split_buf[:cut]
                            if head:
                                reasoning_parts.append(head)
                                yield sse(StreamEvent.REASONING, {"content": head})
                            in_reasoning = False
                            if reason_start_at is not None:
                                reason_ms = int((time.monotonic() - reason_start_at) * 1000)
                            piece = split_buf[cut + len(_THINK_CLOSE) :]
                            split_buf = ""
                        else:
                            # keep a tail that might be a partial </think>; emit the rest
                            keep = len(_THINK_CLOSE) - 1
                            if len(split_buf) > keep:
                                emit, split_buf = split_buf[:-keep], split_buf[-keep:]
                                reasoning_parts.append(emit)
                                yield sse(StreamEvent.REASONING, {"content": emit})
                    else:
                        piece = chunk.content

                    if not answer_started:
                        piece = piece.lstrip()  # drop leading blank lines after </think>
                    if piece:
                        answer_started = True
                        answer_parts.append(piece)
                        data: dict = {"content": piece}
                        if first_delta:
                            data["role"] = "assistant"
                            first_delta = False
                        yield sse(StreamEvent.DELTA, data)
                if chunk.usage:
                    usage = chunk.usage
                if chunk.finish_reason:
                    saw_finish = True
                    finish_reason = chunk.finish_reason
            break  # clean end (or broke on client disconnect)
        except _RETRYABLE as exc:
            if stream_began:
                log.warning("chat_stream_dropped", error=str(exc))
                finish_reason = "stopped"  # preemption mid-stream; no resume
                break
            if time.monotonic() >= deadline:
                yield _error_event(
                    ErrorCode.UPSTREAM_UNAVAILABLE, "no capacity available right now, please retry"
                )
                return
            yield _queued_event(attempt)
            attempt += 1
            await asyncio.sleep(min(2.0, 0.5 * attempt))
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in (503, 429) and not stream_began:
                if time.monotonic() >= deadline:
                    yield _error_event(
                        ErrorCode.UPSTREAM_UNAVAILABLE,
                        "no capacity available right now, please retry",
                    )
                    return
                yield _queued_event(attempt)
                attempt += 1
                await asyncio.sleep(min(2.0, 0.5 * attempt))
                continue
            log.warning("chat_upstream_status", status=status)
            yield _error_event(ErrorCode.UPSTREAM_UNAVAILABLE, f"upstream returned {status}")
            return
        except httpx.HTTPError as exc:
            log.warning("chat_upstream_error", error=str(exc))
            yield _error_event(ErrorCode.UPSTREAM_UNAVAILABLE, "upstream unavailable")
            return

    # Stream ended before </think> (e.g. truncated mid-reasoning): flush the tail.
    if split_buf:
        reasoning_parts.append(split_buf)
        if not client_gone:
            yield sse(StreamEvent.REASONING, {"content": split_buf})
        split_buf = ""
    if reason_ms is None and reason_start_at is not None:
        reason_ms = int((time.monotonic() - reason_start_at) * 1000)

    # Truncated without a finish chunk → treat as stopped.
    if not saw_finish and (answer_parts or reasoning_parts) and not client_gone:
        finish_reason = "stopped"

    assistant_text = "".join(answer_parts)
    reasoning_text = "".join(reasoning_parts)
    prompt_tokens = (usage or {}).get("prompt_tokens")
    completion_tokens = (usage or {}).get("completion_tokens")
    if prompt_tokens is None:
        prompt_tokens = sum(estimate_tokens(m.get("content") or "") for m in outbound)
    if completion_tokens is None:
        completion_tokens = estimate_tokens(reasoning_text + assistant_text)
    total_tokens = prompt_tokens + completion_tokens
    prompt_details = (usage or {}).get("prompt_tokens_details") or {}
    completion_details = (usage or {}).get("completion_tokens_details") or {}
    cached_input_tokens = int(prompt_details.get("cached_tokens", 0) or 0)
    reasoning_tokens = int(completion_details.get("reasoning_tokens", 0) or 0)

    log.info(
        "chat_completed",
        model=model_id,
        anon=identity.is_anon,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
        finish_reason=finish_reason,
        ttft_s=first_token_at,
    )

    conv_id_out: str | None = None
    msg_id_out: str | None = None
    async with SessionLocal() as db:
        try:
            # Persist for both registered and anonymous (anon owned by session_id).
            conv, assistant = await persist_branch_turn(
                db,
                identity=identity,
                conversation_id=conversation_id,
                model=model_id,
                mode=mode,
                attach_parent_id=attach_parent_id,
                new_user_content=new_user_content,
                assistant_content=assistant_text,
                reasoning=reasoning_text or None,
                reasoning_ms=reason_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                finish_reason=finish_reason,
            )
            conv_id_out = str(conv.id)
            msg_id_out = str(assistant.id)
            await db.commit()
        except NotOwnedError:
            log.warning("persist_turn_not_owned", conversation_id=str(conversation_id))
            await db.rollback()
            if not client_gone:
                yield _error_event(ErrorCode.NOT_FOUND, "conversation no longer exists")
            return
        except Exception:  # noqa: BLE001 - stream is already open; emit a terminal SSE error
            log.exception("persist_turn_failed", conversation_id=str(conversation_id))
            await db.rollback()
            if not client_gone:
                yield _error_event(ErrorCode.INTERNAL_ERROR, "reply could not be saved")
            return

    # Meter in its own transaction. A ledger outage must not undo the durable chat.
    async with SessionLocal() as meter_db:
        try:
            await record_usage(
                meter_db,
                type=UsageType.CHAT,
                model=model_id,
                identity=identity,
                input_tokens=prompt_tokens,
                output_tokens=completion_tokens,
                cached_input_tokens=cached_input_tokens,
                reasoning_tokens=reasoning_tokens,
                message_id=assistant.id,
                commit=True,
            )
        except Exception:  # noqa: BLE001 - defense in depth around the best-effort sink
            log.exception("meter_chat_failed", message_id=msg_id_out)
            await meter_db.rollback()

    if client_gone:
        return

    # Auto-title the first turn of a new conversation (ChatGPT style). This applies to
    # both account-owned and anonymous session-owned conversations so a chat keeps the
    # same useful title when an anonymous session is later claimed during registration.
    # Best-effort: a failure/timeout just leaves the trimmed-first-message fallback.
    title_out: str | None = None
    should_title = (
        settings.auto_title
        and conversation_id is None
        and mode == "user"
        and conv_id_out is not None
        and bool((new_user_content or "").strip())
    )
    if should_title:
        title_cfg = cfg
        if settings.title_model_id:
            try:
                _, title_cfg = get_registry().get(settings.title_model_id)
            except ModelNotFoundError:
                title_cfg = cfg
        generated = await generate_title(
            client, title_cfg, new_user_content or "", timeout_s=settings.title_timeout_s
        )
        if generated:
            title_out = generated
            async with SessionLocal() as db:
                try:
                    await db.execute(
                        update(Conversation)
                        .where(Conversation.id == uuid.UUID(conv_id_out))
                        .values(title=generated)
                    )
                    await db.commit()
                    log.info("auto_title_set", conversation_id=conv_id_out, title=generated)
                except Exception:  # noqa: BLE001 — titling never breaks the reply
                    await db.rollback()

    yield sse(
        StreamEvent.USAGE,
        {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "cached_input_tokens": cached_input_tokens,
            "reasoning_tokens": reasoning_tokens,
        },
    )
    if title_out:
        yield sse(StreamEvent.TITLE, {"conversation_id": conv_id_out, "title": title_out})
    yield sse(
        StreamEvent.DONE,
        {
            "conversation_id": conv_id_out,
            "message_id": msg_id_out,
            "finish_reason": finish_reason,
            "title": title_out,
        },
    )
