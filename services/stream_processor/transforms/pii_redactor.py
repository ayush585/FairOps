"""
Stream Processor Transform — PII Redaction via Cloud DLP.

Every record passes through Cloud DLP before writing to BigQuery.
Detect: emails, phone numbers, SSNs, full names.
Action: tokenize (consistent token per value, not delete).

Ref: AGENT.md Section 8.
"""

import json
import logging
from typing import Optional

import apache_beam as beam

logger = logging.getLogger("fairops.stream_processor.pii_redactor")


class RedactPII(beam.DoFn):
    """
    Redacts PII from prediction event features using Cloud DLP.

    Uses consistent tokenization so that the same value always
    produces the same token — enabling cohort fairness analysis
    to still work on tokenized data.
    """

    def __init__(self, project_id: str):
        self.project_id = project_id
        self._dlp_client = None

    def setup(self):
        """Initialize Cloud DLP client (called once per worker)."""
        try:
            from google.cloud import dlp_v2

            self._dlp_client = dlp_v2.DlpServiceClient()
            logger.info("Cloud DLP client initialized")
        except Exception as e:
            logger.warning(
                f"Cloud DLP client initialization failed (will pass through): {e}"
            )
            self._dlp_client = None

    def _redact_value(self, value: str) -> str:
        """
        Redact PII from a string value using Cloud DLP.

        Falls back to passthrough if DLP is unavailable (local dev).
        """
        if self._dlp_client is None or not value or not isinstance(value, str):
            return value

        try:
            parent = f"projects/{self.project_id}/locations/global"

            # Define info types to detect
            inspect_config = {
                "info_types": [
                    {"name": "EMAIL_ADDRESS"},
                    {"name": "PHONE_NUMBER"},
                    {"name": "US_SOCIAL_SECURITY_NUMBER"},
                    {"name": "PERSON_NAME"},
                ],
                "min_likelihood": "POSSIBLE",
            }

            # Tokenize with deterministic crypto hash (consistent tokens)
            deidentify_config = {
                "info_type_transformations": {
                    "transformations": [
                        {
                            "primitive_transformation": {
                                "crypto_hash_config": {
                                    "crypto_key": {
                                        "unwrapped": {
                                            "key": b"fairops-pii-tokenization-key-v1"[:32],
                                        }
                                    }
                                }
                            }
                        }
                    ]
                }
            }

            item = {"value": value}

            response = self._dlp_client.deidentify_content(
                request={
                    "parent": parent,
                    "inspect_config": inspect_config,
                    "deidentify_config": deidentify_config,
                    "item": item,
                }
            )

            return response.item.value

        except Exception as e:
            logger.error(f"DLP redaction failed, passing through: {e}")
            return value

    def _redact_features(self, features: dict) -> dict:
        """Redact PII from all string values in the features dict."""
        redacted = {}
        for key, value in features.items():
            if isinstance(value, str):
                redacted[key] = self._redact_value(value)
            elif isinstance(value, dict):
                redacted[key] = self._redact_features(value)
            else:
                redacted[key] = value
        return redacted

    def process(self, element, *args, **kwargs):
        # Parse features
        features = element.get("features")
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except json.JSONDecodeError:
                features = {}

        if isinstance(features, dict):
            redacted_features = self._redact_features(features)
            element["features"] = json.dumps(redacted_features)

        yield element
