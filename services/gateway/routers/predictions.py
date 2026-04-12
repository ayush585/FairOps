"""
Gateway Router — Predictions Ingestion.

POST /v1/predictions/ingest
  Body:        PredictionEvent | list[PredictionEvent] (max 500)
  Action:      Publish to Pub/Sub
  Returns:     { "event_ids": [...], "queued": N }
  Auth:        API Key (X-Api-Key header)
  Rate limit:  10,000 req/min

Ref: AGENT.md Section 12.
"""

import os
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Header, HTTPException
from pydantic import BaseModel
from typing import Union

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))

from shared.auth import verify_api_key
from shared.logging import log_event
from fairops_sdk.schemas import PredictionEvent, ApiResponse
from fairops_sdk.publisher import PredictionPublisher

logger = logging.getLogger("fairops.gateway.predictions")

router = APIRouter()

# Lazy-initialized publisher
_publisher = None


def _get_publisher() -> PredictionPublisher:
    global _publisher
    if _publisher is None:
        project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
        _publisher = PredictionPublisher(project_id=project_id)
    return _publisher


class IngestResponse(BaseModel):
    event_ids: list[str]
    queued: int


@router.post("/predictions/ingest")
async def ingest_predictions(
    request: Request,
    x_api_key: str = Header(..., alias="X-Api-Key"),
):
    """
    Ingest prediction events for bias monitoring.

    Accepts a single PredictionEvent or a list of up to 500 events.
    Publishes to Cloud Pub/Sub for downstream processing.
    """
    request_id = getattr(request.state, "request_id", "unknown")

    # Validate API key
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Parse request body
    body = await request.json()

    # Handle single event or batch
    if isinstance(body, list):
        if len(body) > 500:
            raise HTTPException(
                status_code=400,
                detail=f"Batch size {len(body)} exceeds maximum of 500",
            )
        events = [PredictionEvent.model_validate(e) for e in body]
    else:
        events = [PredictionEvent.model_validate(body)]

    # Publish to Pub/Sub
    publisher = _get_publisher()
    event_ids = []

    for event in events:
        try:
            publisher.publish(event)
            event_ids.append(event.event_id)
        except Exception as e:
            logger.error(
                f"Failed to publish event {event.event_id}: {e}",
                exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to publish event: {str(e)}",
            )

    log_event(
        logger,
        event_type="PREDICTIONS_INGESTED",
        model_id=events[0].model_id if events else "unknown",
        request_id=request_id,
        event_count=len(event_ids),
    )

    return ApiResponse(
        data=IngestResponse(
            event_ids=event_ids,
            queued=len(event_ids),
        ).model_dump(),
    ).model_dump()
