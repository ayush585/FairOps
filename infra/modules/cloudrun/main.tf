# ==============================================================================
# FairOps — Cloud Run Module
# 4 Cloud Run services: gateway, auditor, explainer, notifier
# Ref: AGENT.md Section 18
# ==============================================================================

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "gateway_sa_email" {
  type = string
}

variable "auditor_sa_email" {
  type = string
}

variable "explainer_sa_email" {
  type = string
}

variable "notifier_sa_email" {
  type = string
}

# ── Gateway ──────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "gateway" {
  name     = "fairops-gateway"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.gateway_sa_email

    scaling {
      min_instance_count = 1
      max_instance_count = 100
    }

    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/fairops/gateway:latest"

      resources {
        limits = {
          memory = "2Gi"
          cpu    = "2"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "K_SERVICE"
        value = "fairops-gateway"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# ── Auditor ──────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "auditor" {
  name     = "fairops-auditor"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.auditor_sa_email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/fairops/auditor:latest"

      resources {
        limits = {
          memory = "4Gi"
          cpu    = "4"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# ── Explainer ────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "explainer" {
  name     = "fairops-explainer"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.explainer_sa_email
    timeout         = "300s"

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/fairops/explainer:latest"

      resources {
        limits = {
          memory = "4Gi"
          cpu    = "4"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# ── Notifier ─────────────────────────────────────────────────────────────────

resource "google_cloud_run_v2_service" "notifier" {
  name     = "fairops-notifier"
  location = var.region
  project  = var.project_id

  template {
    service_account = var.notifier_sa_email

    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "us-central1-docker.pkg.dev/${var.project_id}/fairops/notifier:latest"

      resources {
        limits = {
          memory = "1Gi"
          cpu    = "1"
        }
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].containers[0].image,
    ]
  }
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "gateway_url" {
  value = google_cloud_run_v2_service.gateway.uri
}

output "auditor_url" {
  value = google_cloud_run_v2_service.auditor.uri
}

output "explainer_url" {
  value = google_cloud_run_v2_service.explainer.uri
}

output "notifier_url" {
  value = google_cloud_run_v2_service.notifier.uri
}
