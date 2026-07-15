"""add_chat_messages_table

Revision ID: b5c92f3e1a07
Revises: 7e3a1b2c4d8f
Create Date: 2026-06-02 00:00:00.000000

Creates the chat_messages table that persists per-project Q&A conversation
history in Postgres, replacing the previous client-side localStorage approach.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b5c92f3e1a07"
down_revision: Union[str, None] = "7e3a1b2c4d8f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            sa.String(64),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=True, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_chat_messages_project_id",
        "chat_messages",
        ["project_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_chat_messages_project_id", table_name="chat_messages")
    op.drop_table("chat_messages")
