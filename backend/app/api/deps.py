"""Shared FastAPI dependencies (infra-level: db, redis, settings).

Identity dependencies (``get_current_identity``) live in ``app.auth.dependencies``
and land in M5.
"""

from __future__ import annotations

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.db.session import get_db  # re-exported for convenience

__all__ = ["get_db", "get_redis", "get_settings_dep"]


def get_settings_dep() -> Settings:
    return get_settings()


def get_redis(request: Request) -> Redis:
    return request.app.state.redis
