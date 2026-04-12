"""
Stream Processor Transform — Schema Validation.

Validates incoming JSON against the PredictionEvent schema.
Malformed events are routed to the dead-letter output.

Ref: AGENT.md Sprint 1.
"""

import json
import logging
from datetime import datetime, timezone

import apache_beam as beam
from pydantic import ValidationError

# Import schemas from SDK — single source of truth
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))
from fairops_sdk.schemas import PredictionEvent

logger = logging.getLogger("fairops.stream_processor.schema_validator")


class ValidateSchema(beam.DoFn):
    """
    Validates incoming prediction events against the PredictionEvent schema.

    Valid events are emitted to the main output.
    Invalid events are tagged and emitted to the 'dead_letter' output.
    """

    def process(self, element, *args, **kwargs):
        try:
            # Validate against Pydantic schema
            event = PredictionEvent.model_validate(element)

            # Flatten to BigQuery row format
            row = {
                "event_id": event.event_id,
                "model_id": event.model_id,
                "model_version": event.model_version,
                "timestamp": event.timestamp.isoformat(),
                "features": json.dumps(event.features),
                "prediction_label": event.prediction.label,
                "prediction_score": event.prediction.score,
                "prediction_threshold": event.prediction.threshold,
                "ground_truth": event.ground_truth,
                "demographic_tags": event.demographic_tags,
                "tenant_id": event.session_context.tenant_id,
                "use_case": event.session_context.use_case.value,
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }

            yield beam.pvalue.TaggedOutput("valid", row)

        except (ValidationError, Exception) as e:
            # Route invalid events to dead-letter
            dead_letter_record = {
                "original_message": json.dumps(element) if isinstance(element, dict) else str(element),
                "error_type": type(e).__name__,
                "error_message": str(e),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }

            logger.warning(
                f"Schema validation failed: {e}",
                extra={"error_type": type(e).__name__},
            )

            yield beam.pvalue.TaggedOutput("dead_letter", dead_letter_record)
