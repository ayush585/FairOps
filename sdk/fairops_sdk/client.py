"""
FairOps SDK — Main Client Entry Point.

3-line integration for any deployed ML model:

    from fairops_sdk import FairOpsClient
    client = FairOpsClient("my-project", "my-model", "v1")
    client.log_prediction(features={...}, prediction={...})

Ref: AGENT.md Sprint 1.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fairops_sdk.publisher import PredictionPublisher
from fairops_sdk.schemas import (
    PredictionEvent,
    PredictionResult,
    SessionContext,
    UseCase,
)

logger = logging.getLogger("fairops.sdk.client")


class FairOpsClient:
    """
    Main FairOps SDK client. Provides a simple interface to log
    ML predictions for bias monitoring.

    Usage:
        client = FairOpsClient(
            project_id="fairops-prod",
            model_id="hiring-classifier",
            model_version="v2.1",
            use_case="hiring",
            tenant_id="acme-corp",
        )
        client.log_prediction(
            features={"age": 35, "sex": "Male", "education": "Bachelors"},
            prediction={"label": "approved", "score": 0.87, "threshold": 0.5},
            ground_truth="approved",
        )
    """

    def __init__(
        self,
        project_id: str,
        model_id: str,
        model_version: str,
        use_case: str = "hiring",
        tenant_id: str = "default",
        topic_id: str = "fairops-predictions-ingest",
    ):
        self.project_id = project_id
        self.model_id = model_id
        self.model_version = model_version
        self.use_case = UseCase(use_case)
        self.tenant_id = tenant_id

        self._publisher = PredictionPublisher(
            project_id=project_id,
            topic_id=topic_id,
        )

        logger.info(
            "FairOpsClient initialized",
            extra={
                "project_id": project_id,
                "model_id": model_id,
                "model_version": model_version,
            },
        )

    def log_prediction(
        self,
        features: dict[str, Any],
        prediction: dict[str, Any],
        ground_truth: Optional[str] = None,
        demographic_tags: Optional[list[str]] = None,
        timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Log a single prediction event for bias monitoring.

        Args:
            features: Input features dict (e.g., {"age": 35, "sex": "Male"}).
            prediction: Prediction result dict with keys: label, score, threshold.
            ground_truth: Optional ground truth label for accuracy tracking.
            demographic_tags: Optional pre-computed demographic tags.
            timestamp: Optional event timestamp (defaults to now UTC).

        Returns:
            The event_id of the published prediction event.
        """
        event = PredictionEvent(
            model_id=self.model_id,
            model_version=self.model_version,
            timestamp=timestamp or datetime.now(timezone.utc),
            features=features,
            prediction=PredictionResult(**prediction),
            ground_truth=ground_truth,
            demographic_tags=demographic_tags or [],
            session_context=SessionContext(
                tenant_id=self.tenant_id,
                use_case=self.use_case,
            ),
        )

        self._publisher.publish(event)

        logger.debug(
            "Prediction logged",
            extra={"event_id": event.event_id, "model_id": self.model_id},
        )

        return event.event_id

    def log_predictions_batch(
        self,
        predictions: list[dict[str, Any]],
    ) -> list[str]:
        """
        Log a batch of prediction events.

        Args:
            predictions: List of dicts, each containing:
                - features: dict
                - prediction: dict (label, score, threshold)
                - ground_truth: Optional[str]
                - demographic_tags: Optional[list[str]]
                - timestamp: Optional[datetime]

        Returns:
            List of event_ids.
        """
        events = []
        for pred_data in predictions:
            event = PredictionEvent(
                model_id=self.model_id,
                model_version=self.model_version,
                timestamp=pred_data.get("timestamp", datetime.now(timezone.utc)),
                features=pred_data["features"],
                prediction=PredictionResult(**pred_data["prediction"]),
                ground_truth=pred_data.get("ground_truth"),
                demographic_tags=pred_data.get("demographic_tags", []),
                session_context=SessionContext(
                    tenant_id=self.tenant_id,
                    use_case=self.use_case,
                ),
            )
            events.append(event)

        self._publisher.publish_batch(events)

        return [e.event_id for e in events]

    def flush(self) -> None:
        """Flush all pending messages. Call before shutdown."""
        self._publisher.flush()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush()
        return False
