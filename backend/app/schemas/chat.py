from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator

ReasoningEffort = Literal["none", "low", "medium", "xhigh"]


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
    reasoning_effort: ReasoningEffort | None = None
    # Compatibility with clients that shipped before effort levels were available.
    thinking: bool | None = None

    @model_validator(mode="after")
    def _one_reasoning_control(self):
        if self.reasoning_effort is not None and self.thinking is not None:
            raise ValueError("use either reasoning_effort or thinking, not both")
        return self

    def resolved_reasoning_effort(self, default: ReasoningEffort) -> ReasoningEffort:
        if self.reasoning_effort is not None:
            return self.reasoning_effort
        if self.thinking is not None:
            return default if self.thinking else "none"
        return default
