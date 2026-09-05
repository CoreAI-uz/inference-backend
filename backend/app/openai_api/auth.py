"""Bearer authentication for developer API requests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth.dependencies import Identity, _client_ip
from app.core.config import get_settings
from app.models import ApiKey
from app.openai_api.errors import OpenAIAPIError
from app.services.api_keys import authenticate
from app.services.data_policy import has_legal_acceptance


@dataclass(frozen=True)
class APIPrincipal:
    user_id: uuid.UUID
    api_key_id: uuid.UUID
    identity: Identity
    unlimited: bool = False
    no_content_retention: bool = False


def _unauthorized() -> OpenAIAPIError:
    return OpenAIAPIError(
        401,
        "Incorrect API key provided.",
        code="invalid_api_key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_api_key(
    request: Request, db: AsyncSession = Depends(get_db)
) -> APIPrincipal:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized()

    key: ApiKey | None = await authenticate(db, token.strip())
    if key is None:
        raise _unauthorized()
    if not await has_legal_acceptance(db, key.user_id):
        raise OpenAIAPIError(
            403,
            "Accept the current Terms of Service in the CoreAI API console.",
            code="legal_acceptance_required",
        )

    identity = Identity(
        session_id=f"api:{key.id}",
        user_id=key.user_id,
        ip=_client_ip(request),
    )
    settings = get_settings()
    no_content_retention = key.user_id in settings.api_no_content_retention_user_ids
    return APIPrincipal(
        user_id=key.user_id, api_key_id=key.id, identity=identity,
        unlimited=key.user_id in settings.api_unlimited_user_ids,
        no_content_retention=no_content_retention,
    )
