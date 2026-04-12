"""
Shared — Structured Cloud Logging.

Every service MUST use this. Zero print() statements anywhere.
All log entries include event_type, model_id, request_id for
structured filtering in Cloud Logging.

Ref: AGENT.md Section 16.
"""

import json
import logging
import os
import sys


def setup_logging(service_name: str) -> logging.Logger:
    """
    Initialize structured Cloud Logging for a service.

    In production (on GCP), uses google.cloud.logging for structured output.
    In local dev, falls back to standard logging with JSON formatting.

    Args:
        service_name: Name of the service (e.g., "fairops-auditor").

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers on re-initialization
    if logger.handlers:
        return logger

    # Use Cloud Logging in production, JSON to stdout in local dev
    if os.environ.get("K_SERVICE"):
        # Running on Cloud Run — use native Cloud Logging integration
        try:
            import google.cloud.logging

            client = google.cloud.logging.Client()
            client.setup_logging()
            logger.info(f"Cloud Logging initialized for {service_name}")
            return logger
        except Exception:
            pass  # Fall through to local logging

    # Local dev: JSON-formatted logs to stdout
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)

    class JsonFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "severity": record.levelname,
                "message": record.getMessage(),
                "service": service_name,
                "timestamp": self.formatTime(record),
            }
            if hasattr(record, "extra_fields"):
                log_entry.update(record.extra_fields)
            if record.exc_info and record.exc_info[0]:
                log_entry["exception"] = self.formatException(record.exc_info)
            return json.dumps(log_entry)

    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)

    return logger


def log_event(
    logger: logging.Logger,
    event_type: str,
    model_id: str,
    request_id: str,
    **kwargs,
) -> None:
    """
    Log a structured event with mandatory context fields.

    Every log entry in FairOps MUST include event_type, model_id,
    and request_id. These become structured filter fields in Cloud Logging.

    Args:
        logger: Logger instance from setup_logging().
        event_type: Event type (e.g., "AUDIT_STARTED", "METRIC_COMPUTED").
        model_id: The model being processed.
        request_id: Unique request identifier for tracing.
        **kwargs: Additional structured fields.
    """
    logger.info(
        json.dumps(
            {
                "event_type": event_type,
                "model_id": model_id,
                "request_id": request_id,
                **kwargs,
            }
        )
    )


def log_error(
    logger: logging.Logger,
    event_type: str,
    model_id: str,
    request_id: str,
    error: Exception,
    **kwargs,
) -> None:
    """
    Log an error event with full stack trace.

    AGENT.md Rule #5: Fail loudly. No silent exception swallowing.

    Args:
        logger: Logger instance.
        event_type: Error event type (e.g., "AUDIT_FAILED").
        model_id: The model being processed.
        request_id: Request identifier.
        error: The exception instance.
        **kwargs: Additional context.
    """
    logger.error(
        json.dumps(
            {
                "event_type": event_type,
                "model_id": model_id,
                "request_id": request_id,
                "error_type": type(error).__name__,
                "error_message": str(error),
                **kwargs,
            }
        ),
        exc_info=True,
    )
