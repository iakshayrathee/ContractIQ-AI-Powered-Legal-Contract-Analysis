"""add_document_hash_to_analyses

Revision ID: a3f81c2de905
Revises: 16943c5cbd59
Create Date: 2026-04-10 00:00:00.000000

Adds a nullable document_hash column (VARCHAR 64) to the analyses table.
The hash is a SHA-256 digest of sorted chunk raw_text content, computed
before each analysis run to short-circuit re-analysis when the document
has not changed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a3f81c2de905"
down_revision: Union[str, None] = "16943c5cbd59"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("document_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_analyses_document_hash",
        "analyses",
        ["document_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analyses_document_hash", table_name="analyses")
    op.drop_column("analyses", "document_hash")
