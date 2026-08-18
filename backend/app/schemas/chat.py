from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str


class ChatRequest(BaseModel):
    """Tree-aware chat request.

    Three shapes (server derives the mode):
    - New turn (legacy/compat): send ``messages`` (+ optional ``conversation_id``);
      the new user turn attaches under the conversation's active leaf.
    - Edit / explicit new turn: ``parent_id`` + ``user_content`` → a new user message
      is created under ``parent_id`` (a sibling when editing), then a reply.
    - Regenerate: ``parent_id`` (a user message) with no ``user_content`` → a new
      assistant sibling is generated under it.
    Context sent to the model is always assembled server-side from the tree lineage,
    not from ``messages``.
    """

    model: str | None = None
    messages: list[ChatMessage] | None = None
    conversation_id: str | None = None
    parent_id: str | None = None
    user_content: str | None = None
    # Request chain-of-thought (only honored by models with supports_thinking).
    thinking: bool = False
