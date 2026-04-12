"""
Shared — OpenTelemetry Distributed Tracing.

Provides request tracing across all FairOps services using
OpenTelemetry with GCP Cloud Trace exporter.

Ref: AGENT.md Section 3.
"""

import os
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource


def setup_tracing(service_name: str) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing for a service.

    In production (GCP), exports to Cloud Trace.
    In local dev, exports to console.

    Args:
        service_name: Name of the service.

    Returns:
        Configured Tracer instance.
    """
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "fairops",
            "deployment.environment": os.environ.get("ENV", "development"),
        }
    )

    provider = TracerProvider(resource=resource)

    if os.environ.get("K_SERVICE"):
        # Running on Cloud Run — use GCP Cloud Trace exporter
        try:
            from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter

            exporter = CloudTraceSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(exporter))
        except ImportError:
            # Fallback to console if GCP exporter not available
            provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
    else:
        # Local dev: console output
        provider.add_span_processor(
            BatchSpanProcessor(ConsoleSpanExporter())
        )

    trace.set_tracer_provider(provider)

    return trace.get_tracer(service_name)


def get_tracer(service_name: str) -> trace.Tracer:
    """Get a tracer for the given service name."""
    return trace.get_tracer(service_name)
