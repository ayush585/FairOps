# ==============================================================================
# FairOps — Terraform Root Configuration
# All GCP resources as code. AGENT.md Rule #7.
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.10"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.10"
    }
  }

  # Remote state in GCS — create this bucket manually first
  backend "gcs" {
    bucket = "fairops-terraform-state"
    prefix = "terraform/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# ── Enable Required APIs ─────────────────────────────────────────────────────

resource "google_project_service" "apis" {
  for_each = toset([
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "bigquery.googleapis.com",
    "bigquerystorage.googleapis.com",
    "aiplatform.googleapis.com",
    "run.googleapis.com",
    "spanner.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudscheduler.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "cloudkms.googleapis.com",
    "artifactregistry.googleapis.com",
    "iamcredentials.googleapis.com",
    "cloudtasks.googleapis.com",
  ])

  project = var.project_id
  service = each.value

  disable_on_destroy = false
}

# ── Artifact Registry ────────────────────────────────────────────────────────

resource "google_artifact_registry_repository" "fairops" {
  location      = var.region
  repository_id = "fairops"
  description   = "FairOps container images"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

# ── Modules ──────────────────────────────────────────────────────────────────

module "iam" {
  source     = "./modules/iam"
  project_id = var.project_id

  depends_on = [google_project_service.apis]
}

module "pubsub" {
  source     = "./modules/pubsub"
  project_id = var.project_id

  depends_on = [google_project_service.apis]
}

module "bigquery" {
  source     = "./modules/bigquery"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "spanner" {
  source     = "./modules/spanner"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "vertex" {
  source     = "./modules/vertex"
  project_id = var.project_id
  region     = var.region

  depends_on = [google_project_service.apis]
}

module "cloudrun" {
  source     = "./modules/cloudrun"
  project_id = var.project_id
  region     = var.region

  gateway_sa_email   = module.iam.gateway_sa_email
  auditor_sa_email   = module.iam.auditor_sa_email
  explainer_sa_email = module.iam.explainer_sa_email
  notifier_sa_email  = module.iam.notifier_sa_email

  depends_on = [
    google_project_service.apis,
    google_artifact_registry_repository.fairops,
    module.iam,
  ]
}

module "scheduler" {
  source     = "./modules/scheduler"
  project_id = var.project_id
  region     = var.region

  auditor_url      = module.cloudrun.auditor_url
  auditor_sa_email = module.iam.auditor_sa_email

  depends_on = [
    google_project_service.apis,
    module.cloudrun,
  ]
}

module "monitoring" {
  source     = "./modules/monitoring"
  project_id = var.project_id

  slack_notification_channel_id = var.slack_notification_channel_id

  depends_on = [google_project_service.apis]
}
