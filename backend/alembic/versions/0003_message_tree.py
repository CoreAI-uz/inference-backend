"""messages: tree structure for editing & branching

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-15

Adds parent_id + active_child_id to messages and active_child_id (the active root) to
conversations, forming a message tree. Existing flat conversations are backfilled by
chaining each message to its predecessor in (created_at, user-before-assistant) order,
so today's linear history becomes the active path with no visible change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("messages", sa.Column("active_child_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("conversations", sa.Column("active_child_id", postgresql.UUID(as_uuid=True), nullable=True))

    op.create_foreign_key(
        "fk_messages_parent_id_messages", "messages", "messages",
        ["parent_id"], ["id"], ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_messages_active_child_id_messages", "messages", "messages",
        ["active_child_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_conversations_active_child_id_messages", "conversations", "messages",
        ["active_child_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index("ix_messages_parent_id", "messages", ["parent_id"])

    # --- Backfill existing flat conversations into a linear tree ---
    # Order within each conversation by time, user-before-assistant on ties (matches
    # the ORM relationship order); chain parent_id (LAG) and active_child_id (LEAD).
    op.execute(
        """
        WITH ordered AS (
            SELECT id, conversation_id,
                   row_number() OVER (
                       PARTITION BY conversation_id
                       ORDER BY created_at, (role = 'assistant')
                   ) AS rn
            FROM messages
        ),
        chained AS (
            SELECT id,
                   LAG(id)  OVER (PARTITION BY conversation_id ORDER BY rn) AS parent_id,
                   LEAD(id) OVER (PARTITION BY conversation_id ORDER BY rn) AS active_child_id
            FROM ordered
        )
        UPDATE messages m
        SET parent_id = c.parent_id,
            active_child_id = c.active_child_id
        FROM chained c
        WHERE m.id = c.id
        """
    )
    # Each conversation's active root = its first message.
    op.execute(
        """
        WITH roots AS (
            SELECT DISTINCT ON (conversation_id) conversation_id, id
            FROM messages
            ORDER BY conversation_id, created_at, (role = 'assistant')
        )
        UPDATE conversations c
        SET active_child_id = r.id
        FROM roots r
        WHERE c.id = r.conversation_id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_messages_parent_id", table_name="messages")
    op.drop_constraint("fk_conversations_active_child_id_messages", "conversations", type_="foreignkey")
    op.drop_constraint("fk_messages_active_child_id_messages", "messages", type_="foreignkey")
    op.drop_constraint("fk_messages_parent_id_messages", "messages", type_="foreignkey")
    op.drop_column("conversations", "active_child_id")
    op.drop_column("messages", "active_child_id")
    op.drop_column("messages", "parent_id")
