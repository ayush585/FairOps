"""
FairOps Mitigation Engine — Vertex AI Jobs.

Triggers mitigation workloads as Google Cloud Vertex AI CustomJobs.
Provides an asynchronous mechanism to execute expensive retraining
or post-processing without blocking the API endpoint.

Ref: AGENT.md Sprint 4, Section 15.
"""

import os
import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger("fairops.mitigation.vertex_jobs")


# Mock job execution history for local development / testing
_local_job_history = {}


def trigger_mitigation_job(
    mitigation_id: str,
    audit_id: str,
    model_id: str,
    algorithm: str,
    stage: str,
) -> dict:
    """
    Launch a Vertex AI CustomJob for bias mitigation.

    Args:
        mitigation_id: Unique mitigation record ID.
        audit_id: Originating bias audit ID.
        model_id: Model registry ID.
        algorithm: Algorithm to apply (e.g. "exponentiated_gradient").
        stage: Pipeline stage (e.g. "in-processing").

    Returns:
        Dict containing job reference details (name, vertex_job_id, console_url).
    """
    project_id = os.environ.get("GCP_PROJECT_ID")
    location = os.environ.get("GCP_REGION", "us-central1")
    container_image = os.environ.get(
        "MITIGATION_IMAGE_URI",
        "us-docker.pkg.dev/fairops-prod/artifacts/fairops-mitigation:latest"
    )
    
    # Generate deterministic job name
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    job_display_name = f"fairops_mitigation_{model_id}_{timestamp}"

    # Check if we are running in full GCP mode
    if project_id:
        try:
            from google.cloud import aiplatform

            aiplatform.init(project=project_id, location=location)
            
            logger.info(f"Submitting Vertex AI CustomJob: {job_display_name}")

            # Define the CustomJob
            job = aiplatform.CustomContainerTrainingJob(
                display_name=job_display_name,
                container_uri=container_image,
                command=["python", "run_mitigation.py"],
                # Pass necessary identifiers for the container to query Spanner/Storage
                container_args=[
                    f"--mitigation_id={mitigation_id}",
                    f"--audit_id={audit_id}",
                    f"--model_id={model_id}",
                    f"--algorithm={algorithm}",
                    f"--stage={stage}",
                ],
            )
            
            # Run asynchronously (do not block the thread waiting for Vertex completion)
            # The container execution logic will eventually update the MitigationRecord in Spanner
            # with final mitigated success/failure status.
            job.submit(
                machine_type="n1-standard-4",
                replica_count=1,
            )

            job_resource_name = job.resource_name
            logger.info(f"Vertex AI job submitted successfully: {job_resource_name}")

            console_url = (
                f"https://console.cloud.google.com/vertex-ai/locations/{location}/"
                f"training/{job.name}?project={project_id}"
            )

            return {
                "vertex_job_name": job_display_name,
                "vertex_job_id": job.resource_name,
                "console_url": console_url,
                "status": "SUBMITTED_TO_VERTEX",
            }

        except ImportError:
            logger.error("google-cloud-aiplatform not installed. Cannot submit Vertex Job.")
            raise
        except Exception as e:
            logger.error(f"Failed to submit Vertex job {job_display_name}: {e}", exc_info=True)
            raise
            
    else:
        # Development mode simulation
        logger.warning("GCP_PROJECT_ID not set! Simulating Vertex CustomJob submission locally.")
        mock_job_id = f"mock-jobs/locations/us-central1/customJobs/123456789-{timestamp}"
        
        _local_job_history[mitigation_id] = {
            "mitigation_id": mitigation_id,
            "job_id": mock_job_id,
            "status": "SIMULATED",
            "model_id": model_id,
            "algorithm": algorithm,
        }
        
        return {
            "vertex_job_name": job_display_name,
            "vertex_job_id": mock_job_id,
            "console_url": "http://localhost/simulated-vertex-console",
            "status": "SIMULATED_SUCCESS",
        }
