"""Google Identity Services credential verification."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import EmailStr, TypeAdapter, ValidationError

from app.core.config import get_settings
from app.gateway.errors import APIError, ErrorCode

_email_adapter = TypeAdapter(EmailStr)


@dataclass(frozen=True)
class GoogleClaims:
    subject: str
    email: str
    display_name: str


async def verify_google_credential(credential: str) -> GoogleClaims:
    client_id = get_settings().google_client_id
    if not client_id:
        raise APIError(
            503,
            ErrorCode.AUTH_PROVIDER_UNAVAILABLE,
            "Google sign-in is temporarily unavailable",
        )

    try:
        claims = await asyncio.to_thread(
            id_token.verify_oauth2_token,
            credential,
            google_requests.Request(),
            client_id,
        )
        subject = claims.get("sub")
        raw_email = claims.get("email")
        if not isinstance(subject, str) or not subject:
            raise ValueError("missing subject")
        if claims.get("email_verified") is not True:
            raise ValueError("email is not verified")
        email = str(_email_adapter.validate_python(raw_email))
    except (ValueError, ValidationError):
        raise APIError(
            401,
            ErrorCode.INVALID_IDENTITY_TOKEN,
            "Google sign-in could not be verified",
        ) from None

    raw_name = claims.get("name")
    display_name = " ".join(raw_name.split())[:80] if isinstance(raw_name, str) else ""
    return GoogleClaims(subject=subject, email=email, display_name=display_name)
