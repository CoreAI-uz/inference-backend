"""Chat streaming endpoint.

Pre-flight (JSON errors before the stream opens): rate limit (429), unknown model
(404), over-long input (413), non-owned conversation (404). Once streaming, only SSE
events flow (delta / usage / queued / done / error).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth.dependencies import Identity
from app.core.config import get_settings
from app.db.types import Bucket, MessageRole
from app.gateway.errors import APIError, ErrorCode
from app.gateway.events import SSE_HEADERS
from app.gateway.ratelimit import rate_limit
from app.gateway.registry import ModelNotFoundError, get_registry
from app.schemas.chat import ChatRequest
from app.services.chat_service import stream_chat_completion
from app.services.conversations import (
    active_leaf_id,
    build_lineage,
    get_message_in_conversation,
    get_owned_conversation,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/completions")
async def chat_completions(
    payload: ChatRequest,
    request: Request,
    identity: Identity = Depends(rate_limit(Bucket.CHAT)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    settings = get_settings()

    try:
        model_id, cfg = get_registry().get(payload.model)
    except ModelNotFoundError:
        raise APIError(404, ErrorCode.MODEL_NOT_FOUND,
                       f"unknown or unavailable model: {payload.model!r}") from None

    # --- Resolve conversation + optional branch parent (ownership → 404) ---
    conversation_id: uuid.UUID | None = None
    conv = None
    if payload.conversation_id:
        try:
            conversation_id = uuid.UUID(payload.conversation_id)
        except ValueError:
            raise APIError(
                400, ErrorCode.INVALID_REQUEST, "invalid conversation_id"
            ) from None
        conv = await get_owned_conversation(db, conversation_id, identity)
        if conv is None:
            raise APIError(404, ErrorCode.NOT_FOUND, "conversation not found")

    # An explicitly-sent parent_id (even null) is meaningful: null → attach as a new
    # root sibling (editing the first message); a value → attach under that node.
    # An omitted parent_id → attach under the conversation's active leaf (a new turn).
    parent_id_sent = "parent_id" in payload.model_fields_set
    parent = None
    if payload.parent_id is not None:
        if conv is None:
            raise APIError(400, ErrorCode.INVALID_REQUEST, "parent_id requires a conversation_id")
        try:
            parent_uuid = uuid.UUID(payload.parent_id)
        except ValueError:
            raise APIError(400, ErrorCode.INVALID_REQUEST, "invalid parent_id") from None
        parent = await get_message_in_conversation(db, parent_uuid, conv.id)
        if parent is None:
            raise APIError(404, ErrorCode.NOT_FOUND, "parent message not found")

    # --- Determine mode + assemble the model context from the tree lineage ---
    # user_content (edit / explicit) wins; else derive from messages (new-turn/compat).
    new_user_content = payload.user_content
    if new_user_content is None and payload.messages:
        new_user_content = next(
            (m.content for m in reversed(payload.messages) if m.role == "user"), None
        )

    if new_user_content is not None:
        mode = "user"
        if not new_user_content.strip():
            raise APIError(400, ErrorCode.INVALID_REQUEST, "message is empty")
        if len(new_user_content) > settings.max_chat_input_chars:
            raise APIError(413, ErrorCode.INPUT_TOO_LONG,
                           f"message exceeds {settings.max_chat_input_chars} characters")
        if parent is not None:
            attach_parent_id = parent.id           # under a given node (edit a reply's child)
        elif parent_id_sent:
            attach_parent_id = None                # explicit null → new root sibling
        elif conv is not None:
            attach_parent_id = await active_leaf_id(db, conv)  # new turn → active leaf
        else:
            attach_parent_id = None                # first message of a new conversation
        lineage = await build_lineage(db, attach_parent_id)
        context = [{"role": m.role.value, "content": m.content} for m in lineage]
        context.append({"role": "user", "content": new_user_content})
    else:
        # Regenerate: parent must be an existing user message; reply gets a sibling.
        if parent is None:
            raise APIError(400, ErrorCode.INVALID_REQUEST, "nothing to send")
        if parent.role != MessageRole.USER:
            raise APIError(400, ErrorCode.INVALID_REQUEST,
                           "can only regenerate the reply to a user message")
        mode = "regenerate"
        attach_parent_id = parent.id
        lineage = await build_lineage(db, parent.id)
        context = [{"role": m.role.value, "content": m.content} for m in lineage]

    generator = stream_chat_completion(
        request=request,
        http=request.app.state.http,
        identity=identity,
        cfg=cfg,
        model_id=model_id,
        messages=context,
        conversation_id=conversation_id,
        mode=mode,
        attach_parent_id=attach_parent_id,
        new_user_content=new_user_content,
        thinking=payload.thinking,
    )
    return StreamingResponse(generator, media_type="text/event-stream", headers=SSE_HEADERS)
