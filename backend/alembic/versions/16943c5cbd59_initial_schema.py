"""initial_schema

Revision ID: 16943c5cbd59
Revises: 
Create Date: 2026-04-09 15:26:16.834970

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16943c5cbd59'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial tables: projects, query_cache, analyses."""
    op.create_table(
        "projects",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(80), unique=True, nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("collection_name", sa.String(80), unique=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "query_cache",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("cache_key", sa.String(128), unique=True, nullable=False, index=True),
        sa.Column("project_name", sa.String(80), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("chunks_retrieved", sa.Integer(), server_default="0"),
        sa.Column("sources_json", sa.Text(), server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("project_id", sa.String(64), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("analysis_json", sa.Text(), server_default="{}"),
        sa.Column("risk_json", sa.Text(), server_default="{}"),
        sa.Column("summary_json", sa.Text(), server_default="{}"),
        sa.Column("overall_risk_score", sa.Integer(), server_default="0"),
        sa.Column("error", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("analyses")
    op.drop_table("query_cache")
    op.drop_table("projects")
