"""OCR job row. **Dormant** in the chat-first MVP — the table ships now (with the
config seams) so the deferred OCR track needs no migration when it resumes.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin
from app.db.types import OCR_STATUS_ENUM, OcrStatus, pg_enum


class OcrJob(Base, CreatedAtMixin):
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        CheckConstraint(
            "user_id IS NOT NULL OR session_id IS NOT NULL",
            name="owner_present",
        ),
        Index("ix_ocr_jobs_user_id", "user_id"),
        Index("ix_ocr_jobs_session_id", "session_id"),
        Index("ix_ocr_jobs_status", "status"),
        Index("ix_ocr_jobs_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    # Owned by a registered user OR an anon session (at least one is set).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[OcrStatus] = mapped_column(
        pg_enum(OcrStatus, OCR_STATUS_ENUM), nullable=False, server_default=OcrStatus.QUEUED.value
    )
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
