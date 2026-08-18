"""SSE framing + the named event taxonomy the browser consumes.

The upstream vLLM (mock or real) speaks raw OpenAI ``data:`` chunks; the backend
re-frames everything into these named events, so the frontend only ever sees this
vocabulary.
"""

from __future__ import annotations

import json
from enum import StrEnum


class StreamEvent(StrEnum):
    QUEUED = "queued"        # backpressure / preemption — never an error
    REASONING = "reasoning"  # {content} — chain-of-thought; shown collapsibly, not context
    DELTA = "delta"          # {content, role?} — first delta carries role="assistant"
    USAGE = "usage"          # {prompt_tokens, completion_tokens, total_tokens}  (M4)
    TITLE = "title"          # {conversation_id, title} — auto-generated on the first turn
    DONE = "done"            # {conversation_id?, message_id?, finish_reason, title?}
    ERROR = "error"          # {code, message, retry_after?} — terminal failure only


def sse(event: StreamEvent | str, data: dict) -> str:
    """Frame a named SSE event. ``ensure_ascii=False`` keeps UZ/RU glyphs intact."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def sse_comment(text: str) -> str:
    """A comment line — used for heartbeats (``: ping``)."""
    return f": {text}\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Disable proxy buffering so deltas flush immediately (nginx honors this;
    # Caddy uses flush_interval -1 at the proxy).
    "X-Accel-Buffering": "no",
}
