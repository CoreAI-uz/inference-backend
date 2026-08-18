"""OpenAI-compatible HTTP error envelopes for the public `/v1` API."""

from __future__ import annotations

from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class OpenAIAPIError(Exception):
    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        type: str = "invalid_request_error",
        param: str | None = None,
        code: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.type = type
        self.param = param
        self.code = code
        self.headers = headers or {}

    def body(self) -> dict:
        return {
            "error": {
                "message": self.message,
                "type": self.type,
                "param": self.param,
                "code": self.code,
            }
        }


async def openai_error_handler(_request: Request, exc: OpenAIAPIError) -> JSONResponse:
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)


async def public_validation_error_handler(request: Request, exc: RequestValidationError):
    """Keep browser API validation unchanged while normalizing public API errors."""
    if not request.url.path.startswith("/v1/"):
        return await request_validation_exception_handler(request, exc)

    first = exc.errors()[0] if exc.errors() else {}
    location = first.get("loc") or ()
    param = ".".join(str(part) for part in location if part not in {"body", "query"}) or None
    message = first.get("msg") or "Invalid request"
    error = OpenAIAPIError(400, message, param=param, code="invalid_value")
    return JSONResponse(error.body(), status_code=400)
