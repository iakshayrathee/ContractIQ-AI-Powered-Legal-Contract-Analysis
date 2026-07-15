"""
Shared test fixtures for ContractIQ backend.

Uses an in-memory SQLite database (via aiosqlite) so tests run
without PostgreSQL / Qdrant infrastructure.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings
from app.db.models import Base, ProjectRow, AnalysisRow, QueryCacheRow
from app.services.job_service import JobService
from app.services.project_service import ProjectService


# ---------------------------------------------------------------------------
# Settings override — no external services needed
# ---------------------------------------------------------------------------

def _test_settings() -> Settings:
    """Settings that don't touch real APIs."""
    return Settings(
        openai_api_key="sk-test-fake-key",
        qdrant_url="http://localhost:6333",
        database_url="sqlite+aiosqlite:///:memory:",
        langfuse_enabled=False,
        retrieval_top_k=3,
        jwt_secret_key="test-jwt-secret-key-for-unit-tests-only",
        jwt_expire_minutes=60,
    )


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def db_engine():
    """Create an in-memory async SQLite engine with all tables."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    
    # Enable SQLite foreign key support for cascade deletes
    from sqlalchemy import event
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Seed default test users to satisfy foreign key constraints in endpoint/authorization tests
        from sqlalchemy import text
        await conn.execute(
            text("INSERT INTO users (id, email, hashed_password, created_at) VALUES ('test-user-id', 'test-user@example.com', 'dummy', CURRENT_TIMESTAMP)")
        )
        await conn.execute(
            text("INSERT INTO users (id, email, hashed_password, created_at) VALUES ('user-a', 'user-a@example.com', 'dummy', CURRENT_TIMESTAMP)")
        )
        await conn.execute(
            text("INSERT INTO users (id, email, hashed_password, created_at) VALUES ('user-b', 'user-b@example.com', 'dummy', CURRENT_TIMESTAMP)")
        )
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(db_engine) -> async_sessionmaker[AsyncSession]:
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    import app.db.database as db_mod
    db_mod._session_factory = factory
    return factory


@pytest.fixture
async def db_session(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Service fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def settings() -> Settings:
    return _test_settings()


@pytest.fixture
def project_service(session_factory) -> ProjectService:
    return ProjectService(session_factory)


@pytest.fixture
def job_service() -> JobService:
    return JobService()


@pytest.fixture
def mock_vector_store():
    """A mock VectorStoreService that doesn't touch Qdrant."""
    vs = MagicMock()
    vs.is_loaded.return_value = True
    vs.document_count.return_value = 5
    vs.list_chunks.return_value = [
        {
            "chunk_id": "chunk-1",
            "content": "This is a test chunk about confidentiality.",
            "content_types": ["text"],
            "raw_text": "This is a test chunk about confidentiality.",
            "tables_html": [],
            "images_base64": [],
            "source_file": "contract.pdf",
        }
    ]
    vs.similarity_search.return_value = []
    vs.delete_collection.return_value = None
    vs.create_or_replace.return_value = None
    vs.load.return_value = None
    return vs


@pytest.fixture
def mock_query_service():
    """A mock QueryService that doesn't call OpenAI."""
    qs = MagicMock()
    qs.retrieve.return_value = []
    qs._extract_sources.return_value = []

    async def fake_stream(chunks, question):
        yield "Test "
        yield "answer."

    qs.stream_answer = fake_stream
    return qs


@pytest.fixture
def mock_ingestion_service():
    svc = MagicMock()
    return svc


@pytest.fixture
def mock_contract_analysis_service():
    cas = MagicMock()
    cas.get_analysis = AsyncMock(return_value=None)
    cas.prepare_analysis = AsyncMock(return_value=("analysis-test-1", "running"))
    cas.run_analysis_pipeline_from_row = AsyncMock()
    cas.run_full_analysis = AsyncMock()
    return cas


