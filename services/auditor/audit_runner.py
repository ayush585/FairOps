"""
FairOps Auditor — Audit Runner.

Orchestrates the full audit pipeline:
1. Fetch prediction data from BigQuery
2. Construct demographic slices
3. Compute all 12 fairness metrics
4. Classify overall severity
5. Write results to BigQuery + Cloud Spanner
6. Trigger mitigation pipeline if CRITICAL/HIGH

Ref: AGENT.md Sprint 2.
"""

import logging
import os
import numpy as np
import pandas as pd
from datetime import datetime, timedelta, timezone

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.logging import log_event, log_error
from shared.errors import InsufficientSampleSizeError, AuditError
from fairops_sdk.schemas import BiasAuditResult, Severity

from shared.telemetry import emit_bias_metric

from metrics.fairness import compute_all_metrics
from severity import classify_overall_severity, get_required_action
from slicing import build_demographic_slices

logger = logging.getLogger("fairops.auditor.runner")


def run_audit(
    model_id: str,
    window_hours: int = 1,
    protected_attributes: list[str] | None = None,
    request_id: str = "",
) -> BiasAuditResult:
    """
    Execute a full bias audit for a model.

    Args:
        model_id: Model to audit.
        window_hours: Hours of prediction data to analyze.
        protected_attributes: List of sensitive attributes to audit.
        request_id: Request ID for tracing.

    Returns:
        BiasAuditResult with all 12 metrics computed.

    Raises:
        InsufficientSampleSizeError: If sample size < AUDIT_MIN_SAMPLE_SIZE.
        AuditError: On audit execution failure.
    """
    if protected_attributes is None:
        protected_attributes = ["sex", "race"]

    min_sample_size = int(os.environ.get("AUDIT_MIN_SAMPLE_SIZE", "100"))

    log_event(
        logger,
        event_type="AUDIT_STARTED",
        model_id=model_id,
        request_id=request_id,
        window_hours=window_hours,
        protected_attributes=protected_attributes,
    )

    # ── Step 1: Fetch data from BigQuery ─────────────────────────────────
    window_end = datetime.now(timezone.utc)
    window_start = window_end - timedelta(hours=window_hours)

    try:
        df = _fetch_prediction_data(model_id, window_start, window_end)
    except Exception as e:
        log_error(logger, "AUDIT_DATA_FETCH_FAILED", model_id, request_id, e)
        raise AuditError(f"Failed to fetch prediction data: {e}") from e

    sample_size = len(df)

    if sample_size < min_sample_size:
        raise InsufficientSampleSizeError(
            f"Sample size {sample_size} < minimum {min_sample_size}",
            details={"sample_size": sample_size, "minimum": min_sample_size},
        )

    # ── Step 2: Extract arrays ───────────────────────────────────────────
    y_true = df["ground_truth"].values.astype(int)
    y_pred = df["prediction_label"].values.astype(int)
    y_score = df["prediction_score"].values.astype(float)

    # ── Step 3: Compute metrics per protected attribute ──────────────────
    all_metrics = {}
    all_slices = []

    for attr in protected_attributes:
        if attr not in df.columns:
            logger.warning(f"Protected attribute '{attr}' not found in data")
            continue

        sensitive = df[attr].values.astype(str)

        # Determine privileged group (most common or specified)
        privileged_group = _determine_privileged_group(sensitive, attr)

        # Compute all 12 metrics
        attr_metrics = compute_all_metrics(
            y_true=y_true,
            y_pred=y_pred,
            y_score=y_score,
            sensitive=sensitive,
            privileged_group=privileged_group,
        )
        all_metrics.update(attr_metrics)

        # Build demographic slices
        attr_slices = build_demographic_slices(
            y_true=y_true,
            y_pred=y_pred,
            sensitive=sensitive,
            attribute_name=attr,
        )
        all_slices.extend(attr_slices)

    # ── Step 4: Classify severity ────────────────────────────────────────
    overall_severity = classify_overall_severity(all_metrics)
    action = get_required_action(overall_severity)

    # ── Step 5: Build result ─────────────────────────────────────────────
    model_version = df["model_version"].iloc[0] if "model_version" in df.columns else "unknown"

    audit_result = BiasAuditResult(
        model_id=model_id,
        model_version=model_version,
        window_start=window_start,
        window_end=window_end,
        sample_size=sample_size,
        metrics=all_metrics,
        overall_severity=overall_severity,
        protected_attributes=protected_attributes,
        demographic_slices=all_slices,
    )

    # ── Sprint 5: Emitting Telemetry to Cloud Monitoring ──
    top_metric_name = "none"
    top_metric_value = 0.0
    threshold_val = 0.0
    for name, m in all_metrics.items():
        if m.breached:
            top_metric_name = name
            top_metric_value = m.value
            threshold_val = m.threshold
            break

    emit_bias_metric(model_id, overall_severity.value, top_metric_name, top_metric_value)

    # ── Sprint 5: Dispatch to Notifier Service ──
    if overall_severity.value in ["CRITICAL", "HIGH"]:
        try:
            import httpx
            notifier_host = os.environ.get("NOTIFIER_HOST", "http://localhost:8004")
            with httpx.Client() as client:
                client.post(
                    f"{notifier_host}/notify",
                    json={
                        "audit_id": audit_result.audit_id,
                        "model_id": model_id,
                        "severity": overall_severity.value,
                        "top_metric_name": top_metric_name,
                        "top_metric_value": top_metric_value,
                        "threshold": threshold_val
                    },
                    timeout=2.0
                )
        except Exception as e:
            logger.error(f"Failed to trigger /notify on Notifier service: {e}")

    log_event(
        logger,
        event_type="AUDIT_COMPLETED",
        model_id=model_id,
        request_id=request_id,
        audit_id=audit_result.audit_id,
        severity=overall_severity.value,
        sample_size=sample_size,
        n_metrics=len(all_metrics),
        n_breached=sum(1 for m in all_metrics.values() if m.breached),
    )

    # ── Step 6: Write results ────────────────────────────────────────────
    _persist_results(audit_result, action, request_id)

    return audit_result


