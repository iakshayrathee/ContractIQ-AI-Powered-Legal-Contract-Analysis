"""
app/routes/analysis.py
=======================
Streaming clause analysis endpoint.

POST /analysis/stream
---------------------
Accepts {project_name, question} and streams GPT-4o tokens as SSE.

SSE event format (same protocol as /query for frontend consistency):
  data: {"type": "sources", "sources": [...], "chunks_retrieved": N}
  data: {"type": "token",   "token": "..."}
  data: {"type": "done"}
  data: {"type": "error",  "detail": "..."}

This endpoint is auth-protected via Depends(get_current_user).
"""

import asyncio
import json
import logging
from functools import partial

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.services.project_service import ProjectService
from app.services.query_service import QueryService
from app.utils.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Analysis"])


class AnalysisStreamRequest(BaseModel):
    project_name: str
    question: str
    k: int | None = None


@router.post(
    "/analysis/stream",
    summary="Stream clause analysis answer as SSE tokens",
)
@limiter.limit("20/minute")
async def stream_analysis(
    request: Request,
    body: AnalysisStreamRequest,
    user_id: str = Depends(get_current_user),
) -> StreamingResponse:
    """
    Retrieve relevant contract chunks for `question` then stream the LLM answer
    token-by-token via Server-Sent Events.

    Frontend should consume this with `fetch` + `ReadableStream` (same as /query).

    Response events (JSON, prefixed with `data: `):
      - sources: {type, sources[], chunks_retrieved}
      - token:   {type, token}
      - done:    {type}
      - error:   {type, detail}
    """
    project_service: ProjectService = request.app.state.project_service
    query_service: QueryService = request.app.state.query_service
    settings = request.app.state.settings

    project = await project_service.get_project(body.project_name, user_id=user_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project '{body.project_name}' not found.",
        )

    k = body.k if body.k is not None else settings.retrieval_top_k

    async def event_stream():
        try:
            # Phase 1: Retrieve relevant chunks (blocking I/O → thread executor)
            loop = asyncio.get_event_loop()
            chunks = await loop.run_in_executor(
                None,
                partial(query_service.retrieve, body.question, k, project.collection_name),
            )

            # Emit sources so the frontend can render citations immediately
            source_chunks = query_service._extract_sources(chunks)
            sources_payload = json.dumps({
                "type": "sources",
                "project_name": body.project_name,
                "question": body.question,
                "chunks_retrieved": len(chunks),
                "sources": source_chunks,
            })
            yield f"data: {sources_payload}\n\n"

            # Phase 2: Stream LLM tokens
            async for token in query_service.stream_answer(chunks, body.question):
                yield f"data: {json.dumps({'type': 'token', 'token': token})}\n\n"

            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        except RuntimeError as exc:
            logger.warning(
                "analysis/stream RuntimeError (user=%s, project=%s): %s",
                user_id, body.project_name, exc,
            )
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"
        except Exception as exc:
            logger.error(
                "analysis/stream unexpected error (user=%s, project=%s): %s",
                user_id, body.project_name, exc,
                exc_info=True,
            )
            yield f"data: {json.dumps({'type': 'error', 'detail': f'Analysis failed: {exc}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
