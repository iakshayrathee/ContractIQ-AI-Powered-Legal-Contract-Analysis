"""
app/middleware/request_id.py
=============================
Injects a unique UUID request ID into every request and binds it to the
structlog context so all log events within that request carry the same
`request_id` field automatically.

Also sets an `X-Request-ID` response header so callers can correlate
their request logs with the server-side logs.
"""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Per-request middleware that:
      1. Reads or generates a request ID (prefers X-Request-ID from client).
      2. Binds it to structlog's context vars for the lifetime of the request.
      3. Sets X-Request-ID on the response for client-side correlation.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Bind to structlog — all log calls within this request will include it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
