import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import ProjectRow, ChatMessageRow

logger = logging.getLogger(__name__)


@dataclass
class Project:
    id: str
    name: str
    description: str
    collection_name: str
    created_at: str


class ProjectService:
    """
    Persists project metadata to PostgreSQL via SQLAlchemy async.
    Each project maps to a uniquely named Qdrant collection.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def list_projects(self, user_id: str | None = None) -> list[Project]:
        async with self._session_factory() as session:
            query = select(ProjectRow)
            if user_id is not None:
                # Only return projects owned by this user (no NULL user_id fallback)
                query = query.where(ProjectRow.user_id == user_id)
            result = await session.execute(
                query.order_by(ProjectRow.created_at.desc())
            )
            rows = result.scalars().all()
            return [self._to_dataclass(r) for r in rows]

    async def create_project(self, name: str, description: str = "", user_id: str | None = None) -> Project:
        async with self._session_factory() as session:
            # Check uniqueness scoped to the user
            existing = await session.execute(
                select(ProjectRow).where(
                    ProjectRow.name.ilike(name),
                    ProjectRow.user_id == user_id
                )
            )
            if existing.scalar_one_or_none() is not None:
                raise ValueError(f"A project named '{name}' already exists.")

            collection_name = self._slugify(name)

            # Ensure collection_name is also unique
            coll_check = await session.execute(
                select(ProjectRow).where(ProjectRow.collection_name == collection_name)
            )
            base = collection_name
            counter = 1
            while coll_check.scalar_one_or_none() is not None:
                collection_name = f"{base}-{counter}"
                counter += 1
                coll_check = await session.execute(
                    select(ProjectRow).where(ProjectRow.collection_name == collection_name)
                )

            row = ProjectRow(
                name=name,
                description=description,
                collection_name=collection_name,
                user_id=user_id,
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)

            project = self._to_dataclass(row)
            logger.info("Created project '%s' (user: %s) → collection '%s'.", name, user_id, collection_name)
            return project

    async def get_project(self, name: str, user_id: str | None = None) -> Project | None:
        async with self._session_factory() as session:
            query = select(ProjectRow).where(ProjectRow.name.ilike(name))
            if user_id is not None:
                # Only return project owned by this user (no NULL user_id fallback)
                query = query.where(ProjectRow.user_id == user_id)
            result = await session.execute(query)
            row = result.scalar_one_or_none()
            return self._to_dataclass(row) if row else None

    async def delete_project(self, name: str, user_id: str | None = None) -> None:
        async with self._session_factory() as session:
            query = select(ProjectRow).where(ProjectRow.name.ilike(name))
            if user_id is not None:
                # Only delete project owned by this user (no NULL user_id fallback)
                query = query.where(ProjectRow.user_id == user_id)
            result = await session.execute(query)
            row = result.scalar_one_or_none()
            if row is None:
                raise ValueError(f"Project '{name}' not found.")
            await session.delete(row)
            await session.commit()
            logger.info("Deleted project '%s' (user: %s).", name, user_id)

    async def get_chat_history(self, project_name: str, user_id: str | None = None) -> list[ChatMessageRow]:
        async with self._session_factory() as session:
            query = select(ChatMessageRow).join(ProjectRow).where(ProjectRow.name.ilike(project_name))
            if user_id is not None:
                # Only return chat history for projects owned by this user (no NULL user_id fallback)
                query = query.where(ProjectRow.user_id == user_id)
            result = await session.execute(
                query.order_by(ChatMessageRow.created_at.asc())
            )
            return list(result.scalars().all())

    async def clear_chat_history(self, project_name: str, user_id: str | None = None) -> None:
        async with self._session_factory() as session:
            query = select(ProjectRow.id).where(ProjectRow.name.ilike(project_name))
            if user_id is not None:
                # Only clear chat history for projects owned by this user (no NULL user_id fallback)
                query = query.where(ProjectRow.user_id == user_id)
            project_result = await session.execute(query)
            project_id = project_result.scalar_one_or_none()
            if not project_id:
                raise ValueError(f"Project '{project_name}' not found.")
            await session.execute(
                delete(ChatMessageRow).where(ChatMessageRow.project_id == project_id)
            )
            await session.commit()
            logger.info("Cleared chat history for project '%s' (user: %s).", project_name, user_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dataclass(row: ProjectRow) -> Project:
        return Project(
            id=row.id,
            name=row.name,
            description=row.description or "",
            collection_name=row.collection_name,
            created_at=row.created_at.isoformat() if isinstance(row.created_at, datetime) else str(row.created_at),
        )

    @staticmethod
    def _slugify(name: str) -> str:
        """Convert a project name to a safe Qdrant collection name."""
        slug = name.lower().strip()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s]+", "-", slug)
        slug = re.sub(r"-+", "-", slug).strip("-")
        # Qdrant collection names must be 3-63 chars
        slug = slug[:63] or "project"
        if len(slug) < 3:
            slug = slug.ljust(3, "0")
        return slug
