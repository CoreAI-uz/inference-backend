"""Metering — the single sink that writes ``usage_events``.

Shared by chat and (later) OCR so usage is written from exactly one place. Metering is
best-effort and uses a transaction separate from chat persistence: a ledger failure
must never roll back a durable reply. Redis token buckets are the hot-path limiter;
this table is the durable ledger that feeds billing later.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import Identity
from app.core.logging import get_logger
from app.db.types import UsageType
from app.models import UsageEvent

log = get_logger(__name__)


async def record_usage(
    db: AsyncSession,
    *,
    type: UsageType,
    model: str | None,
    identity: Identity,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_input_tokens: int = 0,
    reasoning_tokens: int = 0,
    pages: int = 0,
    source: str = "web",
    api_key_id: uuid.UUID | None = None,
    request_id: str | None = None,
    latency_ms: int | None = None,
    status_code: int | None = None,
    data_policy: str | None = None,
    message_id: uuid.UUID | None = None,
    ocr_job_id: uuid.UUID | None = None,
    commit: bool = True,
) -> bool:
    """Add a usage row, returning whether it reached the durable ledger.

    Callers must give this function a session dedicated to metering. ``commit=False``
    remains available for a future caller that owns the surrounding transaction.
    """
    try:
        db.add(
            UsageEvent(
                user_id=identity.user_id,
                session_id=identity.session_id,
                type=type,
                model=model,
                source=source,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=cached_input_tokens,
                reasoning_tokens=reasoning_tokens,
                pages=pages,
                api_key_id=api_key_id,
                request_id=request_id,
                latency_ms=latency_ms,
                status_code=status_code,
                data_policy=data_policy,
                message_id=message_id,
                ocr_job_id=ocr_job_id,
            )
        )
        if commit:
            await db.commit()
        return True
    except Exception:  # noqa: BLE001 - metering must never break the caller
        log.exception("record_usage_failed", usage_type=str(type))
        await db.rollback()
        return False
