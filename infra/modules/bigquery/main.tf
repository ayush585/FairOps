# ==============================================================================
# FairOps — BigQuery Module
# 3 datasets + 5 tables with DDL from AGENT.md Section 10
# ==============================================================================

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

# ── Datasets ─────────────────────────────────────────────────────────────────

resource "google_bigquery_dataset" "raw" {
  dataset_id = "fairops_raw"
  project    = var.project_id
  location   = var.region

  labels = {
    env     = "production"
    service = "fairops"
  }
}

resource "google_bigquery_dataset" "enriched" {
  dataset_id = "fairops_enriched"
  project    = var.project_id
  location   = var.region

  labels = {
    env     = "production"
    service = "fairops"
  }
}

resource "google_bigquery_dataset" "metrics" {
  dataset_id = "fairops_metrics"
  project    = var.project_id
  location   = var.region

  labels = {
    env     = "production"
    service = "fairops"
  }
}

# ── Tables: fairops_raw ──────────────────────────────────────────────────────

resource "google_bigquery_table" "predictions" {
  dataset_id = google_bigquery_dataset.raw.dataset_id
  table_id   = "predictions"
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["model_id", "prediction_label"]

  schema = jsonencode([
    { name = "event_id",             type = "STRING",    mode = "REQUIRED" },
    { name = "model_id",             type = "STRING",    mode = "REQUIRED" },
    { name = "model_version",        type = "STRING",    mode = "REQUIRED" },
    { name = "timestamp",            type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "features",             type = "JSON",      mode = "NULLABLE" },
    { name = "prediction_label",     type = "STRING",    mode = "NULLABLE" },
    { name = "prediction_score",     type = "FLOAT64",   mode = "NULLABLE" },
    { name = "prediction_threshold", type = "FLOAT64",   mode = "NULLABLE" },
    { name = "ground_truth",         type = "STRING",    mode = "NULLABLE" },
    { name = "demographic_tags",     type = "STRING",    mode = "REPEATED" },
    { name = "tenant_id",            type = "STRING",    mode = "NULLABLE" },
    { name = "use_case",             type = "STRING",    mode = "NULLABLE" },
    { name = "ingested_at",          type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  deletion_protection = false
}

# ── Tables: fairops_enriched ─────────────────────────────────────────────────

resource "google_bigquery_table" "demographics" {
  dataset_id = google_bigquery_dataset.enriched.dataset_id
  table_id   = "demographics"
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "timestamp"
  }

  clustering = ["model_id"]

  schema = jsonencode([
    { name = "event_id",            type = "STRING",    mode = "REQUIRED" },
    { name = "model_id",            type = "STRING",    mode = "REQUIRED" },
    { name = "timestamp",           type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "gender_distribution", type = "JSON",      mode = "NULLABLE" },
    { name = "race_distribution",   type = "JSON",      mode = "NULLABLE" },
    { name = "age_bin",             type = "STRING",    mode = "NULLABLE" },
    { name = "income_bracket",      type = "STRING",    mode = "NULLABLE" },
    { name = "proxy_quality_score", type = "FLOAT64",   mode = "NULLABLE" },
    { name = "is_proxy",            type = "BOOL",      mode = "NULLABLE" },
    { name = "zip_code",            type = "STRING",    mode = "NULLABLE" },
    { name = "enriched_at",         type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  deletion_protection = false
}

# ── Tables: fairops_metrics ──────────────────────────────────────────────────

resource "google_bigquery_table" "bias_audits" {
  dataset_id = google_bigquery_dataset.metrics.dataset_id
  table_id   = "bias_audits"
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "audit_timestamp"
  }

  clustering = ["model_id", "overall_severity"]

  schema = jsonencode([
    { name = "audit_id",             type = "STRING",    mode = "REQUIRED" },
    { name = "model_id",             type = "STRING",    mode = "REQUIRED" },
    { name = "model_version",        type = "STRING",    mode = "NULLABLE" },
    { name = "audit_timestamp",      type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "window_start",         type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "window_end",           type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "sample_size",          type = "INT64",     mode = "NULLABLE" },
    { name = "overall_severity",     type = "STRING",    mode = "NULLABLE" },
    { name = "metrics",              type = "JSON",      mode = "NULLABLE" },
    { name = "demographic_slices",   type = "JSON",      mode = "NULLABLE" },
    { name = "protected_attributes", type = "STRING",    mode = "REPEATED" },
    { name = "triggered_mitigation", type = "BOOL",      mode = "NULLABLE" },
    { name = "mitigation_id",        type = "STRING",    mode = "NULLABLE" },
    { name = "created_at",           type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  deletion_protection = false
}

resource "google_bigquery_table" "mitigation_log" {
  dataset_id = google_bigquery_dataset.metrics.dataset_id
  table_id   = "mitigation_log"
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "triggered_at"
  }

  clustering = ["model_id", "status"]

  schema = jsonencode([
    { name = "mitigation_id",          type = "STRING",    mode = "REQUIRED" },
    { name = "audit_id",               type = "STRING",    mode = "REQUIRED" },
    { name = "model_id",               type = "STRING",    mode = "REQUIRED" },
    { name = "model_version_before",   type = "STRING",    mode = "NULLABLE" },
    { name = "model_version_after",    type = "STRING",    mode = "NULLABLE" },
    { name = "triggered_at",           type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "algorithm_used",         type = "STRING",    mode = "NULLABLE" },
    { name = "stage",                  type = "STRING",    mode = "NULLABLE" },
    { name = "metrics_before",         type = "JSON",      mode = "NULLABLE" },
    { name = "metrics_after",          type = "JSON",      mode = "NULLABLE" },
    { name = "accuracy_before",        type = "FLOAT64",   mode = "NULLABLE" },
    { name = "accuracy_after",         type = "FLOAT64",   mode = "NULLABLE" },
    { name = "accuracy_delta",         type = "FLOAT64",   mode = "NULLABLE" },
    { name = "status",                 type = "STRING",    mode = "NULLABLE" },
    { name = "promoted_to_production", type = "BOOL",      mode = "NULLABLE" },
    { name = "vertex_pipeline_run_id", type = "STRING",    mode = "NULLABLE" },
    { name = "created_at",             type = "TIMESTAMP", mode = "NULLABLE" },
  ])

  deletion_protection = false
}

resource "google_bigquery_table" "fairness_timeseries" {
  dataset_id = google_bigquery_dataset.metrics.dataset_id
  table_id   = "fairness_timeseries"
  project    = var.project_id

  time_partitioning {
    type  = "DAY"
    field = "recorded_at"
  }

  clustering = ["model_id", "metric_name"]

  schema = jsonencode([
    { name = "model_id",     type = "STRING",    mode = "REQUIRED" },
    { name = "metric_name",  type = "STRING",    mode = "REQUIRED" },
    { name = "metric_value", type = "FLOAT64",   mode = "NULLABLE" },
    { name = "severity",     type = "STRING",    mode = "NULLABLE" },
    { name = "recorded_at",  type = "TIMESTAMP", mode = "REQUIRED" },
  ])

  deletion_protection = false
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "dataset_raw_id" {
  value = google_bigquery_dataset.raw.dataset_id
}

output "dataset_enriched_id" {
  value = google_bigquery_dataset.enriched.dataset_id
}

output "dataset_metrics_id" {
  value = google_bigquery_dataset.metrics.dataset_id
}
