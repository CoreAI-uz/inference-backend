"""Shared error taxonomy (used by chat SSE, OCR polling, and HTTP bodies)."""

from __future__ import annotations

from enum import StrEnum

from fastapi import Request
from fastapi.responses import JSONResponse


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    UNAUTHORIZED = "unauthorized"
    EMAIL_TAKEN = "email_taken"
    ACCOUNT_LINK_REQUIRED = "account_link_required"
    AUTH_PROVIDER_UNAVAILABLE = "auth_provider_unavailable"
    INVALID_IDENTITY_TOKEN = "invalid_identity_token"
    PENDING_REGISTRATION_EXPIRED = "pending_registration_expired"
    IDENTITY_ALREADY_LINKED = "identity_already_linked"
    LAST_SIGN_IN_METHOD = "last_sign_in_method"
    LEGAL_ACCEPTANCE_REQUIRED = "legal_acceptance_required"
    NOT_FOUND = "not_found"
    MODEL_NOT_FOUND = "model_not_found"
    RATE_LIMITED = "rate_limited"
    INPUT_TOO_LONG = "input_too_long"
    CONTEXT_LENGTH_EXCEEDED = "context_length_exceeded"
    CONTENT_BLOCKED = "content_blocked"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"
    UPSTREAM_TIMEOUT = "upstream_timeout"
    CLIENT_CLOSED = "client_closed"
    INTERNAL_ERROR = "internal_error"


class APIError(Exception):
    """A non-streaming (pre-flight) error → uniform JSON body ``{error, message, ...}``.

    Used for anything detectable before the SSE stream opens (rate limit, bad model,
    over-long input, auth). Once streaming has started, failures are SSE ``error``
    events instead (see gateway/events.py).
    """

    def __init__(
        self,
        status_code: int,
        code: ErrorCode,
        message: str,
        *,
        retry_after: int | None = None,
        upgrade_hint: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after = retry_after
        self.upgrade_hint = upgrade_hint

    def body(self) -> dict:
        data: dict = {"error": self.code.value, "message": self.message}
        if self.retry_after is not None:
            data["retry_after"] = self.retry_after
        if self.upgrade_hint is not None:
            data["upgrade_hint"] = self.upgrade_hint
        return data


async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
    headers = {}
    if exc.retry_after is not None:
        headers["Retry-After"] = str(exc.retry_after)
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=headers)


class GatewayError(Exception):
    def __init__(self, code: ErrorCode, message: str, *, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retry_after = retry_after

    def to_event_data(self) -> dict:
        data: dict = {"code": self.code.value, "message": self.message}
        if self.retry_after is not None:
            data["retry_after"] = self.retry_after
        return data
