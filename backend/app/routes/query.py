import asyncio
import hashlib
import json
import logging
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.auth.dependencies import get_current_user
from app.db.models import QueryCacheRow
from app.routes.projects import save_chat_pair
from app.schemas.requests import QueryRequest
from app.services.project_service import ProjectService
from app.services.query_service import QueryService
from app.services.guardrails import validate_query_input
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter()


def _cache_key(project_id: str, question: str, k: int | None, doc_count: int) -> str:
    """
    Generate cache key for query results.
    When k is None (adaptive mode), use 'adaptive' in the key to distinguish from fixed-k queries.
    """
    k_str = "adaptive" if k is None else str(k)
    raw = f"{project_id}|{question.strip().lower()}|{k_str}|{doc_count}"
    return hashlib.sha256(raw.encode()).hexdigest()[:64]


@router.post("/query", summary="Query a project's documents (SSE streaming)")
@limiter.limit("20/minute")
async def query_documents(
    request: Request,
    body: QueryRequest,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """
    Ask a natural-language question about documents ingested into a project.

    Returns a Server-Sent Events stream:
      - event: sources  → JSON array of retrieved source chunks
      - event: token    → each generated token
      - event: done     → final empty event
      - event: error    → error message

    Responses are cached by (project_name, question, k, doc_count) hash.
    """
    project_service: ProjectService = request.app.state.project_service
    query_service: QueryService = request.app.state.query_service
    vs = request.app.state.vector_store_service
    settings = request.app.state.settings
    session_factory = request.app.state.session_factory

    project = await project_service.get_project(body.project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{body.project_name}' not found.",
        )

    # 1. Input Guardrails
    guardrail_result = validate_query_input(body.question)
    if not guardrail_result.passed:
        async def error_stream():
            sources_payload = json.dumps({
                "type": "sources",
                "question": body.question,
                "project_name": body.project_name,
                "chunks_retrieved": 0,
                "sources": [],
            })
            yield f"data: {sources_payload}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'token': guardrail_result.reason})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Use adaptive retrieval when k is None (default behavior)
    # Otherwise use the provided k value for backward compatibility
    k = body.k
    doc_count = vs.document_count(project.collection_name)
    key = _cache_key(project.id, body.question, k, doc_count)

    # Check cache
    async with session_factory() as session:
        result = await session.execute(
            select(QueryCacheRow).where(QueryCacheRow.cache_key == key)
        )
        cached = result.scalar_one_or_none()

    if cached:
        logger.info(
            "Cache HIT for key=%s (k=%s)", 
            key[:12], 
            "adaptive" if k is None else str(k)
        )

        async def cached_stream():
            sources_payload = json.dumps({
                "type": "sources",
                "question": cached.question,
                "project_name": project.name,
                "chunks_retrieved": cached.chunks_retrieved,
                "sources": json.loads(cached.sources_json),
            })
            yield f"data: {sources_payload}\n\n"
            yield f"data: {json.dumps({'type': 'token', 'token': cached.answer})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            # Persist to chat history (fire-and-forget, non-blocking)
            asyncio.ensure_future(
                save_chat_pair(
                    session_factory,
                    project.name,
                    cached.question,
                    cached.answer,
                    cached.sources_json,
                    user_id=user_id,
                )
            )

        return StreamingResponse(
            cached_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def event_stream():
        collected_tokens: list[str] = []
        source_chunks_data = []
        chunks_retrieved_count = 0
        try:
            # Phase 1: Retrieve (blocking → run in executor)
            loop = asyncio.get_event_loop()
            chunks, intent = await loop.run_in_executor(
                None,
                partial(query_service.retrieve, body.question, k, project.collection_name),
            )

            # Send sources upfront so the frontend can render them immediately
            source_chunks_data = query_service._extract_sources(chunks)
            chunks_retrieved_count = len(chunks)
            sources_payload = json.dumps({
                "type": "sources",
                "question": body.question,
                "project_name": body.project_name,
                "chunks_retrieved": chunks_retrieved_count,
                "sources": source_chunks_data,
            })
            yield f"data: {sources_payload}\n\n"

            # Phase 2: Stream generation tokens
            async for token in query_service.stream_answer(chunks, body.question, intent):
                collected_tokens.append(token)
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Cache the result
            full_answer = "".join(collected_tokens)
            try:
                async with session_factory() as session:
                    cache_row = QueryCacheRow(
                        cache_key=key,
                        project_id=project.id,
                        question=body.question,
                        answer=full_answer,
                        chunks_retrieved=chunks_retrieved_count,
                        sources_json=json.dumps(source_chunks_data),
                    )
                    session.add(cache_row)
                    await session.commit()
                    logger.info("Cached query result: key=%s", key[:12])
            except Exception as cache_err:
                logger.warning("Failed to cache query: %s", cache_err)

            # Persist to chat history
            asyncio.ensure_future(
                save_chat_pair(
                    session_factory,
                    body.project_name,
                    body.question,
                    full_answer,
                    json.dumps(source_chunks_data),
                    user_id=user_id,
                )
            )

        except RuntimeError as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception as exc:
            logger.error("SSE stream failed: %s", exc, exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'detail': f'Query failed: {exc}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
