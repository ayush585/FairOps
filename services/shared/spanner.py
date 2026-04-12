"""
Shared — Cloud Spanner Client Factory.

Provides Spanner client with batch write support for the
immutable audit ledger.

Ref: AGENT.md Section 11, 21.
CRITICAL: Use batch() context manager. Never single-row inserts in a loop.
"""

import os
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from google.cloud import spanner

logger = logging.getLogger("fairops.shared.spanner")

# Singleton instances
_spanner_client: Optional[spanner.Client] = None
_database = None


def get_spanner_client() -> spanner.Client:
    """Get or create a Spanner client singleton."""
    global _spanner_client
    if _spanner_client is None:
        project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
        _spanner_client = spanner.Client(project=project_id)
        logger.info(f"Spanner client initialized for project {project_id}")
    return _spanner_client


def get_database():
    """
    Get the FairOps audit ledger database instance.

    Returns:
        Spanner Database instance.
    """
    global _database
    if _database is None:
        client = get_spanner_client()
        instance_id = os.environ.get("SPANNER_INSTANCE_ID", "fairops-audit")
        database_id = os.environ.get("SPANNER_DATABASE_ID", "fairops-ledger")
        instance = client.instance(instance_id)
        _database = instance.database(database_id)
        logger.info(
            f"Spanner database connected: {instance_id}/{database_id}"
        )
    return _database


# Valid EventType values per AGENT.md Section 11
VALID_EVENT_TYPES = {
    "AUDIT_COMPLETED",
    "MITIGATION_TRIGGERED",
    "MITIGATION_COMPLETED",
    "MODEL_PROMOTED",
    "BIAS_ALERT_SENT",
}


def write_audit_event(
    event_type: str,
    model_id: str,
    tenant_id: str,
    payload: dict,
    actor_service_id: str,
    ip_address: Optional[str] = None,
) -> str:
    """
    Write an immutable audit event to Cloud Spanner.

    INSERT ONLY — zero UPDATE or DELETE ever issued.
    Ref: AGENT.md Section 11.

    Args:
        event_type: One of VALID_EVENT_TYPES.
        model_id: The model this event relates to.
        tenant_id: Tenant identifier.
        payload: JSON-serializable event payload.
        actor_service_id: Service that generated this event.
        ip_address: Optional IP address of the request.

    Returns:
        The generated EventId.

    Raises:
        ValueError: If event_type is not valid.
    """
    if event_type not in VALID_EVENT_TYPES:
        raise ValueError(
            f"Invalid event_type '{event_type}'. "
            f"Must be one of: {VALID_EVENT_TYPES}"
        )

    event_id = str(uuid4())
    database = get_database()

    def _insert(transaction):
        transaction.insert(
            table="AuditEvents",
            columns=[
                "EventId",
                "EventType",
                "ModelId",
                "TenantId",
                "EventTimestamp",
                "Payload",
                "ActorServiceId",
                "IpAddress",
            ],
            values=[
                [
                    event_id,
                    event_type,
                    model_id,
                    tenant_id,
                    datetime.now(timezone.utc),
                    payload,
                    actor_service_id,
                    ip_address,
                ]
            ],
        )

    database.run_in_transaction(_insert)

    logger.info(
        f"Audit event written to Spanner",
        extra={
            "event_id": event_id,
            "event_type": event_type,
            "model_id": model_id,
        },
    )

    return event_id


def write_audit_events_batch(events: list[dict]) -> list[str]:
    """
    Write multiple audit events in a single batch transaction.

    AGENT.md Section 21: Use batch() context manager.
    Never single-row inserts in a loop.

    Args:
        events: List of event dicts with keys matching write_audit_event params.

    Returns:
        List of generated EventIds.
    """
    database = get_database()
    event_ids = []

    columns = [
        "EventId",
        "EventType",
        "ModelId",
        "TenantId",
        "EventTimestamp",
        "Payload",
        "ActorServiceId",
        "IpAddress",
    ]

    values = []
    for event in events:
        if event["event_type"] not in VALID_EVENT_TYPES:
            raise ValueError(
                f"Invalid event_type '{event['event_type']}'. "
                f"Must be one of: {VALID_EVENT_TYPES}"
            )

        event_id = str(uuid4())
        event_ids.append(event_id)
        values.append(
            [
                event_id,
                event["event_type"],
                event["model_id"],
                event["tenant_id"],
                datetime.now(timezone.utc),
                event["payload"],
                event.get("actor_service_id", "unknown"),
                event.get("ip_address"),
            ]
        )

    with database.batch() as batch:
        batch.insert(
            table="AuditEvents",
            columns=columns,
            values=values,
        )

    logger.info(
        f"Batch audit events written to Spanner",
        extra={"count": len(event_ids)},
    )

    return event_ids
