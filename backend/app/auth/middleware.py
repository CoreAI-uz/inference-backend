"""Anonymous session middleware.

Guarantees ``request.state.session_id`` on every request (mint-if-absent) and sets
a signed HttpOnly cookie when a new one is minted. This is the anchor the rate
limiter + metering key anonymous usage on. M5 layers authenticated JWT sessions on
top; this anon session always persists (same id across login → usage stitches).
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.types import ASGIApp

from app.core.config import get_settings
from app.core.security import sign_session, unsign_session

ANON_COOKIE = "coreai_sid"


class AnonSessionMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next):
        # Developer API calls authenticate independently with Bearer keys and should
        # not receive browser-session cookies as a side effect.
        path = request.url.path
        is_health_check = path == "/api/health" or path.startswith("/api/health/")
        if path.startswith("/v1/") or is_health_check:
            request.state.session_id = None
            return await call_next(request)

        settings = get_settings()
        token = request.cookies.get(ANON_COOKIE)
        sid = unsign_session(token, max_age=settings.anon_cookie_ttl_s) if token else None
        is_new = sid is None
        if sid is None:
            sid = uuid.uuid4().hex
        request.state.session_id = sid

        response = await call_next(request)

        if is_new:
            response.set_cookie(
                ANON_COOKIE,
                sign_session(sid),
                max_age=settings.anon_cookie_ttl_s,
                httponly=True,
                secure=settings.cookie_secure,
                samesite="lax",
                path="/",
            )
        return response
