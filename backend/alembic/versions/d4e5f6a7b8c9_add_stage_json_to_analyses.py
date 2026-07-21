"""add stage_json and partial results to analyses

Revision ID: d4e5f6a7b8c9
Revises: add_model_registry_table
Create Date: 2026-07-21

Adds:
- analyses.stage_json     — pipeline stage indicator (WS-2.2)
- analyses.analysis_json  — already exists; ensure column is nullable so partial results work
"""

from alembic import op
import sqlalchemy as sa

revision = "d4e5f6a7b8c9"
down_revision = "scope_project_uniqueness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add stage_json column for pipeline progress tracking
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.add_column(
            sa.Column("stage_json", sa.Text(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("analyses") as batch_op:
        batch_op.drop_column("stage_json")
