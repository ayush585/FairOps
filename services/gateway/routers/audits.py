"""
Gateway Router — Audits.

POST /v1/models/{model_id}/audit — trigger a bias audit
GET  /v1/audits/{audit_id} — fetch audit result
GET  /v1/audits/{audit_id}/explain — get Gemini narrative + SHAP
GET  /v1/audits/{audit_id}/shap — get SHAP feature importances

Ref: AGENT.md Section 12.
"""

import os
import logging

from fastapi import APIRouter, Request, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional

import httpx

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))

from shared.logging import log_event
from shared.auth import verify_token, extract_bearer_token
from fairops_sdk.schemas import ApiResponse

logger = logging.getLogger("fairops.gateway.audits")

router = APIRouter()


class AuditRequest(BaseModel):
    window_hours: int = 1
    protected_attributes: list[str] = ["sex", "race"]


async def _get_current_user(request: Request) -> dict:
    """Extract and verify JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    try:
        token = extract_bearer_token(auth_header)
        return verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or missing JWT token")


@router.post("/models/{model_id}/audit")
async def trigger_audit(
    model_id: str,
    body: AuditRequest,
    request: Request,
    user: dict = Depends(_get_current_user),
):
    """
    Trigger a bias audit for a model.

    Proxies the request to the auditor service which:
    1. Pulls data from BigQuery for the specified window
    2. Computes all 12 fairness metrics
    3. Classifies severity
    4. Writes results to BQ + Spanner
    5. If CRITICAL/HIGH, triggers the mitigation pipeline
    """
    request_id = getattr(request.state, "request_id", "unknown")

    log_event(
        logger,
        event_type="AUDIT_REQUESTED",
        model_id=model_id,
        request_id=request_id,
        window_hours=body.window_hours,
        protected_attributes=body.protected_attributes,
    )

    # Proxy to auditor service
    auditor_url = os.environ.get("AUDITOR_URL", "http://localhost:8001")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{auditor_url}/audit",
                json={
                    "model_id": model_id,
                    "window_hours": body.window_hours,
                    "protected_attributes": body.protected_attributes,
                    "request_id": request_id,
                },
            )
            response.raise_for_status()
            audit_result = response.json()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Audit request timed out. SLA: <30s for up to 100k predictions.",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=f"Auditor service error: {e.response.text}",
        )
    except Exception as e:
        logger.error(f"Failed to reach auditor service: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Cannot reach auditor service: {str(e)}",
        )

    return ApiResponse(data=audit_result).model_dump()


@router.get("/audits/{audit_id}")
async def get_audit(
    audit_id: str,
    request: Request,
    user: dict = Depends(_get_current_user),
):
    """Fetch a bias audit result by ID."""
    request_id = getattr(request.state, "request_id", "unknown")

    # Query BigQuery for the audit result
    from shared.bigquery import query

    results = query(
        """
        SELECT * FROM `fairops_metrics.bias_audits`
        WHERE audit_id = @audit_id
        LIMIT 1
        """,
        params=[
            {"name": "audit_id", "parameterType": {"type": "STRING"}, "parameterValue": {"value": audit_id}},
        ],
    )

    if not results:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    return ApiResponse(data=results[0]).model_dump()


@router.get("/audits/{audit_id}/explain")
async def get_audit_explanation(
    audit_id: str,
    include_shap: bool = True,
    include_counterfactuals: bool = True,
    request: Request = None,
    user: dict = Depends(_get_current_user),
):
    """
    Get AI-generated bias narrative for an audit.

    Proxies to the explainer service which:
    1. Computes SHAP values (cached in Redis 1hr)
    2. Calls Gemini Pro for narrative generation (cached in Redis 1hr)
    3. Optionally includes DiCE counterfactuals
    """
    explainer_url = os.environ.get("EXPLAINER_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{explainer_url}/explain/{audit_id}",
                params={
                    "include_shap": include_shap,
                    "include_counterfactuals": include_counterfactuals,
                },
            )
            response.raise_for_status()
            explanation = response.json()

    except Exception as e:
        logger.error(f"Explainer service error: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Explainer service error: {str(e)}",
        )

    return ApiResponse(data=explanation).model_dump()


@router.get("/audits/{audit_id}/shap")
async def get_audit_shap(
    audit_id: str,
    request: Request = None,
    user: dict = Depends(_get_current_user),
):
    """Get SHAP feature importance for an audit."""
    explainer_url = os.environ.get("EXPLAINER_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(
                f"{explainer_url}/shap/{audit_id}",
            )
            response.raise_for_status()
            shap_result = response.json()

    except Exception as e:
        logger.error(f"SHAP service error: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"SHAP service error: {str(e)}",
        )

    return ApiResponse(data=shap_result).model_dump()
