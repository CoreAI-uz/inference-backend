"""conversations: support anonymous (session-owned) ownership

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

Anonymous chats are now persisted server-side keyed by the session cookie:
user_id becomes nullable, a session_id column is added, and a check ensures one owner
is present. On register, stitch_session re-attributes session_id → user_id.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("conversations", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=True)
    op.add_column("conversations", sa.Column("session_id", sa.String(64), nullable=True))
    op.create_check_constraint(
        "owner_present", "conversations", "user_id IS NOT NULL OR session_id IS NOT NULL"
    )
    op.create_index(
        "ix_conversations_session_id_updated_at", "conversations", ["session_id", "updated_at"]
    )


def downgrade() -> None:
    # Drop anon conversations first so user_id can go back to NOT NULL.
    op.execute("DELETE FROM conversations WHERE user_id IS NULL")
    op.drop_index("ix_conversations_session_id_updated_at", table_name="conversations")
    op.drop_constraint("ck_conversations_owner_present", "conversations", type_="check")
    op.drop_column("conversations", "session_id")
    op.alter_column("conversations", "user_id", existing_type=sa.dialects.postgresql.UUID(), nullable=False)
