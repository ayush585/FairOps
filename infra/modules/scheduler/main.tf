# ==============================================================================
# FairOps — Cloud Scheduler Module
# Audit trigger every 15 minutes
# Ref: AGENT.md Section 17
# ==============================================================================

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "auditor_url" {
  type = string
}

variable "auditor_sa_email" {
  type = string
}

resource "google_cloud_scheduler_job" "audit_trigger" {
  name      = "fairops-audit-trigger"
  schedule  = "*/15 * * * *"
  time_zone = "UTC"
  project   = var.project_id
  region    = var.region

  http_target {
    uri         = "${var.auditor_url}/v1/models/default/audit"
    http_method = "POST"
    body        = base64encode(jsonencode({
      window_hours         = 1
      protected_attributes = ["sex", "race"]
    }))
    headers = {
      "Content-Type" = "application/json"
    }

    oidc_token {
      service_account_email = var.auditor_sa_email
    }
  }

  retry_config {
    retry_count          = 3
    min_backoff_duration = "10s"
    max_backoff_duration = "300s"
  }
}
