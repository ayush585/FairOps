# ==============================================================================
# FairOps — Cloud Spanner Module
# Immutable audit ledger
# Ref: AGENT.md Sections 11, 17
# ==============================================================================

variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

resource "google_spanner_instance" "audit_ledger" {
  name         = "fairops-audit"
  config       = "regional-${var.region}"
  display_name = "FairOps Immutable Audit Ledger"
  num_nodes    = 1
  project      = var.project_id
}

resource "google_spanner_database" "fairops_ledger" {
  instance            = google_spanner_instance.audit_ledger.name
  name                = "fairops-ledger"
  project             = var.project_id
  deletion_protection = true

  ddl = [
    <<-SQL
      CREATE TABLE AuditEvents (
          EventId        STRING(36)  NOT NULL,
          EventType      STRING(50)  NOT NULL,
          ModelId        STRING(100) NOT NULL,
          TenantId       STRING(100) NOT NULL,
          EventTimestamp TIMESTAMP   NOT NULL,
          Payload        JSON        NOT NULL,
          ActorServiceId STRING(100),
          IpAddress      STRING(50),
      ) PRIMARY KEY (EventId)
    SQL
    ,
    "CREATE INDEX AuditEventsByModel ON AuditEvents (ModelId, EventTimestamp DESC)",
    "CREATE INDEX AuditEventsByTenant ON AuditEvents (TenantId, EventTimestamp DESC)",
  ]
}

# ── Outputs ──────────────────────────────────────────────────────────────────

output "instance_id" {
  value = google_spanner_instance.audit_ledger.name
}

output "database_id" {
  value = google_spanner_database.fairops_ledger.name
}