def _fetch_prediction_data(
    model_id: str,
    window_start: datetime,
    window_end: datetime,
) -> pd.DataFrame:
    """Fetch prediction data from BigQuery for the audit window."""
    from shared.bigquery import get_bq_client

    client = get_bq_client()
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")

    query = f"""
    SELECT
        p.event_id,
        p.model_id,
        p.model_version,
        p.prediction_label,
        p.prediction_score,
        p.prediction_threshold,
        p.ground_truth,
        p.demographic_tags,
        p.features,
        d.gender_distribution,
        d.race_distribution,
        d.age_bin
    FROM `{project_id}.fairops_raw.predictions` p
    LEFT JOIN `{project_id}.fairops_enriched.demographics` d
        ON p.event_id = d.event_id
    WHERE p.model_id = @model_id
        AND p.timestamp >= @window_start
        AND p.timestamp < @window_end
        AND p.ground_truth IS NOT NULL
    ORDER BY p.timestamp
    """

    from google.cloud import bigquery

    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("model_id", "STRING", model_id),
            bigquery.ScalarQueryParameter("window_start", "TIMESTAMP", window_start),
            bigquery.ScalarQueryParameter("window_end", "TIMESTAMP", window_end),
        ]
    )

    df = client.query(query, job_config=job_config).to_dataframe()

    # Extract sensitive attributes from features/demographics
    if "features" in df.columns:
        df = _extract_sensitive_features(df)

    return df


def _extract_sensitive_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extract sensitive attributes from JSON features column."""
    import json

    if "features" in df.columns:
        for attr in ["sex", "gender", "race", "age"]:
            if attr not in df.columns:
                try:
                    df[attr] = df["features"].apply(
                        lambda x: json.loads(x).get(attr) if isinstance(x, str) else x.get(attr) if isinstance(x, dict) else None
                    )
                except Exception:
                    pass

    # Map gender/sex to standardized values
    if "sex" in df.columns:
        gender_map = {"Male": "Male", "Female": "Female", "M": "Male", "F": "Female", "male": "Male", "female": "Female"}
        df["sex"] = df["sex"].map(gender_map).fillna(df["sex"])

    return df


def _determine_privileged_group(sensitive: np.ndarray, attr: str) -> str:
    """Determine the privileged group for a sensitive attribute."""
    # Known privileged groups per AGENT.md Section 21
    known_privileged = {
        "sex": "Male",
        "gender": "Male",
        "race": "White",
        "age_bin": "AGE_30_40",
    }

    if attr in known_privileged:
        return known_privileged[attr]

    # Default: most common group
    unique, counts = np.unique(sensitive, return_counts=True)
    return str(unique[counts.argmax()])


def _persist_results(
    audit: BiasAuditResult,
    action: dict,
    request_id: str,
) -> None:
    """Persist audit results to BigQuery and Cloud Spanner."""
    try:
        from bq_writer import write_audit_result, write_fairness_timeseries

        if action.get("log_to_bq", True):
            write_audit_result(audit, request_id)
            write_fairness_timeseries(audit, request_id)

    except Exception as e:
        logger.error(f"Failed to write to BigQuery: {e}", exc_info=True)

    try:
        from spanner_writer import write_audit_completed

        if action.get("log_to_spanner", True):
            write_audit_completed(audit)

    except Exception as e:
        logger.error(f"Failed to write to Spanner: {e}", exc_info=True)
