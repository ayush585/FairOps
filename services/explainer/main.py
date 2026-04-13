"""
FairOps Explainer — FastAPI Service.

Serves SHAP explanations, Gemini narratives, DiCE counterfactuals,
and PDF compliance reports.

Ref: AGENT.md Sprint 3, Section 12 (API endpoints).
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import io

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.logging import setup_logging
from redis_cache import get_cache

logger = setup_logging("fairops-explainer")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FairOps Explainer starting up")
    get_cache()  # Warm up cache connection
    yield
    logger.info("FairOps Explainer shutting down")


app = FastAPI(
    title="FairOps Explainer",
    description="SHAP + Gemini Pro + DiCE + PDF Compliance Reports",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "fairops-explainer"}


# ── /explain/{audit_id} ───────────────────────────────────────────────────────

@app.get("/explain/{audit_id}")
async def explain_audit(
    audit_id: str,
    include_shap: bool = Query(True),
    include_counterfactuals: bool = Query(True),
):
    """
    Get full explanation for a bias audit: SHAP + Gemini narrative + counterfactuals.

    Results are cached in Redis for 1 hour.
    """
    cache = get_cache()

    # Check cache first
    cached_narrative = cache.get_narrative(audit_id)
    cached_shap = cache.get_shap(audit_id)

    if cached_narrative and (cached_shap or not include_shap):
        logger.info(f"Cache hit for audit {audit_id}")
        return {
            "audit_id": audit_id,
            "narrative": cached_narrative,
            "shap": cached_shap,
            "cache_hit": True,
        }

    # Fetch audit data from BigQuery
    audit_data = await _fetch_audit_data(audit_id)
    if not audit_data:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    result = {"audit_id": audit_id, "cache_hit": False}

    # Generate SHAP explanation
    if include_shap:
        shap_result = _compute_shap_proxy(audit_data)
        cache.set_shap(audit_id, shap_result)
        result["shap"] = shap_result

    # Generate Gemini narrative
    from gemini_narrator import generate_audit_narrative
    narrative = generate_audit_narrative(
        audit_id=audit_id,
        model_id=audit_data.get("model_id", ""),
        model_version=audit_data.get("model_version", ""),
        window_start=str(audit_data.get("window_start", "")),
        window_end=str(audit_data.get("window_end", "")),
        overall_severity=audit_data.get("overall_severity", "PASS"),
        metrics=audit_data.get("metrics", {}),
        demographic_slices=audit_data.get("demographic_slices", []),
        shap_result=result.get("shap"),
        sample_size=audit_data.get("sample_size", 0),
    )
    cache.set_narrative(audit_id, narrative)
    result["narrative"] = narrative

    return result


# ── /shap/{audit_id} ──────────────────────────────────────────────────────────

@app.get("/shap/{audit_id}")
async def get_shap(audit_id: str):
    """
    Get SHAP feature importances for a bias audit.

    Cached for 1 hour in Redis.
    """
    cache = get_cache()
    cached = cache.get_shap(audit_id)

    if cached:
        return {**cached, "cache_hit": True, "audit_id": audit_id}

    audit_data = await _fetch_audit_data(audit_id)
    if not audit_data:
        raise HTTPException(status_code=404, detail=f"Audit {audit_id} not found")

    shap_result = _compute_shap_proxy(audit_data)
    cache.set_shap(audit_id, shap_result)

    return {**shap_result, "cache_hit": False, "audit_id": audit_id}


# ── /compliance-report/{model_id} ─────────────────────────────────────────────

@app.get("/compliance-report/{model_id}")
async def generate_compliance_report(
    model_id: str,
    start_date: str = Query(...),
    end_date: str = Query(...),
    format: str = Query("json"),
):
    """
    Generate a formal AI bias compliance report.

    Gemini generates the narrative → reportlab renders PDF.
    Cached for 24 hours in Redis.
    """
    cache = get_cache()

    # Check PDF cache
    if format == "pdf":
        cached_pdf = cache.get_report(model_id, start_date, end_date)
        if cached_pdf:
            logger.info(f"PDF cache hit for {model_id} {start_date}/{end_date}")
            return StreamingResponse(
                io.BytesIO(cached_pdf),
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=fairops_{model_id}_{start_date}_{end_date}.pdf",
                    "X-Cache": "HIT",
                },
            )

    # Fetch all audits in date range
    audit_data = await _fetch_audit_range(model_id, start_date, end_date)
    if not audit_data:
        raise HTTPException(
            status_code=404,
            detail=f"No audits found for model {model_id} in {start_date}/{end_date}",
        )

    # Aggregate metrics across audits
    aggregated = _aggregate_audit_data(audit_data)

    # Generate narrative
    from gemini_narrator import generate_audit_narrative
    narrative = generate_audit_narrative(
        audit_id=f"report-{model_id}-{start_date}-{end_date}",
        model_id=model_id,
        model_version=aggregated.get("model_version", "unknown"),
        window_start=start_date,
        window_end=end_date,
        overall_severity=aggregated.get("worst_severity", "PASS"),
        metrics=aggregated.get("metrics", {}),
        demographic_slices=aggregated.get("demographic_slices", []),
        sample_size=aggregated.get("total_sample_size", 0),
    )

    if format == "pdf":
        from compliance_report import generate_pdf_report
        pdf_bytes = generate_pdf_report(
            model_id=model_id,
            model_version=aggregated.get("model_version", "unknown"),
            start_date=start_date,
            end_date=end_date,
            overall_severity=aggregated.get("worst_severity", "PASS"),
            sample_size=aggregated.get("total_sample_size", 0),
            metrics=aggregated.get("metrics", {}),
            demographic_slices=aggregated.get("demographic_slices", []),
            narrative=narrative,
            audit_ids=aggregated.get("audit_ids", []),
        )

        cache.set_report(model_id, start_date, end_date, pdf_bytes)

        return StreamingResponse(
            io.BytesIO(pdf_bytes),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=fairops_{model_id}_{start_date}_{end_date}.pdf",
                "X-Cache": "MISS",
            },
        )
    else:
        return {
            "model_id": model_id,
            "period": {"start": start_date, "end": end_date},
            "narrative": narrative,
            **aggregated,
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _fetch_audit_data(audit_id: str) -> Optional[dict]:
    """Fetch a single audit result from BigQuery."""
    try:
        from shared.bigquery import get_bq_client
        from google.cloud import bigquery
        import json

        client = get_bq_client()
        project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")

        query = f"""
        SELECT * FROM `{project_id}.fairops_metrics.bias_audits`
        WHERE audit_id = @audit_id
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("audit_id", "STRING", audit_id)
            ]
        )
        rows = list(client.query(query, job_config=job_config).result())
        if not rows:
            return None

        row = dict(rows[0])
        if isinstance(row.get("metrics"), str):
            row["metrics"] = json.loads(row["metrics"])
        if isinstance(row.get("demographic_slices"), str):
            row["demographic_slices"] = json.loads(row["demographic_slices"])
        return row

    except Exception as e:
        logger.error(f"Failed to fetch audit {audit_id}: {e}", exc_info=True)
        return None


