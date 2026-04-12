"""
Shared — Custom Exception Hierarchy.

AGENT.md Rule #5: Fail loudly. No silent exception swallowing.
Every service must log errors with full stack traces.
Unhandled exceptions should crash the service, not hide the bug.
"""


class FairOpsError(Exception):
    """Base exception for all FairOps errors."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


# ── Schema / Validation Errors ───────────────────────────────────────────────

class SchemaValidationError(FairOpsError):
    """Raised when incoming data fails Pydantic schema validation."""
    pass


class InvalidModelIdError(FairOpsError):
    """Raised when a model_id is not found or invalid."""
    pass


# ── Audit Errors ─────────────────────────────────────────────────────────────

class AuditError(FairOpsError):
    """Base class for audit-related errors."""
    pass


class InsufficientSampleSizeError(AuditError):
    """Raised when sample size is below AUDIT_MIN_SAMPLE_SIZE threshold."""
    pass


class StaleAuditError(AuditError):
    """Raised when an audit trigger references data older than 2 hours."""
    pass


class MetricComputationError(AuditError):
    """Raised when a fairness metric computation fails."""
    pass


# ── Mitigation Errors ────────────────────────────────────────────────────────

class MitigationError(FairOpsError):
    """Base class for mitigation pipeline errors."""
    pass


class AccuracyGateFailedError(MitigationError):
    """Raised when accuracy delta exceeds the 2% threshold."""
    pass


class PipelineTimeoutError(MitigationError):
    """Raised when a Vertex AI pipeline exceeds its time budget."""
    pass


class ModelPromotionError(MitigationError):
    """Raised when model promotion to Vertex AI Model Registry fails."""
    pass


# ── Explainer Errors ─────────────────────────────────────────────────────────

class ExplainerError(FairOpsError):
    """Base class for explainer service errors."""
    pass


class GeminiApiError(ExplainerError):
    """Raised when Gemini API call fails after all retries."""
    pass


class ShapComputationError(ExplainerError):
    """Raised when SHAP value computation fails."""
    pass


# ── Infrastructure Errors ────────────────────────────────────────────────────

class InfrastructureError(FairOpsError):
    """Base class for infrastructure-related errors."""
    pass


class BigQueryError(InfrastructureError):
    """Raised on BigQuery operation failures."""
    pass


class SpannerError(InfrastructureError):
    """Raised on Cloud Spanner operation failures."""
    pass


class PubSubError(InfrastructureError):
    """Raised on Pub/Sub publish or receive failures."""
    pass


class SecretManagerError(InfrastructureError):
    """Raised when Secret Manager access fails."""
    pass


# ── Auth Errors ──────────────────────────────────────────────────────────────

class AuthenticationError(FairOpsError):
    """Raised on authentication failure."""
    pass


class AuthorizationError(FairOpsError):
    """Raised when a user lacks required role/permission."""
    pass


class RateLimitExceededError(FairOpsError):
    """Raised when rate limit is exceeded."""
    pass
