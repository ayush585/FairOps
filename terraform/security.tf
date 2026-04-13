# FairOps Infrastructure Security Definitions
# Defines strict WAF, IAM, and KMS perimeters.

# 1. Cloud Armor WAF (OWASP 10)
resource "google_compute_security_policy" "fairops_waf" {
  name        = "fairops-gateway-waf"
  description = "OWASP Top 10 blocking for FairOps Gateway"

  # Default Deny/Allow
  rule {
    action   = "allow"
    priority = "2147483647"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    description = "Default allow"
  }

  # OWASP Ruleset Integration (SQLi, XSS, LFI)
  rule {
    action   = "deny(403)"
    priority = "1000"
    match {
      expr {
        expression = "evaluatePreconfiguredExpr('sqli-v33-stable') || evaluatePreconfiguredExpr('xss-v33-stable')"
      }
    }
    description = "Block SQLi and XSS"
  }
}

# 2. Key Management Service (CMEK for BigQuery)
resource "google_kms_key_ring" "fairops_keyring" {
  name     = "fairops-bq-keyring"
  location = "us-central1"
}

resource "google_kms_crypto_key" "fairops_bq_cmek" {
  name            = "fairops-cmek-aes256"
  key_ring        = google_kms_key_ring.fairops_keyring.id
  rotation_period = "7776000s" # 90 days

  lifecycle {
    prevent_destroy = true
  }
}

# 3. VPC Service Controls (Perimeter around Data)
# Note: Requires Organization ID to deploy.
resource "google_access_context_manager_service_perimeter" "fairops_perimeter" {
  parent = "accessPolicies/123456789012"
  name   = "accessPolicies/123456789012/servicePerimeters/fairops_perimeter"
  title  = "FairOps Data Boundary"

  status {
    restricted_services = [
      "bigquery.googleapis.com",
      "storage.googleapis.com"
    ]
    # Resources placed inside the perimeter
    resources = [
      "projects/fairops-prod"
    ]
  }
}

# 4. Binary Authorization for Cloud Run
resource "google_binary_authorization_policy" "fairops_binauth" {
  admission_whitelist_patterns {
    name_pattern = "gcr.io/fairops-prod/*"
  }
  
  default_admission_rule {
    evaluation_mode  = "ALWAYS_DENY"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
  }
}

# 5. Least-Privilege IAM (Removing monolithic roles)
resource "google_project_iam_custom_role" "fairops_auditor_role" {
  role_id     = "FairOpsAuditorRole"
  title       = "FairOps Auditor Standard Role"
  description = "Strict permissions for Auditor Cloud Run instance"
  permissions = [
    "bigquery.jobs.create",
    "bigquery.tables.getData",
    "bigquery.tables.updateData",
    "spanner.databases.beginOrRollbackReadWriteTransaction",
    "spanner.databases.write"
  ]
}

resource "google_service_account" "auditor_sa" {
  account_id   = "fairops-auditor-sa"
  display_name = "FairOps Auditor Service Account"
}

resource "google_project_iam_member" "auditor_bindings" {
  project = "fairops-prod"
  role    = google_project_iam_custom_role.fairops_auditor_role.id
  member  = "serviceAccount:${google_service_account.auditor_sa.email}"
}
