"""Creation, verification, listing, and revocation of developer API keys."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.gateway.errors import APIError, ErrorCode
from app.models import ApiKey, User
from app.services.data_policy import has_legal_acceptance

KEY_MARKER = "cai_"


def _digest(token: str) -> str:
    pepper = get_settings().api_key_pepper.encode()
    return hmac.new(pepper, token.encode(), hashlib.sha256).hexdigest()


def _split_prefix(token: str) -> str | None:
    parts = token.split("_", 2)
    if len(parts) != 3 or parts[0] != "cai" or not parts[1] or not parts[2]:
        return None
    return f"{KEY_MARKER}{parts[1]}"


def _public_row(key: ApiKey) -> dict:
    return {
        "id": key.id,
        "name": key.name,
        "prefix": key.key_prefix,
        "last_four": key.last_four,
        "created_at": key.created_at,
        "last_used_at": key.last_used_at,
        "expires_at": key.expires_at,
    }


async def list_active(db: AsyncSession, user_id: uuid.UUID | None) -> list[dict]:
    if user_id is None:
        return []
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
        .order_by(ApiKey.created_at.desc())
    )
    return [_public_row(key) for key in result.scalars()]


async def create(db: AsyncSession, user_id: uuid.UUID | None, name: str) -> dict:
    if user_id is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")

    # Lock the owner row so simultaneous creates cannot both pass the active-key cap.
    owner = (
        await db.execute(select(User).where(User.id == user_id).with_for_update())
    ).scalar_one_or_none()
    if owner is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")
    if not await has_legal_acceptance(db, user_id):
        raise APIError(
            403,
            ErrorCode.LEGAL_ACCEPTANCE_REQUIRED,
            "Accept the current Terms of Service before creating an API key.",
        )

    active_count = await db.scalar(
        select(func.count())
        .select_from(ApiKey)
        .where(ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
    )
    if (active_count or 0) >= get_settings().max_api_keys_per_user:
        raise APIError(
            409,
            ErrorCode.INVALID_REQUEST,
            f"at most {get_settings().max_api_keys_per_user} active API keys are allowed",
        )

    public_id = secrets.token_hex(6)
    secret = secrets.token_urlsafe(32)
    token = f"{KEY_MARKER}{public_id}_{secret}"
    row = ApiKey(
        user_id=user_id,
        name=name,
        key_prefix=f"{KEY_MARKER}{public_id}",
        secret_digest=_digest(token),
        last_four=token[-4:],
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {**_public_row(row), "key": token}


async def revoke(db: AsyncSession, user_id: uuid.UUID | None, key_id: uuid.UUID) -> None:
    result = await db.execute(
        update(ApiKey)
        .where(ApiKey.id == key_id, ApiKey.user_id == user_id, ApiKey.revoked_at.is_(None))
        .values(revoked_at=func.now())
        .returning(ApiKey.id)
    )
    if result.scalar_one_or_none() is None:
        await db.rollback()
        raise APIError(404, ErrorCode.NOT_FOUND, "API key not found")
    await db.commit()


async def authenticate(db: AsyncSession, token: str) -> ApiKey | None:
    prefix = _split_prefix(token)
    if prefix is None:
        return None
    key = (
        await db.execute(
            select(ApiKey).where(
                ApiKey.key_prefix == prefix,
                ApiKey.revoked_at.is_(None),
                or_(ApiKey.expires_at.is_(None), ApiKey.expires_at > func.now()),
            )
        )
    ).scalar_one_or_none()
    if key is None or not hmac.compare_digest(key.secret_digest, _digest(token)):
        return None

    # Avoid a write on every request while keeping the developer console useful.
    stale_before = datetime.now(UTC) - timedelta(minutes=5)
    if key.user_id not in get_settings().api_no_retention_user_ids and (
        key.last_used_at is None or key.last_used_at < stale_before
    ):
        await db.execute(update(ApiKey).where(ApiKey.id == key.id).values(last_used_at=func.now()))
        await db.commit()
    return key
