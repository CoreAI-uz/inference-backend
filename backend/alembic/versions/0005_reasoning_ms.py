"""messages: record reasoning duration (ms)

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-16

Wall-clock time the model spent reasoning (first reasoning token → </think>), so the UI
can show "Thought for N seconds" on reload, not just live.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("reasoning_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "reasoning_ms")
