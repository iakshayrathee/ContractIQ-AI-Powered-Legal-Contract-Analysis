"""add_model_registry_table

Revision ID: add_model_registry
Revises: b5c92f3e1a07
Create Date: 2026-06-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_model_registry'
down_revision: Union[str, None] = 'b5c92f3e1a07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create model_registry table for fine-tuning model management."""
    op.create_table(
        "model_registry",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("model_id", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("base_model", sa.String(100), nullable=False),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("training_file_id", sa.String(100), nullable=True),
        sa.Column("val_file_id", sa.String(100), nullable=True),
        sa.Column("dataset_hash", sa.String(64), nullable=True, index=True),
        sa.Column("n_examples", sa.Integer(), nullable=True),
        sa.Column("n_epochs", sa.Integer(), nullable=True),
        sa.Column("train_loss", sa.Float(), nullable=True),
        sa.Column("val_loss", sa.Float(), nullable=True),
        sa.Column("training_tokens", sa.Integer(), nullable=True),
        sa.Column("training_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("clause_f1", sa.Float(), nullable=True),
        sa.Column("clause_precision", sa.Float(), nullable=True),
        sa.Column("clause_recall", sa.Float(), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("previous_model_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop model_registry table."""
    op.drop_table("model_registry")
