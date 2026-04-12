# ==============================================================================
# FairOps — Pub/Sub Module
# Topic + subscription + dead-letter
# Ref: AGENT.md Section 17
# ==============================================================================

variable "project_id" {
  type = string
}

# ── Dead Letter Topic ────────────────────────────────────────────────────────

resource "google_pubsub_topic" "dead_letter" {
  name                       = "fairops-predictions-dlq"
  project                    = var.project_id
  message_retention_duration = "604800s" # 7 days
}

resource "google_pubsub_subscription" "dead_letter_sub" {
  name    = "fairops-predictions-dlq-sub"
  topic   = google_pubsub_topic.dead_letter.name
  project = var.project_id

  ack_deadline_seconds = 60

  expiration_policy {
    ttl = "" # Never expires
  }
}

# ── Main Predictions Ingest Topic ────────────────────────────────────────────

resource "google_pubsub_topic" "predictions_ingest" {
  name                       = "fairops-predictions-ingest"
  project                    = var.project_id
  message_retention_duration = "604800s" # 7 days
}

resource "google_pubsub_subscription" "predictions_sub" {
  name    = "fairops-predictions-sub"
  topic   = google_pubsub_topic.predictions_ingest.name
  project = var.project_id

  ack_deadline_seconds = 60

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }

  expiration_policy {
    ttl = "" # Never expires
  }
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "topic_name" {
  value = google_pubsub_topic.predictions_ingest.name
}

output "topic_id" {
  value = google_pubsub_topic.predictions_ingest.id
}

output "subscription_name" {
  value = google_pubsub_subscription.predictions_sub.name
}

output "dead_letter_topic_name" {
  value = google_pubsub_topic.dead_letter.name
}
