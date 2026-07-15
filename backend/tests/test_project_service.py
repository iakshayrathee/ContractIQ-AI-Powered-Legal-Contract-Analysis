"""Unit tests for ProjectService (no HTTP, pure service layer)."""

import pytest

from app.services.project_service import ProjectService


class TestProjectService:
    async def test_create_and_get(self, project_service: ProjectService):
        project = await project_service.create_project("Alpha Contract", "desc")
        assert project.name == "Alpha Contract"
        assert project.collection_name == "alpha-contract"

        fetched = await project_service.get_project("Alpha Contract")
        assert fetched is not None
        assert fetched.name == "Alpha Contract"

    async def test_create_duplicate_raises(self, project_service: ProjectService):
        await project_service.create_project("dup")
        with pytest.raises(ValueError, match="already exists"):
            await project_service.create_project("dup")

    async def test_case_insensitive_lookup(self, project_service: ProjectService):
        await project_service.create_project("My Project")
        fetched = await project_service.get_project("my project")
        assert fetched is not None

    async def test_list_projects(self, project_service: ProjectService):
        await project_service.create_project("A")
        await project_service.create_project("B")
        projects = await project_service.list_projects()
        names = [p.name for p in projects]
        assert "A" in names
        assert "B" in names

    async def test_delete_project(self, project_service: ProjectService):
        await project_service.create_project("to-delete")
        await project_service.delete_project("to-delete")
        assert await project_service.get_project("to-delete") is None

    async def test_delete_nonexistent_raises(self, project_service: ProjectService):
        with pytest.raises(ValueError, match="not found"):
            await project_service.delete_project("ghost")

    async def test_slugify_special_chars(self, project_service: ProjectService):
        project = await project_service.create_project("My Contract! (2024)")
        # Should strip special chars, keep alphanumeric + hyphens
        assert project.collection_name.isascii()
        assert " " not in project.collection_name

    async def test_get_nonexistent_returns_none(self, project_service: ProjectService):
        assert await project_service.get_project("nope") is None
