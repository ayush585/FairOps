"""
Stream Processor — Dataflow Runner.

Launches the Apache Beam pipeline on Google Cloud Dataflow
with proper configuration for streaming mode.

Ref: AGENT.md Sprint 1.
"""

import os
import logging

from apache_beam.options.pipeline_options import (
    PipelineOptions,
    GoogleCloudOptions,
    StandardOptions,
    WorkerOptions,
    SetupOptions,
)

from pipeline import build_pipeline

logger = logging.getLogger("fairops.stream_processor.dataflow_runner")


def get_dataflow_options() -> PipelineOptions:
    """
    Configure pipeline options for Dataflow execution.

    Returns:
        Configured PipelineOptions for Dataflow.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
    region = os.environ.get("GCP_REGION", "us-central1")

    options = PipelineOptions()

    # Standard options
    std_options = options.view_as(StandardOptions)
    std_options.runner = "DataflowRunner"
    std_options.streaming = True

    # GCP options
    gcp_options = options.view_as(GoogleCloudOptions)
    gcp_options.project = project_id
    gcp_options.region = region
    gcp_options.job_name = "fairops-stream-processor"
    gcp_options.temp_location = f"gs://fairops-pipelines-{project_id}/temp"
    gcp_options.staging_location = f"gs://fairops-pipelines-{project_id}/staging"
    gcp_options.service_account_email = (
        f"fairops-stream-processor@{project_id}.iam.gserviceaccount.com"
    )

    # Worker options
    worker_options = options.view_as(WorkerOptions)
    worker_options.max_num_workers = 10
    worker_options.machine_type = "n1-standard-2"
    worker_options.disk_size_gb = 50
    worker_options.autoscaling_algorithm = "THROUGHPUT_BASED"

    # Setup options
    setup_options = options.view_as(SetupOptions)
    setup_options.requirements_file = os.path.join(
        os.path.dirname(__file__), "requirements.txt"
    )

    return options


def run():
    """Launch pipeline on Dataflow."""
    logger.info("Launching FairOps stream processor on Dataflow...")

    options = get_dataflow_options()
    pipeline = build_pipeline(options)
    result = pipeline.run()

    logger.info(f"Pipeline submitted. Job ID: {result.job_id()}")
    logger.info("Pipeline running in streaming mode — will not terminate.")


if __name__ == "__main__":
    run()
