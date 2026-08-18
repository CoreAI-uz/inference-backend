from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.db.types import MessageRole

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


def _message_order() -> list:
    """Order messages by time, then put a turn's user message before its assistant
    one. persist_turn() writes both rows in a single transaction, and Postgres now()
    returns the transaction-start time, so the pair shares an identical created_at;
    without this tiebreak their relative order is undefined and the assistant can
    render above its own prompt on reload. Evaluated lazily so Message stays a
    forward reference (avoids an import cycle)."""
    from app.models.message import Message

    # False (user) sorts before True (assistant) ascending.
    return [Message.created_at, Message.role == MessageRole.ASSISTANT]


class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"
    __table_args__ = (
        # Owned by a registered user OR an anon session (at least one set).
        CheckConstraint("user_id IS NOT NULL OR session_id IS NOT NULL", name="owner_present"),
        # Sidebar list (registered): WHERE user_id = ? ORDER BY updated_at DESC
        Index("ix_conversations_user_id_updated_at", "user_id", "updated_at"),
        # Anon lookup + sweep of unclaimed conversations.
        Index("ix_conversations_session_id_updated_at", "session_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Registered owner (null for anonymous, set on register via stitch_session).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    # Anonymous owner (the per-device session cookie value).
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # The currently-selected root message. The active path = follow active_child_id
    # from here down. NULL until the first message is persisted.
    active_child_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )

    # No delete-orphan: anon conversations have no parent User; user deletion cascades
    # at the DB level (ON DELETE CASCADE + passive_deletes).
    user: Mapped[User | None] = relationship(back_populates="conversations")
    messages: Mapped[list[Message]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=_message_order,
        # Disambiguate: active_child_id is a second FK between the tables.
        foreign_keys="Message.conversation_id",
    )
