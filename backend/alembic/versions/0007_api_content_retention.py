"""Short-lived API request and response content

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_content_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column("request_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("data_policy", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["api_key_id"], ["api_keys.id"],
            name="fk_api_content_records_api_key_id_api_keys", ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_api_content_records_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_content_records"),
        sa.UniqueConstraint("request_id", name="uq_api_content_records_request_id"),
    )
    op.create_index(
        "ix_api_content_records_user_id_created_at",
        "api_content_records",
        ["user_id", "created_at"],
    )
    op.create_index(
        "ix_api_content_records_expires_at",
        "api_content_records",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_content_records_expires_at", table_name="api_content_records")
    op.drop_index(
        "ix_api_content_records_user_id_created_at", table_name="api_content_records"
    )
    op.drop_table("api_content_records")
