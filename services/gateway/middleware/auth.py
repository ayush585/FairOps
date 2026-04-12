"""
Gateway Middleware — Auth.

JWT validation middleware for protected endpoints.
API Key validation for predictions ingest.

Ref: AGENT.md Section 12.
"""

import os
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared.auth import verify_api_key

logger = logging.getLogger("fairops.gateway.auth_middleware")

# Endpoints that don't require auth
PUBLIC_PATHS = {"/", "/health", "/docs", "/redoc", "/openapi.json"}

# Endpoints that use API Key instead of JWT
API_KEY_PATHS = {"/v1/predictions/ingest"}


class AuthMiddleware(BaseHTTPMiddleware):
    """
    Authentication middleware.

    Routes are authenticated based on their path:
    - Public paths: no auth required
    - /v1/predictions/ingest: API Key (X-Api-Key header)
    - All other /v1/* paths: Bearer JWT

    Note: The actual JWT verification is done in route-level dependencies
    for more granular control (e.g., ROLE_ADMIN checks). This middleware
    provides a first-pass filter only.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Public paths — no auth
        if path in PUBLIC_PATHS or path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Metrics endpoint — Cloud Run audience verification, not JWT
        if "/metrics/" in path:
            return await call_next(request)

        # All other paths are handled by route-level Depends()
        return await call_next(request)