# ---------------------------------------------------------------------------
# App + client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def app(
    settings,
    session_factory,
    project_service,
    job_service,
    mock_vector_store,
    mock_query_service,
    mock_ingestion_service,
    mock_contract_analysis_service,
):
    """Create a FastAPI app with test overrides — no real DB/Qdrant/OpenAI.

    We build the app WITHOUT lifespan so it doesn't try to connect to real
    PostgreSQL or Qdrant.  Instead, we attach all test fixtures to app.state
    directly, matching what the real lifespan would do.
    """
    from contextlib import asynccontextmanager

    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse

    from app.routes import contracts, dashboard, health, ingestion, jobs, projects, query
    from app.auth import router as auth_router
    from app.schemas.responses import ErrorResponse

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        yield

    test_app = FastAPI(lifespan=_noop_lifespan)

    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register the same routers as create_app()
    test_app.include_router(auth_router.router)
    test_app.include_router(health.router, tags=["Health"])
    test_app.include_router(projects.router)
    test_app.include_router(jobs.router)
    test_app.include_router(ingestion.router, tags=["Ingestion"])
    test_app.include_router(query.router, tags=["Query"])
    test_app.include_router(contracts.router)
    test_app.include_router(dashboard.router)

    # Exception handlers
    @test_app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content=ErrorResponse(detail=str(exc)).model_dump())

    @test_app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(status_code=503, content=ErrorResponse(detail=str(exc)).model_dump())

    # Inject test fixtures into app.state (mirrors real lifespan)
    test_app.state.settings = settings
    test_app.state.session_factory = session_factory
    test_app.state.project_service = project_service
    test_app.state.job_service = job_service
    test_app.state.vector_store_service = mock_vector_store
    test_app.state.query_service = mock_query_service
    test_app.state.ingestion_service = mock_ingestion_service
    test_app.state.contract_analysis_service = mock_contract_analysis_service
    test_app.state.ingestion_lock = asyncio.Lock()

    # Override get_current_user to bypass authentication in existing unit tests
    from app.auth.dependencies import get_current_user
    test_app.dependency_overrides[get_current_user] = lambda: "test-user-id"

    return test_app


@pytest.fixture
async def async_client(app) -> AsyncGenerator[AsyncClient, None]:
    """Alias for 'client' — used by auth tests."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def client(app) -> AsyncGenerator[AsyncClient, None]:
    """HTTPX async client wired to the test app (no real HTTP)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Seed data helpers
# ---------------------------------------------------------------------------

@pytest.fixture
async def seed_project(session_factory) -> ProjectRow:
    """Insert a test project into the DB."""
    async with session_factory() as session:
        row = ProjectRow(
            id="proj-test-1",
            name="test-project",
            description="A test project",
            collection_name="test-project",
            user_id="test-user-id",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


@pytest.fixture
async def seed_analysis(session_factory, seed_project) -> AnalysisRow:
    """Insert a completed analysis for the test project."""
    analysis = {
        "metadata": {
            "contract_type": "NDA",
            "parties": ["Acme Corp", "Beta LLC"],
            "effective_date": "2024-01-01",
            "expiration_date": "2025-01-01",
            "governing_law": "Delaware",
            "jurisdiction": "United States",
        },
        "clauses": [
            {
                "clause_type": "confidentiality",
                "title": "Confidentiality Obligations",
                "text": "Both parties agree to maintain confidentiality.",
                "section_reference": "Section 2",
                "obligations": [
                    {"party": "Acme Corp", "description": "Must not disclose", "type": "must_not"}
                ],
            }
        ],
        "key_dates": ["2024-01-01", "2025-01-01"],
        "summary": "This is an NDA between Acme and Beta.",
    }
    risk = {
        "overall_score": 35,
        "risk_level": "medium",
        "items": [
            {
                "category": "missing_clause",
                "severity": "medium",
                "title": "No force majeure",
                "description": "Contract lacks force majeure clause.",
                "recommendation": "Add force majeure clause.",
            }
        ],
        "missing_clauses": ["force_majeure"],
        "summary": "Moderate risk due to missing clauses.",
    }
    summary = {
        "executive_summary": "Standard NDA with moderate risk.",
        "what_this_does": "Protects confidential information.",
        "obligations_by_party": {"Acme Corp": ["Must not disclose"], "Beta LLC": ["Must not disclose"]},
        "key_dates": ["Effective: 2024-01-01", "Expires: 2025-01-01"],
        "watch_out_for": ["No force majeure clause"],
        "action_items": ["Add force majeure clause"],
    }
    async with session_factory() as session:
        row = AnalysisRow(
            id="analysis-test-1",
            project_id=seed_project.id,
            status="completed",
            analysis_json=json.dumps(analysis),
            risk_json=json.dumps(risk),
            summary_json=json.dumps(summary),
            overall_risk_score=35,
            completed_at=datetime.now(timezone.utc),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row
