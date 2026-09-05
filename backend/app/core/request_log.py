"""Structured per-request access log.

One line per request (health checks excluded): request_id, method, path, status,
latency, and the session it came from. Attaches an X-Request-ID response header.
Sits inside AnonSessionMiddleware so request.state.session_id is populated.
"""

from __future__ import annotations

import re
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger

log = get_logger("request")
_CLIENT_REQUEST_ID = re.compile(r"^[\x21-\x7e]{1,128}$")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        client_request_id = request.headers.get("x-client-request-id")
        if client_request_id and not _CLIENT_REQUEST_ID.fullmatch(client_request_id):
            client_request_id = None
        request.state.client_request_id = client_request_id
        start = time.perf_counter()
        response = await call_next(request)
        latency_ms = round((time.perf_counter() - start) * 1000, 1)

        path = request.url.path
        if not path.startswith("/api/health") and not getattr(request.state, "api_no_retention", False):
            log.info(
                "request",
                request_id=request_id,
                method=request.method,
                path=path,
                status=response.status_code,
                latency_ms=latency_ms,
                session=getattr(request.state, "session_id", None),
                client_request_id=client_request_id,
            )
        response.headers["X-Request-ID"] = request_id
        if client_request_id:
            response.headers["X-Client-Request-ID"] = client_request_id
        return response
