# ==============================================================================
# FairOps — IAM Module
# 6 service accounts + all IAM bindings
# Ref: AGENT.md Section 2
# Zero service account key files. Workload Identity Federation only.
# ==============================================================================

variable "project_id" {
  type = string
}

# ── Service Accounts ─────────────────────────────────────────────────────────

resource "google_service_account" "stream_processor" {
  account_id   = "fairops-stream-processor"
  display_name = "FairOps Stream Processor"
  project      = var.project_id
}

resource "google_service_account" "auditor" {
  account_id   = "fairops-auditor"
  display_name = "FairOps Auditor"
  project      = var.project_id
}

resource "google_service_account" "explainer" {
  account_id   = "fairops-explainer"
  display_name = "FairOps Explainer"
  project      = var.project_id
}

resource "google_service_account" "mitigator" {
  account_id   = "fairops-mitigator"
  display_name = "FairOps Mitigator"
  project      = var.project_id
}

resource "google_service_account" "gateway" {
  account_id   = "fairops-gateway"
  display_name = "FairOps API Gateway"
  project      = var.project_id
}

resource "google_service_account" "notifier" {
  account_id   = "fairops-notifier"
  display_name = "FairOps Notifier"
  project      = var.project_id
}

# ── IAM Bindings ─────────────────────────────────────────────────────────────

# Stream Processor: BigQuery Data Editor, Pub/Sub Subscriber, DLP User
resource "google_project_iam_member" "stream_processor_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.stream_processor.email}"
}

resource "google_project_iam_member" "stream_processor_pubsub" {
  project = var.project_id
  role    = "roles/pubsub.subscriber"
  member  = "serviceAccount:${google_service_account.stream_processor.email}"
}

resource "google_project_iam_member" "stream_processor_dlp" {
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.stream_processor.email}"
}

# Auditor: BigQuery Data Editor, Spanner Database User, Cloud Run Invoker
resource "google_project_iam_member" "auditor_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.auditor.email}"
}

resource "google_project_iam_member" "auditor_spanner" {
  project = var.project_id
  role    = "roles/spanner.databaseUser"
  member  = "serviceAccount:${google_service_account.auditor.email}"
}

resource "google_project_iam_member" "auditor_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.auditor.email}"
}

# Explainer: BigQuery Data Viewer, Vertex AI User, Secret Manager Accessor
resource "google_project_iam_member" "explainer_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataViewer"
  member  = "serviceAccount:${google_service_account.explainer.email}"
}

resource "google_project_iam_member" "explainer_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.explainer.email}"
}

resource "google_project_iam_member" "explainer_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.explainer.email}"
}

# Mitigator: Vertex AI Pipelines Runner, BigQuery Data Editor, Storage Admin
resource "google_project_iam_member" "mitigator_vertex" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.mitigator.email}"
}

resource "google_project_iam_member" "mitigator_bq" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.mitigator.email}"
}

resource "google_project_iam_member" "mitigator_storage" {
  project = var.project_id
  role    = "roles/storage.admin"
  member  = "serviceAccount:${google_service_account.mitigator.email}"
}

# Gateway: Cloud Run Invoker (all services), Secret Manager Accessor
resource "google_project_iam_member" "gateway_run_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

resource "google_project_iam_member" "gateway_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.gateway.email}"
}

# Notifier: Secret Manager Accessor
resource "google_project_iam_member" "notifier_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.notifier.email}"
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "stream_processor_sa_email" {
  value = google_service_account.stream_processor.email
}

output "auditor_sa_email" {
  value = google_service_account.auditor.email
}

output "explainer_sa_email" {
  value = google_service_account.explainer.email
}

output "mitigator_sa_email" {
  value = google_service_account.mitigator.email
}

output "gateway_sa_email" {
  value = google_service_account.gateway.email
}

output "notifier_sa_email" {
  value = google_service_account.notifier.email
}
