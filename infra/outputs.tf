# ==============================================================================
# FairOps — Terraform Outputs
# ==============================================================================

output "pubsub_topic" {
  value = module.pubsub.topic_name
}

output "pubsub_subscription" {
  value = module.pubsub.subscription_name
}

output "bigquery_datasets" {
  value = {
    raw      = module.bigquery.dataset_raw_id
    enriched = module.bigquery.dataset_enriched_id
    metrics  = module.bigquery.dataset_metrics_id
  }
}

output "spanner_instance" {
  value = module.spanner.instance_id
}

output "spanner_database" {
  value = module.spanner.database_id
}

output "cloudrun_urls" {
  value = {
    gateway   = module.cloudrun.gateway_url
    auditor   = module.cloudrun.auditor_url
    explainer = module.cloudrun.explainer_url
    notifier  = module.cloudrun.notifier_url
  }
}

output "service_accounts" {
  value = {
    stream_processor = module.iam.stream_processor_sa_email
    auditor          = module.iam.auditor_sa_email
    explainer        = module.iam.explainer_sa_email
    mitigator        = module.iam.mitigator_sa_email
    gateway          = module.iam.gateway_sa_email
    notifier         = module.iam.notifier_sa_email
  }
}

output "vertex_pipeline_root" {
  value = module.vertex.pipeline_root_gcs
}
