# ==============================================================================
# FairOps — Cloud Monitoring Module
# Custom metrics + CRITICAL bias alert policy
# Ref: AGENT.md Section 17
# ==============================================================================

variable "project_id" {
  type = string
}

variable "slack_notification_channel_id" {
  type    = string
  default = ""
}

# ── Custom Metric Descriptors ────────────────────────────────────────────────

resource "google_monitoring_metric_descriptor" "bias_severity" {
  project      = var.project_id
  description  = "FairOps bias severity gauge per model"
  display_name = "FairOps Bias Severity"
  type         = "custom.googleapis.com/fairops/bias_severity"
  metric_kind  = "GAUGE"
  value_type   = "INT64"

  labels {
    key         = "model_id"
    value_type  = "STRING"
    description = "Model identifier"
  }

  labels {
    key         = "severity"
    value_type  = "STRING"
    description = "Severity level: CRITICAL, HIGH, MEDIUM, LOW, PASS"
  }
}

resource "google_monitoring_metric_descriptor" "audit_count" {
  project      = var.project_id
  description  = "FairOps audit execution count"
  display_name = "FairOps Audit Count"
  type         = "custom.googleapis.com/fairops/audit_count"
  metric_kind  = "CUMULATIVE"
  value_type   = "INT64"

  labels {
    key         = "model_id"
    value_type  = "STRING"
    description = "Model identifier"
  }
}

resource "google_monitoring_metric_descriptor" "mitigation_count" {
  project      = var.project_id
  description  = "FairOps mitigation pipeline execution count"
  display_name = "FairOps Mitigation Count"
  type         = "custom.googleapis.com/fairops/mitigation_count"
  metric_kind  = "CUMULATIVE"
  value_type   = "INT64"

  labels {
    key         = "model_id"
    value_type  = "STRING"
    description = "Model identifier"
  }

  labels {
    key         = "status"
    value_type  = "STRING"
    description = "Mitigation status"
  }
}

# ── Alert Policy: CRITICAL Bias ──────────────────────────────────────────────

resource "google_monitoring_alert_policy" "critical_bias" {
  project      = var.project_id
  display_name = "FairOps Critical Bias Detected"
  combiner     = "OR"

  conditions {
    display_name = "Critical severity gauge > 0"

    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/fairops/bias_severity\" AND metric.labels.severity=\"CRITICAL\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"

      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = var.slack_notification_channel_id != "" ? [var.slack_notification_channel_id] : []

  alert_strategy {
    auto_close = "604800s" # 7 days
  }
}
