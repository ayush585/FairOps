"""
FairOps Notifier Service — FastAPI Entrypoint.

Handles incoming webhook triggers from the Auditor service
when severe bias boundaries (CRITICAL or HIGH) are breached.

Ref: AGENT.md Sprint 5.
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
from slack_sender import send_slack_alert

logger = setup_logging("fairops-notifier")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FairOps Notifier service starting up")
    yield
    logger.info("FairOps Notifier service shutting down")


app = FastAPI(
    title="FairOps Notifier Service",
    description="Alerts distribution across Slack and compliance channels",
    version="0.1.0",
    lifespan=lifespan,
)


class NotificationRequest(BaseModel):
    audit_id: str
    model_id: str
    severity: str
    top_metric_name: str
    top_metric_value: float
    threshold: float


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fairops-notifier"}


@app.post("/notify")
async def trigger_notification(request: NotificationRequest, background_tasks: BackgroundTasks):
    """
    Trigger notifications across configured channels (e.g., Slack).
    Only proceeds if severity is CRITICAL or HIGH.
    """
    if request.severity not in ["CRITICAL", "HIGH"]:
        logger.info(f"Ignored alert payload for {request.model_id} - severity is only {request.severity}")
        return {"status": "ignored", "reason": f"Severity {request.severity} does not meet threshold"}

    logger.info(f"Dispatching notifications for audit {request.audit_id} ({request.severity})")

    # Send asynchronously without blocking the upstream Auditor
    background_tasks.add_task(
        send_slack_alert,
        model_id=request.model_id,
        audit_id=request.audit_id,
        severity=request.severity,
        top_metric_name=request.top_metric_name,
        top_metric_value=request.top_metric_value,
        threshold=request.threshold,
    )

    return {
        "status": "success",
        "message": "Alert dispatched to background queues",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8004)),
        reload=os.environ.get("ENV", "development") == "development",
    )
