"""Conversation data-access + the chat persistence path.

Ownership is identity-based: a registered user owns conversations where
``user_id == their id``; an anonymous session owns conversations where
``session_id == theirs AND user_id IS NULL`` (i.e. not yet claimed by an account).
A miss is a 404 at the router (never 403), so others' rows don't leak.
``persist_branch_turn`` flushes but does not commit; the chat service commits the turn
before attempting best-effort metering in a separate transaction.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import Identity
from app.db.types import FinishReason, MessageRole
from app.models import Conversation, Message
from app.services.titles import DEFAULT_TITLE, derive_title


class NotOwnedError(Exception):
    """conversation_id was supplied but is not owned by / visible to the identity."""


def owner_filter(identity: Identity) -> ColumnElement[bool]:
    if identity.user_id is not None:
        return Conversation.user_id == identity.user_id
    return and_(
        Conversation.session_id == identity.session_id,
        Conversation.user_id.is_(None),
    )


async def get_owned_conversation(
    db: AsyncSession, conversation_id: uuid.UUID, identity: Identity
) -> Conversation | None:
    result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id, owner_filter(identity))
    )
    return result.scalar_one_or_none()


async def get_conversation_detail(
    db: AsyncSession, conversation_id: uuid.UUID, identity: Identity
) -> Conversation | None:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.id == conversation_id, owner_filter(identity))
        .options(selectinload(Conversation.messages))
    )
    return result.scalar_one_or_none()


async def get_message_in_conversation(
    db: AsyncSession, message_id: uuid.UUID, conversation_id: uuid.UUID
) -> Message | None:
    return (
        await db.execute(
            select(Message).where(
                Message.id == message_id, Message.conversation_id == conversation_id
            )
        )
    ).scalar_one_or_none()


async def build_lineage(db: AsyncSession, node_id: uuid.UUID | None) -> list[Message]:
    """Messages from the root down to ``node_id`` (inclusive), walking parent_id up.
    This is the model context for a reply — the path leading to the message being
    answered. Empty when ``node_id`` is None (start of a new conversation)."""
    chain: list[Message] = []
    nid = node_id
    while nid is not None:
        msg = (
            await db.execute(select(Message).where(Message.id == nid))
        ).scalar_one_or_none()
        if msg is None:
            break
        chain.append(msg)
        nid = msg.parent_id
    chain.reverse()
    return chain


async def select_version(db: AsyncSession, conv: Conversation, message: Message) -> None:
    """Make ``message`` the selected child of its parent (or the active root), so the
    active path runs through it. Deeper selections are untouched (per-branch memory)."""
    if message.parent_id is None:
        conv.active_child_id = message.id
    else:
        await db.execute(
            update(Message)
            .where(Message.id == message.parent_id)
            .values(active_child_id=message.id)
        )
    await db.commit()


async def delete_message(db: AsyncSession, conv: Conversation, message: Message) -> None:
    """Delete a message and its whole subtree (parent_id ON DELETE CASCADE). If the
    deleted node was the selected one on the active path, its parent's active_child (or
    the conversation's active root) is left dangling by the SET NULL FK — re-point it to
    the newest remaining sibling so the conversation still resolves to a coherent path."""
    parent_id = message.parent_id
    await db.execute(delete(Message).where(Message.id == message.id))
    await db.flush()

    sib_q = select(Message.id).where(Message.conversation_id == conv.id)
    sib_q = sib_q.where(Message.parent_id.is_(None) if parent_id is None else Message.parent_id == parent_id)
    newest_sibling = (await db.execute(sib_q.order_by(Message.created_at.desc()))).scalars().first()

    if parent_id is None:
        current = (
            await db.execute(select(Conversation.active_child_id).where(Conversation.id == conv.id))
        ).scalar_one()
        if current is None and newest_sibling is not None:
            await db.execute(
                update(Conversation).where(Conversation.id == conv.id).values(active_child_id=newest_sibling)
            )
    else:
        current = (
            await db.execute(select(Message.active_child_id).where(Message.id == parent_id))
        ).scalar_one_or_none()
        if current is None and newest_sibling is not None:
            await db.execute(
                update(Message).where(Message.id == parent_id).values(active_child_id=newest_sibling)
            )
    await db.commit()


async def list_conversations(db: AsyncSession, user_id: uuid.UUID) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    return list(result.scalars().all())


async def create_conversation(
    db: AsyncSession, user_id: uuid.UUID, *, title: str | None, model: str
) -> Conversation:
    conv = Conversation(user_id=user_id, title=title or DEFAULT_TITLE, model=model)
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


async def rename_conversation(db: AsyncSession, conv: Conversation, title: str) -> Conversation:
    conv.title = title
    await db.commit()
    await db.refresh(conv)
    return conv


async def delete_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> None:
    await db.execute(delete(Conversation).where(Conversation.id == conversation_id))
    await db.commit()


async def active_leaf_id(db: AsyncSession, conv: Conversation) -> uuid.UUID | None:
    """Tip of the conversation's active path: follow active_child_id from the active
    root down until a node has no selected child."""
    node_id = conv.active_child_id
    while node_id is not None:
        nxt = (
            await db.execute(select(Message.active_child_id).where(Message.id == node_id))
        ).scalar_one_or_none()
        if nxt is None:
            return node_id
        node_id = nxt
    return None


async def persist_branch_turn(
    db: AsyncSession,
    *,
    identity: Identity,
    conversation_id: uuid.UUID | None,
    model: str,
    mode: str,
    attach_parent_id: uuid.UUID | None,
    new_user_content: str | None,
    assistant_content: str,
    reasoning: str | None,
    reasoning_ms: int | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    finish_reason: str,
) -> tuple[Conversation, Message]:
    """Persist one generated turn into the message tree, advancing the active path to
    the new reply. Flushes only (the caller commits the turn). Two modes:

    - ``"user"``: create a user message (``new_user_content``) under ``attach_parent_id``
      — a new turn when the parent is the active leaf, a sibling edit otherwise — then a
      reply under it. Auto-creates + auto-titles a conversation when ``conversation_id``
      is None.
    - ``"regenerate"``: ``attach_parent_id`` is an existing user message; create a new
      assistant sibling under it (no new user message).
    """
    if conversation_id is not None:
        conv = await get_owned_conversation(db, conversation_id, identity)
        if conv is None:
            raise NotOwnedError(str(conversation_id))
    else:
        conv = Conversation(
            user_id=identity.user_id,
            session_id=None if identity.user_id else identity.session_id,
            title=DEFAULT_TITLE,
            model=model,
        )
        db.add(conv)
        await db.flush()

    if mode == "user":
        user_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.USER,
            content=new_user_content or "",
            model=None,
            parent_id=attach_parent_id,
        )
        db.add(user_msg)
        await db.flush()
        # Redirect the active path onto the new user message.
        if attach_parent_id is None:
            conv.active_child_id = user_msg.id
        else:
            await db.execute(
                update(Message)
                .where(Message.id == attach_parent_id)
                .values(active_child_id=user_msg.id)
            )
        assistant_parent_id = user_msg.id
        if mode == "user" and (not conv.title or conv.title == DEFAULT_TITLE):
            conv.title = derive_title(new_user_content or "")
    else:  # regenerate — attach_parent_id is the existing user message
        assistant_parent_id = attach_parent_id

    assistant = Message(
        conversation_id=conv.id,
        role=MessageRole.ASSISTANT,
        content=assistant_content,
        reasoning=reasoning or None,
        reasoning_ms=reasoning_ms,
        model=model,
        parent_id=assistant_parent_id,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        finish_reason=FinishReason(finish_reason) if finish_reason else None,
    )
    db.add(assistant)
    await db.flush()
    # Switch the active reply to the new assistant message.
    await db.execute(
        update(Message)
        .where(Message.id == assistant_parent_id)
        .values(active_child_id=assistant.id)
    )

    await db.execute(
        update(Conversation).where(Conversation.id == conv.id).values(updated_at=func.now())
    )
    await db.flush()
    return conv, assistant
