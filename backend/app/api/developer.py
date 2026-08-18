"""Session-authenticated developer console endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth.dependencies import Identity, require_user
from app.db.types import UsageType
from app.models import UsageEvent
from app.services import api_keys as key_service

router = APIRouter(prefix="/api/developer", tags=["developer"])


class CreateApiKeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)

    @field_validator("name")
    @classmethod
    def _clean_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    prefix: str
    last_four: str
    created_at: datetime
    last_used_at: datetime | None
    expires_at: datetime | None


class CreatedApiKeyOut(ApiKeyOut):
    key: str


class UsageTotals(BaseModel):
    requests: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    reasoning_tokens: int


class UsageBySource(UsageTotals):
    source: str


class UsageByModel(UsageTotals):
    model: str


class DeveloperUsageOut(BaseModel):
    period_start: datetime
    lifetime: UsageTotals
    last_24_hours: UsageTotals
    by_source: list[UsageBySource]
    by_model: list[UsageByModel]


def _usage_columns():
    return (
        func.count(UsageEvent.id).label("requests"),
        func.coalesce(func.sum(UsageEvent.input_tokens), 0).label("input_tokens"),
        func.coalesce(func.sum(UsageEvent.output_tokens), 0).label("output_tokens"),
        func.coalesce(func.sum(UsageEvent.cached_input_tokens), 0).label(
            "cached_input_tokens"
        ),
        func.coalesce(func.sum(UsageEvent.reasoning_tokens), 0).label("reasoning_tokens"),
    )


def _totals(row) -> dict[str, int]:
    return {
        "requests": int(row.requests),
        "input_tokens": int(row.input_tokens),
        "output_tokens": int(row.output_tokens),
        "cached_input_tokens": int(row.cached_input_tokens),
        "reasoning_tokens": int(row.reasoning_tokens),
    }


@router.get("/keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    identity: Identity = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await key_service.list_active(db, identity.user_id)


@router.post("/keys", response_model=CreatedApiKeyOut, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateApiKeyIn,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    return await key_service.create(db, identity.user_id, payload.name)


@router.delete("/keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    await key_service.revoke(db, identity.user_id, key_id)


@router.get("/usage", response_model=DeveloperUsageOut)
async def developer_usage(
    identity: Identity = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    """Aggregate metering only; prompt and response content never appears here."""
    period_start = datetime.now(UTC) - timedelta(hours=24)
    owner = (UsageEvent.user_id == identity.user_id, UsageEvent.type == UsageType.CHAT)

    lifetime = (await db.execute(select(*_usage_columns()).where(*owner))).one()
    recent = (
        await db.execute(
            select(*_usage_columns()).where(*owner, UsageEvent.created_at >= period_start)
        )
    ).one()

    source_rows = (
        await db.execute(
            select(UsageEvent.source, *_usage_columns())
            .where(*owner)
            .group_by(UsageEvent.source)
            .order_by(UsageEvent.source)
        )
    ).all()
    model_rows = (
        await db.execute(
            select(UsageEvent.model, *_usage_columns())
            .where(*owner)
            .group_by(UsageEvent.model)
            .order_by(UsageEvent.model)
        )
    ).all()

    return {
        "period_start": period_start,
        "lifetime": _totals(lifetime),
        "last_24_hours": _totals(recent),
        "by_source": [
            {"source": row.source, **_totals(row)} for row in source_rows
        ],
        "by_model": [
            {"model": row.model or "unknown", **_totals(row)} for row in model_rows
        ],
    }
