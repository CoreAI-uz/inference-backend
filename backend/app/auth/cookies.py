"""Host-only HttpOnly authentication cookie helpers for the chat/API account."""

from __future__ import annotations

from starlette.responses import Response

from app.core.config import get_settings

AUTH_COOKIE = "coreai_auth"
GOOGLE_PENDING_COOKIE = "coreai_google_pending"


def set_auth_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        AUTH_COOKIE,
        token,
        max_age=settings.access_token_ttl_s,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(AUTH_COOKIE, path="/")


def set_google_pending_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        GOOGLE_PENDING_COOKIE,
        token,
        max_age=settings.google_pending_ttl_s,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/auth/google",
    )


def clear_google_pending_cookie(response: Response) -> None:
    response.delete_cookie(GOOGLE_PENDING_COOKIE, path="/api/auth/google")
