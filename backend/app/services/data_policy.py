"""Versioned legal acceptance and effective request data policy."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConsentEvent

LEGAL_ACCEPTANCE_SCOPE = "terms_privacy_acceptance"
LEGAL_POLICY_VERSION = "legal-2026-08-16"
FREE_DATA_POLICY = "free_review_v1"
USAGE_ONLY_DATA_POLICY = "usage_only_v1"


async def has_legal_acceptance(db: AsyncSession, user_id: uuid.UUID) -> bool:
    latest = (
        await db.execute(
            select(ConsentEvent)
            .where(
                ConsentEvent.user_id == user_id,
                ConsentEvent.scope == LEGAL_ACCEPTANCE_SCOPE,
            )
            .order_by(ConsentEvent.created_at.desc(), ConsentEvent.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return bool(
        latest
        and latest.action == "grant"
        and latest.policy_version == LEGAL_POLICY_VERSION
    )


async def record_legal_acceptance(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    locale: str,
    source: str,
    commit: bool = True,
) -> None:
    if await has_legal_acceptance(db, user_id):
        return
    db.add(
        ConsentEvent(
            user_id=user_id,
            scope=LEGAL_ACCEPTANCE_SCOPE,
            action="grant",
            policy_version=LEGAL_POLICY_VERSION,
            source=source,
            locale=locale,
        )
    )
    if commit:
        await db.commit()
