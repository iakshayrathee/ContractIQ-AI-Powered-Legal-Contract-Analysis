"""scope project uniqueness per user

Revision ID: scope_project_uniqueness
Revises: force_user_id
Create Date: 2026-07-07 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = "scope_project_uniqueness"
down_revision: Union[str, None] = "force_user_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # 1. Drop existing unique constraints or indexes on projects.name
    # Postgres names it projects_name_key, but let's find it dynamically
    uq_constraints = inspector.get_unique_constraints("projects")
    for uq in uq_constraints:
        if "name" in uq["column_names"]:
            op.drop_constraint(uq["name"], "projects", type_="unique")

    indexes = inspector.get_indexes("projects")
    for idx in indexes:
        if idx["unique"] and idx["column_names"] == ["name"]:
            op.drop_index(idx["name"], table_name="projects")

    # 2. Drop existing foreign keys referencing projects.name from query_cache if any
    fks = inspector.get_foreign_keys("query_cache")
    for fk in fks:
        if "project_name" in fk["constrained_columns"]:
            op.drop_constraint(fk["name"], "query_cache", type_="foreignkey")

    # 3. Add project_id column to query_cache (initially nullable)
    op.add_column("query_cache", sa.Column("project_id", sa.String(64), nullable=True))

    # 4. Populate project_id in query_cache using projects.id where names match
    op.execute(
        "UPDATE query_cache SET project_id = projects.id "
        "FROM projects WHERE projects.name = query_cache.project_name"
    )

    # For any rows where project_id couldn't be matched (e.g. orphan caches),
    # let's delete them to avoid NOT NULL violation, or update with dummy if empty
    op.execute("DELETE FROM query_cache WHERE project_id IS NULL")

    # 5. Make project_id NOT NULL
    op.alter_column("query_cache", "project_id", nullable=False)

    # 6. Drop the old project_name column
    op.drop_column("query_cache", "project_name")

    # 7. Create composite unique constraint on projects(user_id, name)
    op.create_unique_constraint(
        "uq_projects_user_id_name",
        "projects",
        ["user_id", "name"],
    )

    # 8. Create foreign key on query_cache.project_id
    op.create_foreign_key(
        "fk_query_cache_project_id",
        "query_cache",
        "projects",
        ["project_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    # 1. Drop composite unique constraint on projects(user_id, name)
    op.drop_constraint("uq_projects_user_id_name", "projects", type_="unique")

    # 2. Drop foreign key on query_cache.project_id
    fks = inspector.get_foreign_keys("query_cache")
    for fk in fks:
        if "project_id" in fk["constrained_columns"]:
            op.drop_constraint(fk["name"], "query_cache", type_="foreignkey")

    # 3. Add project_name column back to query_cache (initially nullable)
    op.add_column("query_cache", sa.Column("project_name", sa.String(80), nullable=True))

    # 4. Populate project_name in query_cache from projects.name where ids match
    op.execute(
        "UPDATE query_cache SET project_name = projects.name "
        "FROM projects WHERE projects.id = query_cache.project_id"
    )

    # Delete any orphaned cache rows
    op.execute("DELETE FROM query_cache WHERE project_name IS NULL")

    # 5. Make project_name NOT NULL
    op.alter_column("query_cache", "project_name", nullable=False)

    # 6. Drop project_id column
    op.drop_column("query_cache", "project_id")

    # 7. Add unique constraint back to projects.name
    op.create_unique_constraint(
        "projects_name_key",
        "projects",
        ["name"],
    )

    # 8. Create foreign key back on query_cache.project_name referencing projects.name
    op.create_foreign_key(
        "fk_query_cache_project_name",
        "query_cache",
        "projects",
        ["project_name"],
        ["name"],
        ondelete="CASCADE",
    )
