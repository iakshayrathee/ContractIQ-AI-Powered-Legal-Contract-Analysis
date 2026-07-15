"""add_users_table

Revision ID: c1d2e3f4a5b6
Revises: add_model_registry
Create Date: 2026-06-07 00:00:00.000000

Adds:
  - users table (id, email, hashed_password, created_at)
  - user_id FK column to projects table (nullable, SET NULL on delete)
  - user_id FK column to analyses table (nullable, SET NULL on delete)

Idempotent: uses inspector checks so it is safe to run even when the
backend's create_all() already created some of these objects.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "add_model_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    return inspect(bind).has_table(table_name)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    cols = [c["name"] for c in inspect(bind).get_columns(table_name)]
    return column_name in cols


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    idxs = [i["name"] for i in inspect(bind).get_indexes(table_name)]
    return index_name in idxs


def _fk_exists(bind, table_name: str, fk_name: str) -> bool:
    fks = [f["name"] for f in inspect(bind).get_foreign_keys(table_name)]
    return fk_name in fks


def upgrade() -> None:
    bind = op.get_bind()

    # ── users table ──────────────────────────────────────────────────────────
    if not _table_exists(bind, "users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("email", sa.String(255), unique=True, nullable=False),
            sa.Column("hashed_password", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    if not _index_exists(bind, "users", "ix_users_email"):
        op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ── projects.user_id ─────────────────────────────────────────────────────
    if not _column_exists(bind, "projects", "user_id"):
        op.add_column(
            "projects",
            sa.Column("user_id", sa.String(64), nullable=True),
        )
    if not _fk_exists(bind, "projects", "fk_projects_user_id"):
        op.create_foreign_key(
            "fk_projects_user_id",
            "projects",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists(bind, "projects", "ix_projects_user_id"):
        op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # ── analyses.user_id ─────────────────────────────────────────────────────
    if not _column_exists(bind, "analyses", "user_id"):
        op.add_column(
            "analyses",
            sa.Column("user_id", sa.String(64), nullable=True),
        )
    if not _fk_exists(bind, "analyses", "fk_analyses_user_id"):
        op.create_foreign_key(
            "fk_analyses_user_id",
            "analyses",
            "users",
            ["user_id"],
            ["id"],
            ondelete="SET NULL",
        )
    if not _index_exists(bind, "analyses", "ix_analyses_user_id"):
        op.create_index("ix_analyses_user_id", "analyses", ["user_id"])


def downgrade() -> None:
    bind = op.get_bind()

    if _index_exists(bind, "analyses", "ix_analyses_user_id"):
        op.drop_index("ix_analyses_user_id", table_name="analyses")
    if _fk_exists(bind, "analyses", "fk_analyses_user_id"):
        op.drop_constraint("fk_analyses_user_id", "analyses", type_="foreignkey")
    if _column_exists(bind, "analyses", "user_id"):
        op.drop_column("analyses", "user_id")

    if _index_exists(bind, "projects", "ix_projects_user_id"):
        op.drop_index("ix_projects_user_id", table_name="projects")
    if _fk_exists(bind, "projects", "fk_projects_user_id"):
        op.drop_constraint("fk_projects_user_id", "projects", type_="foreignkey")
    if _column_exists(bind, "projects", "user_id"):
        op.drop_column("projects", "user_id")

    if _index_exists(bind, "users", "ix_users_email"):
        op.drop_index("ix_users_email", table_name="users")
    if _table_exists(bind, "users"):
        op.drop_table("users")
