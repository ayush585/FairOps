"""
FairOps SDK — Pub/Sub Prediction Publisher.

Publishes PredictionEvent messages to Cloud Pub/Sub with batching
for high-throughput ingestion.

Ref: AGENT.md Section 1, Sprint 1.
"""

import json
import logging
from typing import Optional

from google.cloud import pubsub_v1
from google.api_core import retry as api_retry

from fairops_sdk.schemas import PredictionEvent

logger = logging.getLogger("fairops.sdk.publisher")


class PredictionPublisher:
    """
    Publishes PredictionEvent messages to Cloud Pub/Sub.

    Uses batching for throughput: up to 100 messages or 1MB per batch,
    flushed every 0.1 seconds.
    """

    def __init__(
        self,
        project_id: str,
        topic_id: str = "fairops-predictions-ingest",
        batch_max_messages: int = 100,
        batch_max_bytes: int = 1_048_576,  # 1 MB
        batch_max_latency: float = 0.1,    # seconds
    ):
        self.project_id = project_id
        self.topic_path = f"projects/{project_id}/topics/{topic_id}"

        batch_settings = pubsub_v1.types.BatchSettings(
            max_messages=batch_max_messages,
            max_bytes=batch_max_bytes,
            max_latency=batch_max_latency,
        )

        self._publisher = pubsub_v1.PublisherClient(
            batch_settings=batch_settings,
        )
        self._futures: list = []

        logger.info(
            "PredictionPublisher initialized",
            extra={"topic": self.topic_path, "project_id": project_id},
        )

    def publish(
        self,
        event: PredictionEvent,
        ordering_key: Optional[str] = None,
    ) -> str:
        """
        Publish a single PredictionEvent to Pub/Sub.

        Args:
            event: Validated PredictionEvent instance.
            ordering_key: Optional ordering key for message ordering.

        Returns:
            Published message ID.

        Raises:
            google.api_core.exceptions.GoogleAPIError: On publish failure.
        """
        data = event.model_dump_json().encode("utf-8")

        # Pub/Sub attributes for filtering and routing
        attributes = {
            "model_id": event.model_id,
            "model_version": event.model_version,
            "tenant_id": event.session_context.tenant_id,
            "use_case": event.session_context.use_case.value,
            "event_id": event.event_id,
        }

        kwargs = {"data": data, **attributes}
        if ordering_key:
            kwargs["ordering_key"] = ordering_key

        future = self._publisher.publish(
            self.topic_path,
            **kwargs,
        )
        self._futures.append(future)

        # Get message ID (blocks until publish completes)
        message_id = future.result(timeout=30)

        logger.info(
            "Published prediction event",
            extra={
                "event_id": event.event_id,
                "model_id": event.model_id,
                "message_id": message_id,
            },
        )

        return message_id

    def publish_batch(self, events: list[PredictionEvent]) -> list[str]:
        """
        Publish a batch of PredictionEvents.

        Args:
            events: List of validated PredictionEvent instances.

        Returns:
            List of published message IDs.
        """
        if len(events) > 500:
            raise ValueError(
                f"Batch size {len(events)} exceeds maximum of 500. "
                "Split into smaller batches."
            )

        message_ids = []
        for event in events:
            msg_id = self.publish(event)
            message_ids.append(msg_id)

        logger.info(
            "Published prediction event batch",
            extra={"batch_size": len(events), "published": len(message_ids)},
        )

        return message_ids

    def flush(self) -> None:
        """Flush all pending messages. Call before shutdown."""
        for future in self._futures:
            try:
                future.result(timeout=60)
            except Exception as e:
                logger.error(f"Failed to flush message: {e}", exc_info=True)
        self._futures.clear()
        logger.info("Publisher flushed all pending messages")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        return False
