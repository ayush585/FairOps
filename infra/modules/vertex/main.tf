# ==============================================================================
# FairOps — Vertex AI Module
# Pipeline root GCS bucket + metadata store
# Ref: AGENT.md Section 9
# ==============================================================================

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

resource "google_storage_bucket" "pipeline_root" {
  name          = "fairops-pipelines-${var.project_id}"
  location      = var.region
  project       = var.project_id
  force_destroy = false

  uniform_bucket_level_access = true

  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      age = 90
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_vertex_ai_metadata_store" "fairops" {
  provider    = google-beta
  project     = var.project_id
  region      = var.region
  description = "FairOps pipeline metadata store"
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "pipeline_root_gcs" {
  value = "gs://${google_storage_bucket.pipeline_root.name}/"
}

output "pipeline_bucket_name" {
  value = google_storage_bucket.pipeline_root.name
}
