"""messages: separate reasoning (chain-of-thought) column

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-16

Reasoning is stored apart from ``content`` so it can be shown collapsibly and is never
included in the context assembled for later turns (build_lineage uses ``content`` only).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("reasoning", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("messages", "reasoning")