async def _fetch_audit_range(model_id: str, start_date: str, end_date: str) -> list[dict]:
    """Fetch all audits for a model in a date range."""
    try:
        from shared.bigquery import get_bq_client
        from google.cloud import bigquery
        import json

        client = get_bq_client()
        project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")

        query = f"""
        SELECT * FROM `{project_id}.fairops_metrics.bias_audits`
        WHERE model_id = @model_id
          AND DATE(audit_timestamp) BETWEEN @start_date AND @end_date
        ORDER BY audit_timestamp DESC
        LIMIT 100
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("model_id", "STRING", model_id),
                bigquery.ScalarQueryParameter("start_date", "DATE", start_date),
                bigquery.ScalarQueryParameter("end_date", "DATE", end_date),
            ]
        )
        rows = []
        for row in client.query(query, job_config=job_config).result():
            r = dict(row)
            if isinstance(r.get("metrics"), str):
                r["metrics"] = json.loads(r["metrics"])
            if isinstance(r.get("demographic_slices"), str):
                r["demographic_slices"] = json.loads(r["demographic_slices"])
            rows.append(r)
        return rows

    except Exception as e:
        logger.error(f"Failed to fetch audit range: {e}", exc_info=True)
        return []


def _aggregate_audit_data(audits: list[dict]) -> dict:
    """Aggregate multiple audit results into a report summary."""
    severity_order = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "PASS"]
    worst_severity = "PASS"

    all_metrics: dict[str, dict] = {}
    all_slices: list[dict] = []
    total_samples = 0
    audit_ids = []
    model_version = "unknown"

    for audit in audits:
        audit_ids.append(audit.get("audit_id", ""))
        total_samples += audit.get("sample_size", 0)
        model_version = audit.get("model_version", model_version)

        severity = audit.get("overall_severity", "PASS")
        if severity_order.index(severity) < severity_order.index(worst_severity):
            worst_severity = severity

        # Merge metrics (keep worst breach per metric)
        for name, m in (audit.get("metrics") or {}).items():
            if name not in all_metrics or (m.get("breached") and not all_metrics[name].get("breached")):
                all_metrics[name] = m

        # Collect slices (deduplicated by group)
        for s in (audit.get("demographic_slices") or []):
            key = f"{s.get('attribute')}={s.get('group_value')}"
            if not any(
                f"{x.get('attribute')}={x.get('group_value')}" == key
                for x in all_slices
            ):
                all_slices.append(s)

    return {
        "worst_severity": worst_severity,
        "total_sample_size": total_samples,
        "n_audits": len(audits),
        "audit_ids": audit_ids,
        "metrics": all_metrics,
        "demographic_slices": all_slices[:20],
        "model_version": model_version,
    }


def _compute_shap_proxy(audit_data: dict) -> dict:
    """
    Compute a SHAP-proxy explanation from audit metrics.

    Used when the model artifact is not available — derives feature
    importance from the bias audit's metric values and demographic data.
    """
    from shap_explainer import explain_bias_drivers

    metrics = audit_data.get("metrics", {})
    slices = audit_data.get("demographic_slices", [])

    # Build proxy feature importance from metric contributions
    feature_importance = []
    for i, (name, m) in enumerate(metrics.items()):
        if m.get("breached"):
            feature_importance.append({
                "feature": name.replace("_", " ").title(),
                "importance": round(float(m.get("value", 0)), 4),
                "rank": i + 1,
            })

    return explain_bias_drivers(
        audit_id=audit_data.get("audit_id", ""),
        model_id=audit_data.get("model_id", ""),
        feature_importance=feature_importance,
        demographic_slices=[
            {
                "attribute": s.get("attribute"),
                "group_value": s.get("group_value"),
                "positive_rate": s.get("positive_rate"),
                "metrics": s.get("metrics", {}),
            }
            for s in slices
        ],
        metrics=metrics,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8002)),
        reload=os.environ.get("ENV", "development") == "development",
    )
