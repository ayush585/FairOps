"""
FairOps Stream Processor — Apache Beam Pipeline.

Reads prediction events from Pub/Sub, validates, enriches with
demographics, redacts PII via Cloud DLP, and writes to BigQuery.

Ref: AGENT.md Section 1, Sprint 1.
"""

import json
import logging
import os
from datetime import datetime, timezone

import apache_beam as beam
from apache_beam.options.pipeline_options import PipelineOptions, StandardOptions
from apache_beam.io.gcp.pubsub import ReadFromPubSub
from apache_beam.io.gcp.bigquery import WriteToBigQuery, BigQueryDisposition

from transforms.schema_validator import ValidateSchema
from transforms.demographic_enricher import EnrichDemographics
from transforms.pii_redactor import RedactPII
from transforms.dead_letter_handler import WriteToDeadLetter

logger = logging.getLogger("fairops.stream_processor")


def build_pipeline(pipeline_options: PipelineOptions) -> beam.Pipeline:
    """
    Build the FairOps streaming pipeline.

    Flow:
    1. Read from Pub/Sub
    2. Parse JSON
    3. Validate against PredictionEvent schema
    4. Enrich with demographic tags
    5. Redact PII via Cloud DLP
    6. Write valid records to BigQuery (raw + enriched)
    7. Route invalid records to dead-letter topic
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
    topic = os.environ.get(
        "PUBSUB_SUBSCRIPTION_ID",
        f"projects/{project_id}/subscriptions/fairops-predictions-sub",
    )

    raw_table = f"{project_id}:fairops_raw.predictions"
    enriched_table = f"{project_id}:fairops_enriched.demographics"

    p = beam.Pipeline(options=pipeline_options)

    # Read from Pub/Sub subscription
    messages = (
        p
        | "ReadPubSub" >> ReadFromPubSub(subscription=topic)
        | "DecodeUTF8" >> beam.Map(lambda msg: msg.decode("utf-8"))
        | "ParseJSON" >> beam.Map(json.loads)
    )

    # Validate schema — outputs to main (valid) and dead_letter (invalid)
    validated = messages | "ValidateSchema" >> beam.ParDo(
        ValidateSchema()
    ).with_outputs("dead_letter", main="valid")

    valid_events = validated.valid
    dead_letter_events = validated.dead_letter

    # Enrich with demographic data
    enriched = valid_events | "EnrichDemographics" >> beam.ParDo(
        EnrichDemographics()
    )

    # Redact PII before writing to BigQuery
    redacted = valid_events | "RedactPII" >> beam.ParDo(
        RedactPII(project_id=project_id)
    )

    # Write raw predictions to BigQuery
    redacted | "WriteRawToBQ" >> WriteToBigQuery(
        table=raw_table,
        schema={
            "fields": [
                {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
                {"name": "model_id", "type": "STRING", "mode": "REQUIRED"},
                {"name": "model_version", "type": "STRING", "mode": "REQUIRED"},
                {"name": "timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
                {"name": "features", "type": "JSON", "mode": "NULLABLE"},
                {"name": "prediction_label", "type": "STRING", "mode": "NULLABLE"},
                {"name": "prediction_score", "type": "FLOAT64", "mode": "NULLABLE"},
                {"name": "prediction_threshold", "type": "FLOAT64", "mode": "NULLABLE"},
                {"name": "ground_truth", "type": "STRING", "mode": "NULLABLE"},
                {"name": "demographic_tags", "type": "STRING", "mode": "REPEATED"},
                {"name": "tenant_id", "type": "STRING", "mode": "NULLABLE"},
                {"name": "use_case", "type": "STRING", "mode": "NULLABLE"},
                {"name": "ingested_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
            ]
        },
        write_disposition=BigQueryDisposition.WRITE_APPEND,
        create_disposition=BigQueryDisposition.CREATE_NEVER,
        method="STREAMING_INSERTS",
    )

    # Write enriched demographics to BigQuery
    enriched | "WriteEnrichedToBQ" >> WriteToBigQuery(
        table=enriched_table,
        schema={
            "fields": [
                {"name": "event_id", "type": "STRING", "mode": "REQUIRED"},
                {"name": "model_id", "type": "STRING", "mode": "REQUIRED"},
                {"name": "timestamp", "type": "TIMESTAMP", "mode": "REQUIRED"},
                {"name": "gender_distribution", "type": "JSON", "mode": "NULLABLE"},
                {"name": "race_distribution", "type": "JSON", "mode": "NULLABLE"},
                {"name": "age_bin", "type": "STRING", "mode": "NULLABLE"},
                {"name": "income_bracket", "type": "STRING", "mode": "NULLABLE"},
                {"name": "proxy_quality_score", "type": "FLOAT64", "mode": "NULLABLE"},
                {"name": "is_proxy", "type": "BOOL", "mode": "NULLABLE"},
                {"name": "zip_code", "type": "STRING", "mode": "NULLABLE"},
                {"name": "enriched_at", "type": "TIMESTAMP", "mode": "NULLABLE"},
            ]
        },
        write_disposition=BigQueryDisposition.WRITE_APPEND,
        create_disposition=BigQueryDisposition.CREATE_NEVER,
        method="STREAMING_INSERTS",
    )

    # Route dead-letter events
    dead_letter_events | "WriteDeadLetter" >> beam.ParDo(
        WriteToDeadLetter(project_id=project_id)
    )

    return p


def run():
    """Launch the streaming pipeline."""
    pipeline_options = PipelineOptions()
    pipeline_options.view_as(StandardOptions).streaming = True

    pipeline = build_pipeline(pipeline_options)
    result = pipeline.run()
    result.wait_until_finish()


if __name__ == "__main__":
    run()
