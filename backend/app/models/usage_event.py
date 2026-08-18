"""Usage ledger. Written from a single sink (``gateway.metering.record_usage``).

Exists now purely for rate limiting + future billing (brief §6). One row per
completed chat turn or OCR job. Owned by a registered user and/or an anon session
(at least one present). FKs are SET NULL so pruning messages/jobs never orphans the
metering history.
"""

from __future__ import annotations

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.db.types import USAGE_TYPE_ENUM, UsageType, pg_enum


class UsageEvent(Base, CreatedAtMixin):
    __tablename__ = "usage_events"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR session_id IS NOT NULL",
            name="owner_present",
        ),
        # Drive rate-limit windows: WHERE user_id/session_id = ? AND created_at > ?
        Index("ix_usage_events_user_id_created_at", "user_id", "created_at"),
        Index("ix_usage_events_session_id_created_at", "session_id", "created_at"),
        Index("ix_usage_events_api_key_id_created_at", "api_key_id", "created_at"),
        Index("ix_usage_events_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    type: Mapped[UsageType] = mapped_column(pg_enum(UsageType, USAGE_TYPE_ENUM), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(16), nullable=False, server_default="web")
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cached_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    reasoning_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    pages: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    api_key_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    data_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)

    message_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    ocr_job_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ocr_jobs.id", ondelete="SET NULL"), nullable=True
    )
