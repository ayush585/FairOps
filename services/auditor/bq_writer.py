"""
FairOps Auditor — BigQuery Writer.

Writes BiasAuditResult and fairness timeseries to BigQuery.

Ref: AGENT.md Section 10 (DDL), Sprint 2.
"""

import json
import logging
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.bigquery import streaming_insert, get_bq_client
from fairops_sdk.schemas import BiasAuditResult

logger = logging.getLogger("fairops.auditor.bq_writer")


def write_audit_result(audit: BiasAuditResult, request_id: str = "") -> None:
    """
    Write a BiasAuditResult to fairops_metrics.bias_audits.

    Args:
        audit: The completed audit result.
        request_id: Request ID for tracing.
    """
    row = {
        "audit_id": audit.audit_id,
        "model_id": audit.model_id,
        "model_version": audit.model_version,
        "audit_timestamp": audit.audit_timestamp.isoformat(),
        "window_start": audit.window_start.isoformat(),
        "window_end": audit.window_end.isoformat(),
        "sample_size": audit.sample_size,
        "overall_severity": audit.overall_severity.value,
        "metrics": json.dumps({
            name: {
                "name": m.name,
                "value": m.value,
                "threshold": m.threshold,
                "breached": m.breached,
                "confidence_interval": list(m.confidence_interval),
                "severity": m.severity.value,
                "groups_compared": list(m.groups_compared),
                "sample_sizes": list(m.sample_sizes),
                "p_value": m.p_value,
            }
            for name, m in audit.metrics.items()
        }),
        "demographic_slices": json.dumps([
            {
                "attribute": s.attribute,
                "group_value": s.group_value,
                "count": s.count,
                "positive_rate": s.positive_rate,
                "metrics": s.metrics,
            }
            for s in audit.demographic_slices
        ]),
        "protected_attributes": audit.protected_attributes,
        "triggered_mitigation": audit.triggered_mitigation,
        "mitigation_id": audit.mitigation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    streaming_insert(
        dataset="fairops_metrics",
        table="bias_audits",
        rows=[row],
        request_id=request_id,
    )

    logger.info(
        f"Audit result written to BigQuery",
        extra={
            "audit_id": audit.audit_id,
            "model_id": audit.model_id,
            "severity": audit.overall_severity.value,
        },
    )


def write_fairness_timeseries(
    audit: BiasAuditResult,
    request_id: str = "",
) -> None:
    """
    Write individual metric values to fairops_metrics.fairness_timeseries.

    This powers the temporal trend dashboard and drift detection.

    Args:
        audit: The completed audit result.
        request_id: Request ID for tracing.
    """
    rows = []
    for name, metric in audit.metrics.items():
        rows.append({
            "model_id": audit.model_id,
            "metric_name": name,
            "metric_value": metric.value,
            "severity": metric.severity.value,
            "recorded_at": audit.audit_timestamp.isoformat(),
        })

    if rows:
        streaming_insert(
            dataset="fairops_metrics",
            table="fairness_timeseries",
            rows=rows,
            request_id=request_id,
        )

        logger.info(
            f"Wrote {len(rows)} metric timeseries entries",
            extra={"model_id": audit.model_id, "audit_id": audit.audit_id},
        )
