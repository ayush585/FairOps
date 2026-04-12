"""
Gateway Router — Models.

POST /v1/models/{model_id}/mitigate — trigger mitigation pipeline
GET  /v1/models/{model_id}/mitigate/{mitigation_id} — get mitigation status
GET  /v1/models/{model_id}/drift — get drift analysis

Ref: AGENT.md Section 12.
"""

import os
import logging
from typing import Optional

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel

import httpx

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))

from shared.logging import log_event
from shared.auth import verify_token, extract_bearer_token
from fairops_sdk.schemas import ApiResponse

logger = logging.getLogger("fairops.gateway.models")

router = APIRouter()


class MitigateRequest(BaseModel):
    audit_id: str
    algorithm: Optional[str] = None  # Auto-select if omitted


async def _get_current_user(request: Request) -> dict:
    """Extract and verify JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    try:
        token = extract_bearer_token(auth_header)
        payload = verify_token(token)
        return payload
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or missing JWT token")


async def _require_admin(user: dict = Depends(_get_current_user)) -> dict:
    """Require ROLE_ADMIN for mitigation endpoints."""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="ROLE_ADMIN required for mitigation operations",
        )
    return user


@router.post("/models/{model_id}/mitigate")
async def trigger_mitigation(
    model_id: str,
    body: MitigateRequest,
    request: Request,
    user: dict = Depends(_require_admin),
):
    """
    Trigger the Vertex AI mitigation pipeline.

    Auth: Bearer JWT + ROLE_ADMIN
    """
    request_id = getattr(request.state, "request_id", "unknown")

    log_event(
        logger,
        event_type="MITIGATION_REQUESTED",
        model_id=model_id,
        request_id=request_id,
        audit_id=body.audit_id,
        algorithm=body.algorithm or "auto-select",
    )

    auditor_url = os.environ.get("AUDITOR_URL", "http://localhost:8001")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{auditor_url}/mitigate",
                json={
                    "model_id": model_id,
                    "audit_id": body.audit_id,
                    "algorithm": body.algorithm,
                    "request_id": request_id,
                },
            )
            response.raise_for_status()
            result = response.json()

    except Exception as e:
        logger.error(f"Mitigation trigger failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to trigger mitigation: {str(e)}",
        )

    return ApiResponse(data=result).model_dump()


@router.get("/models/{model_id}/mitigate/{mitigation_id}")
async def get_mitigation_status(
    model_id: str,
    mitigation_id: str,
    request: Request,
    user: dict = Depends(_get_current_user),
):
    """Get the status of a mitigation pipeline run."""
    from shared.bigquery import query

    results = query(
        """
        SELECT * FROM `fairops_metrics.mitigation_log`
        WHERE mitigation_id = @mitigation_id AND model_id = @model_id
        LIMIT 1
        """,
        params=[
            {"name": "mitigation_id", "parameterType": {"type": "STRING"}, "parameterValue": {"value": mitigation_id}},
            {"name": "model_id", "parameterType": {"type": "STRING"}, "parameterValue": {"value": model_id}},
        ],
    )

    if not results:
        raise HTTPException(
            status_code=404,
            detail=f"Mitigation {mitigation_id} not found for model {model_id}",
        )

    return ApiResponse(data=results[0]).model_dump()


@router.get("/models/{model_id}/drift")
async def get_drift_analysis(
    model_id: str,
    window_days: int = 30,
    metrics: Optional[str] = None,
    request: Request = None,
    user: dict = Depends(_get_current_user),
):
    """
    Get temporal drift analysis for a model's fairness metrics.

    Returns time series of metric values + CUSUM drift detection output.
    """
    metric_list = metrics.split(",") if metrics else ["demographic_parity_difference"]

    from shared.bigquery import query

    results = query(
        f"""
        SELECT model_id, metric_name, metric_value, severity, recorded_at
        FROM `fairops_metrics.fairness_timeseries`
        WHERE model_id = @model_id
          AND metric_name IN UNNEST(@metrics)
          AND recorded_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL @window_days DAY)
        ORDER BY recorded_at ASC
        """,
        params=[
            {"name": "model_id", "parameterType": {"type": "STRING"}, "parameterValue": {"value": model_id}},
            {"name": "metrics", "parameterType": {"type": "ARRAY", "arrayType": {"type": "STRING"}}, "parameterValue": {"arrayValues": [{"value": m} for m in metric_list]}},
            {"name": "window_days", "parameterType": {"type": "INT64"}, "parameterValue": {"value": str(window_days)}},
        ],
    )

    return ApiResponse(data={"timeseries": results, "window_days": window_days}).model_dump()
