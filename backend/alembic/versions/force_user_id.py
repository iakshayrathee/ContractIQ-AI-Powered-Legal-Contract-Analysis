"""Force add user_id columns

Revision ID: force_user_id
Revises: c1d2e3f4a5b6
Create Date: 2026-06-07 12:00:00.000000

Force adds user_id columns with safe inspection checks for PostgreSQL.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "force_user_id"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    
    # ── PROJECTS TABLE ───────────────────────────────────────────
    projects_columns = [col["name"] for col in inspector.get_columns("projects")]
    if "user_id" not in projects_columns:
        op.add_column(
            "projects",
            sa.Column("user_id", sa.String(64), nullable=True),
        )
    
    projects_fks = [fk["name"] for fk in inspector.get_foreign_keys("projects")]
    if "fk_projects_user_id" not in projects_fks:
        # Check if fk matches base table to avoid collision
        op.create_foreign_key(
            "fk_projects_user_id",
            "projects",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        
    projects_indexes = [idx["name"] for idx in inspector.get_indexes("projects")]
    if "ix_projects_user_id" not in projects_indexes:
        op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # ── ANALYSES TABLE ───────────────────────────────────────────
    analyses_columns = [col["name"] for col in inspector.get_columns("analyses")]
    if "user_id" not in analyses_columns:
        op.add_column(
            "analyses",
            sa.Column("user_id", sa.String(64), nullable=True),
        )
        
    analyses_fks = [fk["name"] for fk in inspector.get_foreign_keys("analyses")]
    if "fk_analyses_user_id" not in analyses_fks:
        op.create_foreign_key(
            "fk_analyses_user_id",
            "analyses",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        
    analyses_indexes = [idx["name"] for idx in inspector.get_indexes("analyses")]
    if "ix_analyses_user_id" not in analyses_indexes:
        op.create_index("ix_analyses_user_id", "analyses", ["user_id"])


def downgrade() -> None:
    pass
