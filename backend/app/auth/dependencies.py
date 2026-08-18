"""Identity — the single source of truth for who is making a request.

Every subsystem (chat, rate-limit, metering, later conversations/ocr) consumes
``Identity`` and uses its accessors; none re-derives identity. M4 ships the
anon-only version (``user_id`` always None). M5 fills in the JWT decode that sets
``user_id`` — no call sites change, only the tier/caps swap in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import AUTH_COOKIE
from app.core.config import get_settings
from app.core.security import decode_access
from app.db.session import get_db
from app.db.types import Tier
from app.gateway.errors import APIError, ErrorCode
from app.models import User


@dataclass(frozen=True)
class Identity:
    session_id: str            # always present (guaranteed by AnonSessionMiddleware)
    user_id: uuid.UUID | None  # None => anonymous
    ip: str

    @property
    def is_anon(self) -> bool:
        return self.user_id is None

    @property
    def scope_id(self) -> str:
        return str(self.user_id) if self.user_id else self.session_id

    @property
    def tier(self) -> Tier:
        return Tier.REGISTERED if self.user_id else Tier.ANON


def _client_ip(request: Request) -> str:
    if get_settings().trusted_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def get_current_identity(
    request: Request, db: AsyncSession = Depends(get_db)
) -> Identity:
    session_id = getattr(request.state, "session_id", None) or "no-session"
    user_id = None
    token = request.cookies.get(AUTH_COOKIE)
    if token:
        candidate = decode_access(token)
        if candidate is not None and await db.get(User, candidate) is not None:
            user_id = candidate
    return Identity(session_id=session_id, user_id=user_id, ip=_client_ip(request))


def require_user(identity: Identity = Depends(get_current_identity)) -> Identity:
    if identity.user_id is None:
        raise APIError(401, ErrorCode.UNAUTHORIZED, "authentication required")
    return identity
