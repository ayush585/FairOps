"""
FairOps Auditor — Cloud Spanner Writer.

Writes AUDIT_COMPLETED events to the immutable audit ledger.

Ref: AGENT.md Section 11 — INSERT ONLY. Zero UPDATE or DELETE.
"""

import json
import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))

from shared.spanner import write_audit_event
from fairops_sdk.schemas import BiasAuditResult

logger = logging.getLogger("fairops.auditor.spanner_writer")


def write_audit_completed(
    audit: BiasAuditResult,
    tenant_id: str = "default",
) -> str:
    """
    Write an AUDIT_COMPLETED event to Cloud Spanner.

    INSERT ONLY — this is an immutable audit trail.

    Args:
        audit: The completed audit result.
        tenant_id: Tenant identifier.

    Returns:
        The EventId of the created audit event.
    """
    payload = {
        "audit_id": audit.audit_id,
        "model_id": audit.model_id,
        "model_version": audit.model_version,
        "audit_timestamp": audit.audit_timestamp.isoformat(),
        "sample_size": audit.sample_size,
        "overall_severity": audit.overall_severity.value,
        "breached_metrics": [
            name for name, m in audit.metrics.items() if m.breached
        ],
        "triggered_mitigation": audit.triggered_mitigation,
        "mitigation_id": audit.mitigation_id,
    }

    event_id = write_audit_event(
        event_type="AUDIT_COMPLETED",
        model_id=audit.model_id,
        tenant_id=tenant_id,
        payload=payload,
        actor_service_id="fairops-auditor",
    )

    logger.info(
        f"AUDIT_COMPLETED event written to Spanner",
        extra={
            "event_id": event_id,
            "audit_id": audit.audit_id,
            "model_id": audit.model_id,
            "severity": audit.overall_severity.value,
        },
    )

    return event_id


def write_mitigation_triggered(
    audit: BiasAuditResult,
    mitigation_id: str,
    algorithm: str,
    tenant_id: str = "default",
) -> str:
    """
    Write a MITIGATION_TRIGGERED event to Cloud Spanner.

    Args:
        audit: The audit that triggered mitigation.
        mitigation_id: ID of the initiated mitigation.
        algorithm: Selected mitigation algorithm.
        tenant_id: Tenant identifier.

    Returns:
        The EventId of the created event.
    """
    payload = {
        "audit_id": audit.audit_id,
        "mitigation_id": mitigation_id,
        "model_id": audit.model_id,
        "severity": audit.overall_severity.value,
        "algorithm": algorithm,
        "breached_metrics": [
            name for name, m in audit.metrics.items() if m.breached
        ],
    }

    event_id = write_audit_event(
        event_type="MITIGATION_TRIGGERED",
        model_id=audit.model_id,
        tenant_id=tenant_id,
        payload=payload,
        actor_service_id="fairops-auditor",
    )

    logger.info(
        f"MITIGATION_TRIGGERED event written to Spanner",
        extra={
            "event_id": event_id,
            "mitigation_id": mitigation_id,
            "algorithm": algorithm,
        },
    )

    return event_id
