"""
Stream Processor Transform — Dead Letter Handler.

Routes schema validation failures to the Pub/Sub dead-letter topic
for manual inspection and reprocessing.

Ref: AGENT.md Sprint 1.
"""

import json
import logging

import apache_beam as beam
from google.cloud import pubsub_v1

logger = logging.getLogger("fairops.stream_processor.dead_letter")


class WriteToDeadLetter(beam.DoFn):
    """
    Publishes failed messages to the dead-letter Pub/Sub topic.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._publisher = None
        self._topic_path = None

    def setup(self):
        """Initialize Pub/Sub publisher (called once per worker)."""
        self._publisher = pubsub_v1.PublisherClient()
        self._topic_path = self._publisher.topic_path(
            self.project_id, "fairops-predictions-dlq"
        )
        logger.info(f"Dead letter publisher initialized: {self._topic_path}")

    def process(self, element, *args, **kwargs):
        try:
            message_data = json.dumps(element).encode("utf-8")

            future = self._publisher.publish(
                self._topic_path,
                data=message_data,
                error_type=element.get("error_type", "unknown"),
            )
            future.result(timeout=10)

            logger.info(
                "Dead-letter message published",
                extra={"error_type": element.get("error_type")},
            )

        except Exception as e:
            # Last resort: log the failed message
            logger.error(
                f"Failed to publish to dead-letter topic: {e}",
                extra={"message": str(element)[:500]},
                exc_info=True,
            )

    def teardown(self):
        """Cleanup publisher."""
        if self._publisher:
            self._publisher = None
