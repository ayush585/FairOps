"""
Shared — BigQuery Client Factory.

Provides a singleton BigQuery client with standard configuration
used by all services.

Ref: AGENT.md Section 10.
"""

import os
import logging
from typing import Optional

from google.cloud import bigquery

logger = logging.getLogger("fairops.shared.bigquery")

# Singleton client instance
_bq_client: Optional[bigquery.Client] = None


def get_bq_client() -> bigquery.Client:
    """
    Get or create a BigQuery client singleton.

    Returns:
        Configured BigQuery client.
    """
    global _bq_client
    if _bq_client is None:
        project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
        _bq_client = bigquery.Client(project=project_id)
        logger.info(f"BigQuery client initialized for project {project_id}")
    return _bq_client


def get_dataset_ref(dataset_name: str) -> str:
    """
    Get fully qualified dataset reference.

    Args:
        dataset_name: One of fairops_raw, fairops_enriched, fairops_metrics.

    Returns:
        Fully qualified dataset reference string.
    """
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
    return f"{project_id}.{dataset_name}"


def get_table_ref(dataset_name: str, table_name: str) -> str:
    """
    Get fully qualified table reference.

    Args:
        dataset_name: Dataset name.
        table_name: Table name.

    Returns:
        Fully qualified table reference string.
    """
    return f"{get_dataset_ref(dataset_name)}.{table_name}"


def streaming_insert(
    dataset: str,
    table: str,
    rows: list[dict],
    request_id: str = "",
) -> list[dict]:
    """
    Insert rows via BigQuery streaming API.

    Use for real-time queryable data like prediction events.
    For batch operations, use load_from_gcs() instead.

    Ref: AGENT.md Section 21 — streaming for predictions, batch for training data.

    Args:
        dataset: Dataset name.
        table: Table name.
        rows: List of row dicts matching table schema.
        request_id: Request ID for logging.

    Returns:
        List of errors (empty if all succeeded).

    Raises:
        RuntimeError: If any rows failed to insert.
    """
    client = get_bq_client()
    table_ref = get_table_ref(dataset, table)

    errors = client.insert_rows_json(table_ref, rows)

    if errors:
        logger.error(
            f"BigQuery streaming insert errors",
            extra={
                "table": table_ref,
                "request_id": request_id,
                "error_count": len(errors),
                "errors": str(errors[:5]),  # Log first 5 errors
            },
        )
        raise RuntimeError(
            f"BigQuery streaming insert failed: {len(errors)} errors. "
            f"First error: {errors[0]}"
        )

    logger.info(
        f"Streaming insert successful",
        extra={
            "table": table_ref,
            "request_id": request_id,
            "row_count": len(rows),
        },
    )

    return errors


def query(sql: str, params: Optional[list] = None) -> list[dict]:
    """
    Execute a BigQuery SQL query and return results as dicts.

    Args:
        sql: SQL query string.
        params: Optional query parameters.

    Returns:
        List of result row dicts.
    """
    client = get_bq_client()

    job_config = bigquery.QueryJobConfig()
    if params:
        job_config.query_parameters = params

    query_job = client.query(sql, job_config=job_config)
    results = query_job.result()

    return [dict(row) for row in results]
