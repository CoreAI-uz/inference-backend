"""Integration tests for message editing/branching (service layer, against the dev DB).

Run in-container: `docker compose exec backend pytest tests/test_branching.py`.
Every test uses an anonymous (session-owned) identity, so they double as the anon-parity
check: editing, regenerating, switching, and deleting all work without an account.
"""

import uuid

import pytest
from sqlalchemy import delete, select

from app.auth.dependencies import Identity
from app.db.session import SessionLocal, engine
from app.db.types import MessageRole
from app.models import Conversation, Message
from app.services import conversations as svc


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """pytest-asyncio gives each test a fresh event loop; the shared async engine pools
    asyncpg connections bound to the previous loop. Dispose after each test so the next
    one opens connections on its own loop (avoids 'attached to a different loop')."""
    yield
    await engine.dispose()


def _ident() -> Identity:
    return Identity(session_id=f"test-{uuid.uuid4().hex}", user_id=None, ip="127.0.0.1")


async def _persist(db, ident, *, conversation_id, mode, attach_parent_id, new_user_content, assistant="reply"):
    conv, a = await svc.persist_branch_turn(
        db,
        identity=ident,
        conversation_id=conversation_id,
        model="gemma-mock",
        mode=mode,
        attach_parent_id=attach_parent_id,
        new_user_content=new_user_content,
        assistant_content=assistant,
        reasoning=None,
        reasoning_ms=None,
        prompt_tokens=1,
        completion_tokens=1,
        finish_reason="stop",
    )
    await db.commit()
    return conv, a


async def _children(db, cid, parent_id):
    q = select(Message).where(Message.conversation_id == cid)
    q = q.where(Message.parent_id.is_(None) if parent_id is None else Message.parent_id == parent_id)
    return list((await db.execute(q.order_by(Message.created_at))).scalars().all())


async def _conv(db, cid):
    return (await db.execute(select(Conversation).where(Conversation.id == cid))).scalar_one()


async def _cleanup(cid):
    async with SessionLocal() as db:
        await db.execute(delete(Conversation).where(Conversation.id == cid))
        await db.commit()


async def test_new_turn_builds_linear_tree():
    ident = _ident()
    async with SessionLocal() as db:
        conv, _ = await _persist(db, ident, conversation_id=None, mode="user", attach_parent_id=None, new_user_content="hi")
        cid = conv.id
    try:
        async with SessionLocal() as db:
            roots = await _children(db, cid, None)
            assert len(roots) == 1 and roots[0].role == MessageRole.USER
            assert roots[0].parent_id is None
            kids = await _children(db, cid, roots[0].id)
            assert len(kids) == 1 and kids[0].role == MessageRole.ASSISTANT
            leaf = await svc.active_leaf_id(db, await _conv(db, cid))
            assert leaf == kids[0].id
    finally:
        await _cleanup(cid)


async def test_edit_root_creates_sibling_and_restore():
    ident = _ident()
    async with SessionLocal() as db:
        conv, _ = await _persist(db, ident, conversation_id=None, mode="user", attach_parent_id=None, new_user_content="Q1")
        cid = conv.id
        u1_id = (await _children(db, cid, None))[0].id
    try:
        # edit the first message -> a second root sibling, active flips to it
        async with SessionLocal() as db:
            await _persist(db, ident, conversation_id=cid, mode="user", attach_parent_id=None, new_user_content="Q1-edit")
        async with SessionLocal() as db:
            roots = await _children(db, cid, None)
            assert len(roots) == 2
            conv = await _conv(db, cid)
            edited = next(r for r in roots if r.content == "Q1-edit")
            assert conv.active_child_id == edited.id
        # switch back to the original -> exact prior path restored
        async with SessionLocal() as db:
            conv = await _conv(db, cid)
            u1 = await svc.get_message_in_conversation(db, u1_id, cid)
            await svc.select_version(db, conv, u1)
        async with SessionLocal() as db:
            conv = await _conv(db, cid)
            assert conv.active_child_id == u1_id
    finally:
        await _cleanup(cid)


async def test_regenerate_adds_assistant_sibling():
    ident = _ident()
    async with SessionLocal() as db:
        conv, _ = await _persist(db, ident, conversation_id=None, mode="user", attach_parent_id=None, new_user_content="Q")
        cid = conv.id
        u_id = (await _children(db, cid, None))[0].id
    try:
        async with SessionLocal() as db:
            await _persist(db, ident, conversation_id=cid, mode="regenerate", attach_parent_id=u_id, new_user_content=None, assistant="reply2")
        async with SessionLocal() as db:
            replies = await _children(db, cid, u_id)
            assert len(replies) == 2 and all(r.role == MessageRole.ASSISTANT for r in replies)
            u_row = (await db.execute(select(Message).where(Message.id == u_id))).scalar_one()
            # active reply switched to the newest sibling
            assert u_row.active_child_id == max(replies, key=lambda r: r.created_at).id
    finally:
        await _cleanup(cid)


async def test_build_lineage_is_root_to_node():
    ident = _ident()
    async with SessionLocal() as db:
        conv, _ = await _persist(db, ident, conversation_id=None, mode="user", attach_parent_id=None, new_user_content="Q1")
        cid = conv.id
    try:
        async with SessionLocal() as db:
            leaf = await svc.active_leaf_id(db, await _conv(db, cid))
            lineage = await svc.build_lineage(db, leaf)
            assert [m.role for m in lineage] == [MessageRole.USER, MessageRole.ASSISTANT]
            assert lineage[0].parent_id is None and lineage[-1].id == leaf
    finally:
        await _cleanup(cid)


async def test_delete_version_repoints_active():
    ident = _ident()
    async with SessionLocal() as db:
        conv, _ = await _persist(db, ident, conversation_id=None, mode="user", attach_parent_id=None, new_user_content="Q")
        cid = conv.id
        u_id = (await _children(db, cid, None))[0].id
    try:
        # two assistant versions under the user message
        async with SessionLocal() as db:
            await _persist(db, ident, conversation_id=cid, mode="regenerate", attach_parent_id=u_id, new_user_content=None, assistant="reply2")
        async with SessionLocal() as db:
            u_row = (await db.execute(select(Message).where(Message.id == u_id))).scalar_one()
            active_reply_id = u_row.active_child_id
            conv = await _conv(db, cid)
            msg = await svc.get_message_in_conversation(db, active_reply_id, cid)
            await svc.delete_message(db, conv, msg)
        async with SessionLocal() as db:
            replies = await _children(db, cid, u_id)
            assert len(replies) == 1
            assert replies[0].id != active_reply_id
            u_row = (await db.execute(select(Message).where(Message.id == u_id))).scalar_one()
            # active pointer re-pointed to the surviving sibling (not left dangling)
            assert u_row.active_child_id == replies[0].id
    finally:
        await _cleanup(cid)
