"""
Gateway Middleware — Request ID.

Generates a unique request ID for every incoming request
and attaches it to the request state for tracing.

Ref: AGENT.md Section 16 — every log entry must include request_id.
"""

from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Generates and propagates a unique request ID.

    If the client sends an X-Request-Id header, use it.
    Otherwise, generate a new UUID4.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Use client-provided request ID or generate new one
        request_id = request.headers.get("X-Request-Id", str(uuid4()))

        # Attach to request state for use in handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Include request ID in response headers
        response.headers["X-Request-Id"] = request_id

        return response
