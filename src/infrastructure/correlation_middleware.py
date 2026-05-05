"""
Correlation-ID Middleware for INFERRA.

Injects a correlation_id into every request for end-to-end tracing.
The ID is sourced from the X-Correlation-ID header if provided by
the client, or generated as a new UUID4. It is bound into structlog
context variables so all log messages within the request carry the ID.

Phase 1 WS-5: mandatory log fields (session_id, node_id, fact_source,
correlation_id) are propagated via structlog context vars.
"""

import re
import uuid
from typing import Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_CORRELATION_ID_MAX_LENGTH = 128
_CORRELATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_\.]+$")


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Injects a correlation_id into every request for end-to-end tracing.

    - Reads X-Correlation-ID from the incoming request header
    - Falls back to a new UUID4 if not provided
    - Validates the header value (alphanumeric, hyphens, underscores, dots only)
    - Limits header length to prevent abuse
    - Binds the ID into structlog context vars
    - Returns X-Correlation-ID in the response header
    """

    async def dispatch(self, request: Request, call_next: Callable[..., Response]) -> Response:
        raw_id = request.headers.get("X-Correlation-ID", "")
        if raw_id and (
            len(raw_id) > _CORRELATION_ID_MAX_LENGTH
            or not _CORRELATION_ID_PATTERN.match(raw_id)
        ):
            correlation_id = str(uuid.uuid4())
        elif raw_id:
            correlation_id = raw_id
        else:
            correlation_id = str(uuid.uuid4())

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            structlog.contextvars.clear_contextvars()
