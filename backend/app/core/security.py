"""Security primitives: anon-session signing, argon2 password hashing, auth JWT."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import Argon2Error
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.core.config import get_settings

_ANON_SALT = "anon-session"
_GOOGLE_PENDING_SALT = "google-pending-registration"
_ph = PasswordHasher()
# Precomputed so login against an unknown email still spends ~one argon2 verify
# (constant-time-ish; blunts user enumeration by timing).
_DUMMY_HASH = _ph.hash("dummy-password-for-timing-defense")


# --- anon session cookie (itsdangerous) ---
def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=_ANON_SALT)


def sign_session(session_id: str) -> str:
    return _serializer().dumps(session_id)


def unsign_session(token: str, *, max_age: int | None = None) -> str | None:
    try:
        return _serializer().loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None


def _google_pending_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().session_secret, salt=_GOOGLE_PENDING_SALT)


def sign_google_pending(payload: dict[str, str]) -> str:
    return _google_pending_serializer().dumps(payload)


def unsign_google_pending(token: str) -> dict[str, str] | None:
    try:
        value = _google_pending_serializer().loads(
            token, max_age=get_settings().google_pending_ttl_s
        )
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        return None
    return value


# --- passwords (argon2id) ---
def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _ph.verify(password_hash, password)
    except Argon2Error:
        return False


def dummy_verify(password: str) -> None:
    """Spend an argon2 verify against a fixed hash (timing defense for unknown user)."""
    try:
        _ph.verify(_DUMMY_HASH, password)
    except Argon2Error:
        pass


# --- auth JWT (HS256) ---
def encode_access(user_id: uuid.UUID) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.access_token_ttl_s)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access(token: str) -> uuid.UUID | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
