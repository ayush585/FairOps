"""
Shared Telemetry for Google Cloud Monitoring.

Used to emit custom metric timeseries back to GCP to allow
Terraform alerting policies (e.g. tracking bias severity over time).

Ref: AGENT.md Sprint 5.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("fairops.shared.telemetry")


# For mapping categorical severities to numeric thresholds for charting
SEVERITY_MAPPING = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
    "PASS": 0,
}


def emit_bias_metric(model_id: str, severity: str, metric_name: str, value: float):
    """
    Emit bias custom metrics to Google Cloud Monitoring.

    Args:
        model_id: Traced Model.
        severity: Classification class.
        metric_name: The worst performing metric constraint.
        value: The constrained value itself.
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    
    if not project_id:
        logger.debug(f"Telemetry mock: {model_id} | {severity} | {metric_name}={value}")
        return

    try:
        from google.cloud import monitoring_v3

        client = monitoring_v3.MetricServiceClient()
        project_name = f"projects/{project_id}"

        # Setup the Series
        series = monitoring_v3.TimeSeries()
        series.metric.type = "custom.googleapis.com/fairops/bias_severity"
        
        # Attach labels to allow Looker/Cloud Monitoring aggregation
        series.metric.labels["model_id"] = model_id
        series.metric.labels["severity"] = severity
        series.metric.labels["top_metric_name"] = metric_name

        # Standard GCP Generic Task Resource
        series.resource.type = "generic_task"
        series.resource.labels["project_id"] = project_id
        series.resource.labels["location"] = os.environ.get("GCP_REGION", "global")
        series.resource.labels["namespace"] = "fairops_auditor"
        series.resource.labels["job"] = "bias_audit"
        series.resource.labels["task_id"] = model_id

        # Mapping Severity String to an Integer for alert thresholding triggers
        point = monitoring_v3.Point()
        point.value.int64_value = SEVERITY_MAPPING.get(severity, 0)
        
        now = datetime.now(timezone.utc)
        point.interval.end_time.seconds = int(now.timestamp())
        
        series.points = [point]

        # Push to cloud
        client.create_time_series(name=project_name, time_series=[series])
        logger.info(f"Emitted custom metric for {model_id} to Cloud Monitoring")

    except ImportError:
        logger.error("google-cloud-monitoring not installed, skipping telemetry.")
    except Exception as e:
        logger.error(f"Failed emitting telemetry to Cloud Monitoring: {e}")
