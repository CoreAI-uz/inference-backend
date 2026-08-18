"""API keys, consent history, and enriched usage ledger

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("key_prefix", sa.String(32), nullable=False),
        sa.Column("secret_digest", sa.String(64), nullable=False),
        sa.Column("last_four", sa.String(4), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_api_keys_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("key_prefix", name="uq_api_keys_key_prefix"),
    )
    op.create_index("ix_api_keys_user_id_revoked_at", "api_keys", ["user_id", "revoked_at"])

    op.create_table(
        "consent_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("policy_version", sa.String(32), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("locale", sa.String(5), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("action IN ('grant', 'withdraw')", name="ck_consent_events_valid_action"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_consent_events_user_id_users", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_consent_events"),
    )
    op.create_index(
        "ix_consent_events_user_scope_created_at",
        "consent_events",
        ["user_id", "scope", "created_at"],
    )

    op.add_column(
        "usage_events", sa.Column("source", sa.String(16), server_default="web", nullable=False)
    )
    op.add_column(
        "usage_events",
        sa.Column("cached_input_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "usage_events",
        sa.Column("reasoning_tokens", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "usage_events", sa.Column("api_key_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("usage_events", sa.Column("request_id", sa.String(64), nullable=True))
    op.add_column("usage_events", sa.Column("latency_ms", sa.Integer(), nullable=True))
    op.add_column("usage_events", sa.Column("status_code", sa.SmallInteger(), nullable=True))
    op.add_column("usage_events", sa.Column("data_policy", sa.String(32), nullable=True))
    op.create_foreign_key(
        "fk_usage_events_api_key_id_api_keys",
        "usage_events",
        "api_keys",
        ["api_key_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_usage_events_api_key_id_created_at", "usage_events", ["api_key_id", "created_at"]
    )
    op.create_index("ix_usage_events_request_id", "usage_events", ["request_id"])


def downgrade() -> None:
    op.drop_index("ix_usage_events_request_id", table_name="usage_events")
    op.drop_index("ix_usage_events_api_key_id_created_at", table_name="usage_events")
    op.drop_constraint(
        "fk_usage_events_api_key_id_api_keys", "usage_events", type_="foreignkey"
    )
    for column in (
        "data_policy",
        "status_code",
        "latency_ms",
        "request_id",
        "api_key_id",
        "reasoning_tokens",
        "cached_input_tokens",
        "source",
    ):
        op.drop_column("usage_events", column)

    op.drop_index("ix_consent_events_user_scope_created_at", table_name="consent_events")
    op.drop_table("consent_events")
    op.drop_index("ix_api_keys_user_id_revoked_at", table_name="api_keys")
    op.drop_table("api_keys")
