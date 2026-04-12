"""
Gateway Router — Compliance.

GET /v1/compliance/report/{model_id}
  Query:   ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&format=pdf|json
  Action:  Gemini generates narrative → reportlab renders PDF
  Returns: application/pdf binary or JSON
  Auth:    Bearer JWT + ROLE_COMPLIANCE

Ref: AGENT.md Section 12.
"""

import os
import logging

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

import httpx

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))

from shared.auth import verify_token, extract_bearer_token
from fairops_sdk.schemas import ApiResponse

logger = logging.getLogger("fairops.gateway.compliance")

router = APIRouter()


async def _get_compliance_user(request: Request) -> dict:
    """Extract JWT and require ROLE_COMPLIANCE."""
    auth_header = request.headers.get("Authorization", "")
    try:
        token = extract_bearer_token(auth_header)
        payload = verify_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or missing JWT token")

    if payload.get("role") not in ("compliance", "admin"):
        raise HTTPException(
            status_code=403,
            detail="ROLE_COMPLIANCE or ROLE_ADMIN required",
        )
    return payload


@router.get("/compliance/report/{model_id}")
async def get_compliance_report(
    model_id: str,
    start_date: str = Query(..., description="Start date YYYY-MM-DD"),
    end_date: str = Query(..., description="End date YYYY-MM-DD"),
    format: str = Query("json", description="Output format: pdf or json"),
    request: Request = None,
    user: dict = Depends(_get_compliance_user),
):
    """
    Generate a formal AI bias regulatory compliance report.

    Gemini generates the narrative → reportlab renders PDF.
    """
    explainer_url = os.environ.get("EXPLAINER_URL", "http://localhost:8002")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.get(
                f"{explainer_url}/compliance-report/{model_id}",
                params={
                    "start_date": start_date,
                    "end_date": end_date,
                    "format": format,
                },
            )
            response.raise_for_status()

            if format == "pdf":
                return StreamingResponse(
                    iter([response.content]),
                    media_type="application/pdf",
                    headers={
                        "Content-Disposition": f"attachment; filename=fairops_compliance_{model_id}_{start_date}_{end_date}.pdf"
                    },
                )
            else:
                return ApiResponse(data=response.json()).model_dump()

    except Exception as e:
        logger.error(f"Compliance report generation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail=f"Compliance report generation failed: {str(e)}",
        )
