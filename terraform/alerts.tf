# FairOps Alerting Policies
# Defines a Google Cloud Monitoring Alert that triggers on high bias classifications.

resource "google_monitoring_notification_channel" "slack_channel" {
  display_name = "FairOps Slack Compliance Notify"
  type         = "slack"
  labels = {
    "channel_name" = "#ai-compliance"
  }
}

resource "google_monitoring_alert_policy" "bias_severity_alert" {
  display_name = "Model Bias Severity Exceeded CRITICAL Level"
  combiner     = "OR"
  
  conditions {
    display_name = "CRITICAL Bias Found"
    
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/fairops/bias_severity\" AND resource.type=\"generic_task\""
      duration        = "300s" # 5 minutes sliding window
      comparison      = "COMPARISON_GT"
      threshold_value = 3 # 4 = CRITICAL
      
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_MAX"
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.slack_channel.name,
  ]

  user_labels = {
    severity = "critical"
  }

  documentation {
    content = <<-EOT
      🚨 **FairOps Alert: CRITICAL AI Bias Detected!** 🚨
      
      The FairOps Auditor pipeline has detected a CRITICAL severity bias rating for a model 
      within the last 5 minutes. 
      
      **Details:**
      - **Metric Type:** custom.googleapis.com/fairops/bias_severity > 3
      - **Review Dashboard:** [Looker Studio Link]
      - **Incident Response:** Follow AI Incident Playbook Section C.
      
      *Action Required:* The Mitigation process should have already automatically spun up a 
      Vertex AI Retraining Job. Please verify the progress in GCP.
    EOT
    mime_type = "text/markdown"
  }
}
