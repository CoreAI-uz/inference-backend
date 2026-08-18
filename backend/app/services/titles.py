"""Conversation auto-titling.

Two layers:
- ``derive_title`` — instant, deterministic fallback (a trimmed first message). Always
  used when a conversation is first created, so there is never a blank title.
- ``generate_title`` — a one-shot LLM "name this chat in a few words" call (ChatGPT /
  Claude style), run once on the first turn of a new conversation. Best-effort: bounded
  by a timeout and swallows every error, falling back to ``derive_title``.
"""

from __future__ import annotations

import asyncio

from app.core.config import ModelConfig
from app.core.logging import get_logger
from app.gateway.client import VLLMClient

log = get_logger(__name__)

DEFAULT_TITLE = "New chat"
_MAX = 48

# A reasoning model may wrap its answer after this marker; keep only what follows.
_THINK_CLOSE = "</think>"

_TITLE_SYSTEM = (
    "You write short, descriptive titles for chat conversations. Given the user's first "
    "message, reply with ONLY a title of 3 to 6 words in Title Case — no surrounding "
    "quotes, no markdown, no trailing punctuation, no preamble."
)


def derive_title(first_user_message: str) -> str:
    text = " ".join(first_user_message.split())
    if not text:
        return DEFAULT_TITLE
    if len(text) <= _MAX:
        return text
    return text[:_MAX].rstrip() + "…"


def clean_title(raw: str) -> str | None:
    """Normalise a model's raw title output into a tidy one-line title (or None)."""
    s = (raw or "").strip()
    if not s:
        return None
    if _THINK_CLOSE in s:  # strip any leaked chain-of-thought
        s = s.split(_THINK_CLOSE)[-1].strip()
    s = s.split("\n", 1)[0].strip()          # first line only
    if s.lower().startswith("title:"):        # drop a "Title:" label
        s = s[len("title:") :].strip()
    s = s.strip("\"'`“”*#").strip()           # surrounding quotes / markdown
    s = " ".join(s.split())                    # collapse whitespace
    s = s.rstrip(" .,;:!?—-")                   # trailing punctuation
    if not s:
        return None
    if len(s) > _MAX:
        s = s[:_MAX].rstrip() + "…"
    return s


async def generate_title(
    client: VLLMClient,
    cfg: ModelConfig,
    first_user_message: str,
    *,
    timeout_s: float = 8.0,
) -> str | None:
    """One-shot LLM title for a conversation's first message. Returns a cleaned title,
    or None on empty input / timeout / any upstream error (caller keeps the fallback)."""
    text = " ".join(first_user_message.split())[:600]
    if not text:
        return None

    messages = [
        {"role": "system", "content": _TITLE_SYSTEM},
        {"role": "user", "content": text},
    ]
    extra: dict = {"max_tokens": 24, "temperature": 0.3}
    if cfg.supports_thinking:
        # Never spend the budget thinking about a title.
        extra["chat_template_kwargs"] = {"enable_thinking": False}

    async def _run() -> str:
        parts: list[str] = []
        async for chunk in client.stream_chat(cfg, messages, extra=extra):
            if chunk.content:
                parts.append(chunk.content)
        return "".join(parts)

    try:
        raw = await asyncio.wait_for(_run(), timeout=timeout_s)
    except Exception as exc:  # best-effort: titling must never break a reply
        log.info("auto_title_failed", error=str(exc))
        return None
    return clean_title(raw)
