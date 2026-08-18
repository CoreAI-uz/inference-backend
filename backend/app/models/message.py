from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin
from app.db.types import (
    FINISH_REASON_ENUM,
    MESSAGE_ROLE_ENUM,
    FinishReason,
    MessageRole,
    pg_enum,
)

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class Message(Base, CreatedAtMixin):
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
        # Sibling / children lookups when building the message tree.
        Index("ix_messages_parent_id", "parent_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Tree edges (message editing / branching). The first message of a branch has a
    # NULL parent (a "root"); deleting a node cascades to its whole subtree.
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )
    # Which child is currently selected on the active path (ChatGPT-exact per-branch
    # memory). NULL for a leaf. SET NULL if the selected child is deleted.
    active_child_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[MessageRole] = mapped_column(pg_enum(MessageRole, MESSAGE_ROLE_ENUM), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Chain-of-thought (assistant only); kept separate so it's shown collapsibly and
    # NEVER included in the context sent on later turns.
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Wall-clock reasoning time in ms (first reasoning token → </think>), for "Thought
    # for N seconds".
    reasoning_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    finish_reason: Mapped[FinishReason | None] = mapped_column(
        pg_enum(FinishReason, FINISH_REASON_ENUM), nullable=True
    )

    conversation: Mapped[Conversation] = relationship(
        back_populates="messages", foreign_keys="Message.conversation_id"
    )
