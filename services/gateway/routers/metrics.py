"""
Gateway Router — Prometheus Metrics.

GET /v1/metrics/fairness/{model_id}
  Returns:  Prometheus text format for Cloud Monitoring scraping
  Auth:     Internal Cloud Run audience verification (no JWT)

Ref: AGENT.md Section 12.
"""

import os
import logging

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))

from shared.bigquery import query

logger = logging.getLogger("fairops.gateway.metrics")

router = APIRouter()


@router.get("/metrics/fairness/{model_id}", response_class=PlainTextResponse)
async def get_fairness_metrics_prometheus(model_id: str, request: Request):
    """
    Export fairness metrics in Prometheus text format.

    Used by Cloud Monitoring for scraping. No JWT required —
    authentication is handled by Cloud Run audience verification.
    """
    try:
        results = query(
            """
            SELECT metric_name, metric_value, severity, recorded_at
            FROM `fairops_metrics.fairness_timeseries`
            WHERE model_id = @model_id
              AND recorded_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
            ORDER BY recorded_at DESC
            """,
            params=[
                {
                    "name": "model_id",
                    "parameterType": {"type": "STRING"},
                    "parameterValue": {"value": model_id},
                },
            ],
        )

        # Build Prometheus text format
        lines = [
            "# HELP fairops_bias_metric Current bias metric value",
            "# TYPE fairops_bias_metric gauge",
        ]

        seen_metrics = set()
        for row in results:
            metric_name = row.get("metric_name", "unknown")
            if metric_name not in seen_metrics:
                seen_metrics.add(metric_name)
                value = row.get("metric_value", 0.0)
                severity = row.get("severity", "UNKNOWN")
                lines.append(
                    f'fairops_bias_metric{{model_id="{model_id}",'
                    f'metric="{metric_name}",severity="{severity}"}} {value}'
                )

        return "\n".join(lines) + "\n"

    except Exception as e:
        logger.error(f"Metrics export failed: {e}", exc_info=True)
        return PlainTextResponse(
            f"# Error fetching metrics: {str(e)}\n",
            status_code=500,
        )
