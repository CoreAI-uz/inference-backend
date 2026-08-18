from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    model: str | None = None


class ConversationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=200)


class SelectVersion(BaseModel):
    """Persist a branch switch: make this message the selected one on the active path."""

    message_id: UUID


class ConversationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str | None
    updated_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    parent_id: UUID | None = None
    active_child_id: UUID | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    reasoning: str | None = None
    reasoning_ms: int | None = None
    model: str | None
    created_at: datetime


class ConversationDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    title: str | None
    model: str
    created_at: datetime
    updated_at: datetime
    # The active root; the client follows active_child_id down to build the visible path.
    active_child_id: UUID | None = None
    messages: list[MessageOut] = []
