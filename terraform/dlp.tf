# FairOps At-Rest Data Loss Prevention
# Asynchronous DLP Scanning of BigQuery Datasets

resource "google_data_loss_prevention_inspect_template" "fairops_at_rest_inspect" {
  parent       = "projects/fairops-prod/locations/global"
  description  = "Scan for all PII at rest in BigQuery beyond Name and SSN"
  display_name = "FairOps At-Rest Full PII Scan"

  inspect_config {
    info_types {
      name = "EMAIL_ADDRESS"
    }
    info_types {
      name = "PHONE_NUMBER"
    }
    info_types {
      name = "CREDIT_CARD_NUMBER"
    }
    info_types {
      name = "PASSPORT"
    }
    info_types {
      name = "STREET_ADDRESS"
    }
    
    # Do not specify PERSON_NAME or SSN, as they were stripped inline via SDK.
    
    min_likelihood = "LIKELY"
  }
}

resource "google_data_loss_prevention_job_trigger" "bigquery_pipeline_scanner" {
  parent       = "projects/fairops-prod/locations/global"
  description  = "Runs nightly sweeps of BigQuery predictions table for rogue PII"
  display_name = "FairOps Nightly BQ PII Scan"

  triggers {
    schedule {
      recurrence_period_duration = "86400s" # Daily
    }
  }

  inspect_job {
    inspect_template_name = google_data_loss_prevention_inspect_template.fairops_at_rest_inspect.id
    
    storage_config {
      big_query_options {
        table_reference {
          project_id = "fairops-prod"
          dataset_id = "fairops_raw"
          table_id   = "predictions"
        }
      }
    }

    actions {
      pub_sub {
        topic = "projects/fairops-prod/topics/dlp-alerts"
      }
    }
  }
}
