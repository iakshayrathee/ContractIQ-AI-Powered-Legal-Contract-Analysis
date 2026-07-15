import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

import structlog

from app.config import get_settings
from app.core.logging import configure_structlog
from app.middleware.request_id import RequestIDMiddleware
from app.utils.rate_limit import limiter
from app.db.database import close_db, get_session_factory, init_db
from app.routes import health, ingestion, query
from app.routes import contracts, dashboard, jobs, projects
from app.routes import analysis as analysis_routes
from app.auth import router as auth_router
from app.schemas.responses import ErrorResponse
from app.services.contract_analysis_service import ContractAnalysisService
from app.services.ingestion_service import IngestionService
from app.services.job_service import JobService
from app.services.project_service import ProjectService
from app.services.query_service import QueryService
from app.services.vector_store_service import VectorStoreService
from app.utils.langfuse_utils import flush_langfuse, init_langfuse



@asynccontextmanager
async def lifespan(app):
    settings = get_settings()
    log_format = "console" if settings.log_level.upper() == "DEBUG" else "json"
    configure_structlog(settings.log_level, log_format)
    logger = structlog.get_logger()
    logger.info("startup", title=settings.app_title, version=settings.app_version)

    # --- Database ---
    await init_db(settings)
    session_factory = get_session_factory()

    # --- Services ---
    vector_store_service = VectorStoreService(settings)
    ingestion_service = IngestionService(settings)
    query_service = QueryService(settings, vector_store_service)
    project_service = ProjectService(session_factory)
    job_service = JobService()
    contract_analysis_service = ContractAnalysisService(settings, vector_store_service, session_factory)

    vector_store_service.load()

    # --- Langfuse ---
    init_langfuse(settings)

    app.state.settings = settings
    app.state.vector_store_service = vector_store_service
    app.state.ingestion_service = ingestion_service
    app.state.query_service = query_service
    app.state.project_service = project_service
    app.state.job_service = job_service
    app.state.contract_analysis_service = contract_analysis_service
    app.state.session_factory = session_factory
    app.state.ingestion_lock = asyncio.Lock()

    logger.info("Application startup complete.")
    yield

    # --- Shutdown ---
    flush_langfuse()
    await close_db()
    logger.info("Application shut down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        description=(
            "ContractIQ API — AI-powered legal contract analysis. "
            "Ingest contracts, extract clauses, assess risks, and ask questions "
            "using GPT-4o vision + Qdrant vector search."
        ),
        lifespan=lifespan,
    )

    # --- Rate limiting ---
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # --- CORS (configurable via env) ---
    cors_origins = [origin.strip() for origin in settings.cors_origins.split(",")]
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods.split(",") if "," in settings.cors_allow_methods else ["*"],
        allow_headers=settings.cors_allow_headers.split(",") if "," in settings.cors_allow_headers else ["*"],
    )

    # --- Routers ---
    app.include_router(auth_router.router)
    app.include_router(health.router, tags=["Health"])
    app.include_router(projects.router)
    app.include_router(jobs.router)
    app.include_router(ingestion.router, tags=["Ingestion"])
    app.include_router(query.router, tags=["Query"])
    app.include_router(analysis_routes.router)
    app.include_router(contracts.router)
    app.include_router(dashboard.router)
    from app.routes import finetuning
    app.include_router(finetuning.router)

    # --- Global exception handlers ---

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=ErrorResponse(detail=str(exc)).model_dump(),
        )

    @app.exception_handler(RuntimeError)
    async def runtime_error_handler(request: Request, exc: RuntimeError) -> JSONResponse:
        return JSONResponse(
            status_code=503,
            content=ErrorResponse(detail=str(exc)).model_dump(),
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logging.getLogger(__name__).error(
            "Unhandled exception on %s %s: %s",
            request.method,
            request.url.path,
            exc,
            exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(detail="An unexpected internal error occurred.").model_dump(),
        )

    return app


app = create_app()
