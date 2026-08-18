"""Background sweeps.

Anonymous conversations and expired API content records are deleted on their
respective retention schedules. Runs in a lifespan loop guarded by a Redis leader
lock so it fires once per interval across all gunicorn workers. The durable
usage_events ledger (metering) is untouched.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from redis.asyncio import Redis
from sqlalchemy import delete

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import ApiContentRecord, Conversation

log = get_logger(__name__)

_LOCK_KEY = "sweep:retained_content:lock"


async def sweep_anon_conversations(retention_days: int) -> int:
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    async with SessionLocal() as db:
        result = await db.execute(
            delete(Conversation).where(
                Conversation.user_id.is_(None), Conversation.updated_at < cutoff
            )
        )
        await db.commit()
        return result.rowcount or 0


async def sweep_api_content() -> int:
    async with SessionLocal() as db:
        result = await db.execute(
            delete(ApiContentRecord).where(ApiContentRecord.expires_at <= datetime.now(UTC))
        )
        await db.commit()
        return result.rowcount or 0


async def sweep_loop(redis: Redis) -> None:
    settings = get_settings()
    interval = settings.conv_sweep_interval_s
    while True:
        try:
            # Leader lock (NX + TTL≈interval): only one worker sweeps per interval.
            if await redis.set(_LOCK_KEY, "1", nx=True, ex=interval):
                swept = await sweep_anon_conversations(settings.anon_conv_retention_days)
                if swept:
                    log.info("swept_anon_conversations", count=swept)
                swept_api = await sweep_api_content()
                if swept_api:
                    log.info("swept_api_content", count=swept_api)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never let the loop die
            log.exception("sweep_loop_error")
        await asyncio.sleep(interval)
