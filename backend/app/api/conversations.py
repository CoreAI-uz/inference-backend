"""Conversations API.

- List / create / rename / delete: registered users only (`require_user`).
- Get one by id: any identity that owns it — so an anonymous user can restore their
  own (session-owned) conversation on refresh via /c/{id}.
Ownership misses return 404 (never 403).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth.dependencies import Identity, get_current_identity, require_user
from app.core.config import get_settings
from app.gateway.errors import APIError, ErrorCode
from app.schemas.conversation import (
    ConversationCreate,
    ConversationDetail,
    ConversationListItem,
    ConversationUpdate,
    SelectVersion,
)
from app.services import conversations as svc

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=list[ConversationListItem])
async def list_conversations(
    identity: Identity = Depends(require_user), db: AsyncSession = Depends(get_db)
):
    return await svc.list_conversations(db, identity.user_id)


@router.post("", response_model=ConversationDetail, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreate,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    model = payload.model or get_settings().resolve_default_model_id()
    if model is None:
        raise APIError(503, ErrorCode.UPSTREAM_UNAVAILABLE, "no inference model is configured")
    conv = await svc.create_conversation(db, identity.user_id, title=payload.title, model=model)
    return await svc.get_conversation_detail(db, conv.id, identity)


@router.get("/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: AsyncSession = Depends(get_db),
):
    conv = await svc.get_conversation_detail(db, conversation_id, identity)
    if conv is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")
    return conv


@router.post("/{conversation_id}/select", status_code=status.HTTP_204_NO_CONTENT)
async def select_version(
    conversation_id: uuid.UUID,
    payload: SelectVersion,
    identity: Identity = Depends(get_current_identity),
    db: AsyncSession = Depends(get_db),
):
    """Persist a branch switch so the choice survives a reload. Any identity that owns
    the conversation (incl. anonymous) may switch its own versions."""
    conv = await svc.get_owned_conversation(db, conversation_id, identity)
    if conv is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")
    msg = await svc.get_message_in_conversation(db, payload.message_id, conv.id)
    if msg is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "message not found")
    await svc.select_version(db, conv, msg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{conversation_id}/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message version and its subtree (any owner, incl. anonymous)."""
    conv = await svc.get_owned_conversation(db, conversation_id, identity)
    if conv is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")
    msg = await svc.get_message_in_conversation(db, message_id, conv.id)
    if msg is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "message not found")
    await svc.delete_message(db, conv, msg)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/{conversation_id}", response_model=ConversationDetail)
async def rename_conversation(
    conversation_id: uuid.UUID,
    payload: ConversationUpdate,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await svc.get_owned_conversation(db, conversation_id, identity)
    if conv is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")
    await svc.rename_conversation(db, conv, payload.title)
    return await svc.get_conversation_detail(db, conversation_id, identity)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: uuid.UUID,
    identity: Identity = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await svc.get_owned_conversation(db, conversation_id, identity)
    if conv is None:
        raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")
    await svc.delete_conversation(db, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
