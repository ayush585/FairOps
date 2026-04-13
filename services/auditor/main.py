"""
FairOps Auditor — FastAPI Service.

Receives audit triggers from the gateway or Cloud Scheduler
and orchestrates bias detection.

Ref: AGENT.md Sprint 2.
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.logging import setup_logging
from shared.errors import InsufficientSampleSizeError, AuditError

logger = setup_logging("fairops-auditor")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FairOps Auditor starting up")
    yield
    logger.info("FairOps Auditor shutting down")


app = FastAPI(
    title="FairOps Auditor",
    description="Bias Detection Engine — 12 Fairness Metrics",
    version="0.1.0",
    lifespan=lifespan,
)


class AuditRequest(BaseModel):
    model_id: str
    window_hours: int = 1
    protected_attributes: list[str] = ["sex", "race"]
    request_id: str = ""


class MitigateRequest(BaseModel):
    model_id: str
    audit_id: str
    algorithm: Optional[str] = None
    request_id: str = ""


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fairops-auditor"}


@app.post("/audit")
async def run_audit_endpoint(body: AuditRequest):
    """
    Run a full bias audit.

    Called by:
    - Gateway: POST /v1/models/{model_id}/audit
    - Cloud Scheduler: every 15 minutes
    """
    from audit_runner import run_audit

    try:
        result = run_audit(
            model_id=body.model_id,
            window_hours=body.window_hours,
            protected_attributes=body.protected_attributes,
            request_id=body.request_id,
        )
        return result.model_dump()

    except InsufficientSampleSizeError as e:
        raise HTTPException(
            status_code=422,
            detail=str(e),
        )
    except AuditError as e:
        raise HTTPException(
            status_code=500,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unhandled audit error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal audit error: {str(e)}",
        )


@app.post("/mitigate")
async def trigger_mitigation_endpoint(body: MitigateRequest):
    """Trigger the Vertex AI mitigation pipeline."""
    # Placeholder — full implementation in Sprint 4
    logger.info(
        f"Mitigation requested for model {body.model_id}, audit {body.audit_id}"
    )

    return {
        "mitigation_id": f"mit-{body.audit_id[:8]}",
        "pipeline_run_id": "pending",
        "status": "queued",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8001)),
        reload=os.environ.get("ENV", "development") == "development",
    )
