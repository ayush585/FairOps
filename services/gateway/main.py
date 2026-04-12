"""
FairOps API Gateway — Main FastAPI Application.

Central entry point for all FairOps API endpoints.
All responses use the ApiResponse envelope from Section 5.

Ref: AGENT.md Section 12.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Add parent directory to path for shared imports
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.logging import setup_logging, log_event
from shared.errors import FairOpsError, AuthenticationError, RateLimitExceededError

from routers import predictions, audits, models, compliance, metrics
from middleware.request_id import RequestIdMiddleware
from middleware.rate_limit import RateLimitMiddleware

# Initialize structured logging — zero print() statements
logger = setup_logging("fairops-gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management."""
    logger.info("FairOps Gateway starting up")
    yield
    logger.info("FairOps Gateway shutting down")


app = FastAPI(
    title="FairOps API",
    description="Real-Time ML Bias Monitoring & Mitigation Pipeline",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware Stack ─────────────────────────────────────────────────────────
# Order matters: outermost middleware runs first

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Lock down in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimitMiddleware)


# ── Exception Handlers ──────────────────────────────────────────────────────

@app.exception_handler(FairOpsError)
async def fairops_error_handler(request: Request, exc: FairOpsError):
    """Handle all FairOps custom exceptions."""
    status_map = {
        AuthenticationError: 401,
        RateLimitExceededError: 429,
    }
    status_code = status_map.get(type(exc), 500)

    logger.error(
        f"FairOps error: {exc}",
        extra={"error_type": type(exc).__name__, "details": exc.details},
        exc_info=True,
    )

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "error",
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
                "details": exc.details,
            },
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Handle unhandled exceptions.
    AGENT.md Rule #5: Fail loudly with full stack traces.
    """
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error": {
                "type": "InternalServerError",
                "message": "An unexpected error occurred. Check Cloud Logging for details.",
            },
            "request_id": getattr(request.state, "request_id", "unknown"),
        },
    )


# ── Register Routers ────────────────────────────────────────────────────────

app.include_router(predictions.router, prefix="/v1", tags=["Predictions"])
app.include_router(audits.router, prefix="/v1", tags=["Audits"])
app.include_router(models.router, prefix="/v1", tags=["Models"])
app.include_router(compliance.router, prefix="/v1", tags=["Compliance"])
app.include_router(metrics.router, prefix="/v1", tags=["Metrics"])


# ── Health Check ─────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "fairops-gateway"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "FairOps API Gateway",
        "version": "0.1.0",
        "docs": "/docs",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8080)),
        reload=os.environ.get("ENV", "development") == "development",
    )
