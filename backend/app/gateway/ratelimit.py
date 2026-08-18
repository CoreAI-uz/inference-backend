"""Redis token-bucket rate limiting.

One atomic Lua script per check (no fixed-window boundary bursts, exact retry_after).
Anon requests also hit a coarser per-IP bucket so cookie-clearing doesn't reset the
limit. Numbers come from settings (RL_* env) and are tuned in M8.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.auth.dependencies import Identity, get_current_identity
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.types import Bucket, Tier
from app.gateway.errors import APIError, ErrorCode

log = get_logger(__name__)

# tokens/ts stored in a hash; refill continuous; TTL = time to fully refill (idle GC).
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local t = redis.call('TIME')
local now = tonumber(t[1]) + tonumber(t[2]) / 1000000
local tokens = tonumber(redis.call('HGET', key, 'tokens'))
local ts = tonumber(redis.call('HGET', key, 'ts'))
if tokens == nil then
  tokens = capacity
  ts = now
end
tokens = math.min(capacity, tokens + math.max(0, now - ts) * refill)
local allowed = 0
local retry_after = 0
if tokens >= cost then
  allowed = 1
  tokens = tokens - cost
elseif refill > 0 then
  retry_after = (cost - tokens) / refill
end
redis.call('HSET', key, 'tokens', tokens, 'ts', now)
local ttl = 3600
if refill > 0 then ttl = math.ceil(capacity / refill) + 1 end
redis.call('EXPIRE', key, ttl)
return {allowed, tostring(tokens), tostring(retry_after)}
"""


@dataclass(frozen=True)
class Limit:
    capacity: int          # burst
    refill_per_sec: float  # sustained


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: float
    retry_after: int


@dataclass(frozen=True)
class BucketStatus:
    capacity: int
    remaining: int
    next_token_in: int


def _limits(settings: Settings) -> dict[tuple[Tier, Bucket], Limit]:
    hour = 3600.0
    return {
        (Tier.ANON, Bucket.CHAT): Limit(settings.rl_anon_chat, settings.rl_anon_chat / hour),
        (Tier.REGISTERED, Bucket.CHAT): Limit(settings.rl_user_chat, settings.rl_user_chat / hour),
        (Tier.ANON, Bucket.OCR): Limit(settings.rl_anon_ocr, settings.rl_anon_ocr / hour),
        (Tier.REGISTERED, Bucket.OCR): Limit(settings.rl_user_ocr, settings.rl_user_ocr / hour),
        # Account creations per IP (anti-farming); always anon tier.
        (Tier.ANON, Bucket.SIGNUP): Limit(settings.rl_signup_per_ip, settings.rl_signup_per_ip / hour),
        (Tier.ANON, Bucket.LOGIN): Limit(settings.rl_login_per_ip, settings.rl_login_per_ip / hour),
    }


async def check_and_consume(
    redis: Redis, bucket: Bucket, tier: Tier, scope_id: str, *, cost: int = 1
) -> RateLimitResult:
    limit = _limits(get_settings())[(tier, bucket)]
    key = f"rl:{bucket.value}:{tier.value}:{scope_id}"
    res = await redis.eval(
        TOKEN_BUCKET_LUA, 1, key, limit.capacity, limit.refill_per_sec, cost
    )
    allowed = bool(int(res[0]))
    remaining = float(res[1])
    retry_after = float(res[2])
    return RateLimitResult(
        allowed=allowed,
        remaining=remaining,
        retry_after=math.ceil(retry_after) if retry_after > 0 else 0,
    )


async def chat_bucket_status(redis: Redis, identity: Identity) -> BucketStatus:
    """Return the live chat allowance without consuming a token.

    Anonymous chat is governed by both session and IP buckets, so the lower balance
    is the honest balance to show. Lifetime usage remains a separate DB metric.
    """
    limit = _limits(get_settings())[(identity.tier, Bucket.CHAT)]
    results = [
        await check_and_consume(redis, Bucket.CHAT, identity.tier, identity.scope_id, cost=0)
    ]
    if identity.is_anon:
        results.append(
            await check_and_consume(redis, Bucket.CHAT, Tier.ANON, f"ip:{identity.ip}", cost=0)
        )
    tokens = min(result.remaining for result in results)
    remaining = max(0, math.floor(tokens))
    next_token_in = 0
    if remaining < 1 and limit.refill_per_sec > 0:
        next_token_in = math.ceil((1 - max(0.0, tokens)) / limit.refill_per_sec)
    return BucketStatus(
        capacity=limit.capacity,
        remaining=remaining,
        next_token_in=next_token_in,
    )


def rate_limit(bucket: Bucket):
    """FastAPI dependency factory. Returns the resolved Identity so the endpoint can
    reuse it. Raises APIError(429) pre-flight (before any SSE stream opens)."""

    async def _dep(
        request: Request, identity: Identity = Depends(get_current_identity)
    ) -> Identity:
        redis: Redis = request.app.state.redis
        result = await check_and_consume(redis, bucket, identity.tier, identity.scope_id)
        if identity.is_anon and result.allowed:
            # coarser IP bucket blunts cookie-clearing
            ip_result = await check_and_consume(redis, bucket, Tier.ANON, f"ip:{identity.ip}")
            if not ip_result.allowed:
                result = ip_result
        if not result.allowed:
            log.info("rate_limited", bucket=bucket.value, tier=identity.tier.value,
                     scope=identity.scope_id, retry_after=result.retry_after)
            hint = (
                "Sign up free to keep chatting and save your history."
                if identity.is_anon
                else "High demand — please try again shortly."
            )
            raise APIError(
                429,
                ErrorCode.RATE_LIMITED,
                "rate limit exceeded",
                retry_after=result.retry_after,
                upgrade_hint=hint,
            )
        return identity

    return _dep


async def check_signup_limit(redis: Redis, ip: str) -> None:
    """Per-IP signup throttle (anti-farming). Raises APIError(429) when exceeded."""
    result = await check_and_consume(redis, Bucket.SIGNUP, Tier.ANON, f"ip:{ip}")
    if not result.allowed:
        log.info("signup_rate_limited", ip=ip, retry_after=result.retry_after)
        raise APIError(
            429,
            ErrorCode.RATE_LIMITED,
            "too many accounts created from this network — please try again later",
            retry_after=result.retry_after,
        )


async def check_login_limit(redis: Redis, ip: str, email: str) -> None:
    """Throttle login attempts by network and account without storing email in Redis."""
    settings = get_settings()
    account_hash = hashlib.sha256(email.strip().lower().encode()).hexdigest()[:24]
    scopes = (
        (f"ip:{ip}", settings.rl_login_per_ip),
        (f"account:{account_hash}", settings.rl_login_per_account),
    )
    for scope, capacity in scopes:
        limit = Limit(capacity, capacity / 3600.0)
        key = f"rl:{Bucket.LOGIN.value}:{Tier.ANON.value}:{scope}"
        res = await redis.eval(TOKEN_BUCKET_LUA, 1, key, limit.capacity, limit.refill_per_sec, 1)
        result = RateLimitResult(
            allowed=bool(int(res[0])),
            remaining=float(res[1]),
            retry_after=math.ceil(float(res[2])) if float(res[2]) > 0 else 0,
        )
        if not result.allowed:
            log.info("login_rate_limited", scope=scope.split(":", 1)[0], retry_after=result.retry_after)
            raise APIError(
                429,
                ErrorCode.RATE_LIMITED,
                "too many login attempts — please try again later",
                retry_after=result.retry_after,
            )
