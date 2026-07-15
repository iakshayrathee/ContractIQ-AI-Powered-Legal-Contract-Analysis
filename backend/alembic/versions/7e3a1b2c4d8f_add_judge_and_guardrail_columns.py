"""add_judge_and_guardrail_columns

Revision ID: 7e3a1b2c4d8f
Revises: a3f81c2de905
Create Date: 2026-04-25 00:00:00.000000

Adds judge/quality tracking columns to the analyses table:
  - judge_json: Full LLM-as-Judge evaluation output
  - guardrail_warnings_json: Output guardrail validation results
  - quality_score: Normalized judge score (0.0-1.0)
  - flagged_for_review: True if analysis had quality issues requiring human review
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7e3a1b2c4d8f"
down_revision: Union[str, None] = "a3f81c2de905"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("judge_json", sa.Text(), server_default="{}", nullable=False),
    )
    op.add_column(
        "analyses",
        sa.Column("guardrail_warnings_json", sa.Text(), server_default="{}", nullable=False),
    )
    op.add_column(
        "analyses",
        sa.Column("quality_score", sa.Float(), server_default="0.0", nullable=False),
    )
    op.add_column(
        "analyses",
        sa.Column("flagged_for_review", sa.Boolean(), server_default="false", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("analyses", "flagged_for_review")
    op.drop_column("analyses", "quality_score")
    op.drop_column("analyses", "guardrail_warnings_json")
    op.drop_column("analyses", "judge_json")
