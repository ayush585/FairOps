"""
FairOps Mitigation Engine — FastAPI Service.

Serves the HTTP endpoint necessary to trigger an asynchronous mitigation
Vertex CustomJob based on severe bias severity events.

Ref: AGENT.md Sprint 4.
"""

import os
import sys
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.logging import setup_logging
from services.mitigation.vertex_jobs import trigger_mitigation_job
from fairops_sdk.schemas import MitigationStage

logger = setup_logging("fairops-mitigation")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FairOps Mitigation service starting up")
    yield
    logger.info("FairOps Mitigation service shutting down")


app = FastAPI(
    title="FairOps Mitigation Engine",
    description="Orchestrates AI bias mitigation Vertex CustomJobs",
    version="0.1.0",
    lifespan=lifespan,
)


class MitigationRequest(BaseModel):
    audit_id: str
    model_id: str
    algorithm: str = "exponentiated_gradient"
    stage: MitigationStage = MitigationStage.IN_PROCESSING


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fairops-mitigation"}


@app.post("/mitigate")
async def mitigate_bias(request: MitigationRequest, background_tasks: BackgroundTasks):
    """
    Trigger a mitigation job for a biased model.
    """
    from uuid import uuid4
    mitigation_id = str(uuid4())

    logger.info(
        f"Received mitigation request for {request.model_id} (Audit: {request.audit_id}). "
        f"Assigned Mitigation ID: {mitigation_id}"
    )

    try:
        # Launch Vertex CustomJob asynchronously
        # This will write out the mitigation_id and current status payload to Vertex.
        result = trigger_mitigation_job(
            mitigation_id=mitigation_id,
            audit_id=request.audit_id,
            model_id=request.model_id,
            algorithm=request.algorithm,
            stage=request.stage.value,
        )

        return {
            "status": "success",
            "message": "Mitigation job submitted",
            "mitigation_id": mitigation_id,
            "vertex_details": result,
        }

    except Exception as e:
        logger.error(f"Mitigation trigger failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8003)),
        reload=os.environ.get("ENV", "development") == "development",
    )
