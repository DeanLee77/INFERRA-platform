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

import structlog
from starlette.datastructures import Headers, MutableHeaders

_CORRELATION_ID_MAX_LENGTH = 128
_CORRELATION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9\-_\.]+$")


class CorrelationIdMiddleware:
    """
    Injects a correlation_id into every request for end-to-end tracing.

    - Reads X-Correlation-ID from the incoming request header
    - Falls back to a new UUID4 if not provided
    - Validates the header value (alphanumeric, hyphens, underscores, dots only)
    - Limits header length to prevent abuse
    - Binds the ID into structlog context vars
    - Returns X-Correlation-ID in the response header
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        raw_id = headers.get("X-Correlation-ID", "")
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

        async def send_with_correlation_id(message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-Correlation-ID"] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_correlation_id)
        finally:
            structlog.contextvars.clear_contextvars()
