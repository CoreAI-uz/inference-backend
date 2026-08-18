"""MVP-minimal safety: the moderation hook + token/context helpers.

The moderation hook is a no-op seam now (Phase 2 plugs a classifier in without
touching routing). ``trim_to_context`` keeps a conversation within a model's context
window (sliding window; keeps system messages).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.dependencies import Identity


@dataclass(frozen=True)
class ModerationResult:
    allowed: bool
    reason: str | None = None


async def moderate_input(messages: list[dict], identity: Identity) -> ModerationResult:
    """Phase-2 hook. MVP: allow everything. A real classifier drops in here and the
    chat path emits an SSE ``error {code: content_blocked}`` when allowed is False."""
    return ModerationResult(allowed=True)


def estimate_tokens(text: str) -> int:
    """Cheap fallback when upstream usage is absent (~4 chars/token)."""
    return max(1, len(text) // 4)


def _msg_tokens(m: dict) -> int:
    content = m.get("content") or ""
    return estimate_tokens(content) + 4  # per-message overhead


def trim_to_context(messages: list[dict], max_context: int, *, reserve: int = 1024) -> list[dict]:
    """Drop oldest non-system messages until the estimate fits ``max_context - reserve``.
    System messages are always kept."""
    budget = max(256, max_context - reserve)
    system = [m for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]

    used = sum(_msg_tokens(m) for m in system)
    kept: list[dict] = []
    # walk newest → oldest, keep while under budget
    for m in reversed(rest):
        t = _msg_tokens(m)
        if used + t > budget and kept:
            break
        used += t
        kept.append(m)
    kept.reverse()
    return system + kept
