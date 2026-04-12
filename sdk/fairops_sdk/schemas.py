"""
FairOps Core Data Schemas — Pydantic v2.

ALL services import from here. Never redefine these schemas elsewhere.
Ref: AGENT.md Section 5.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4


# ── Enums ─────────────────────────────────────────────────────────────────────

class Severity(str, Enum):
    """Bias severity classification levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PASS = "PASS"


class UseCase(str, Enum):
    """Supported ML use case domains."""
    HIRING = "hiring"
    LENDING = "lending"
    HEALTHCARE = "healthcare"
    CRIMINAL_JUSTICE = "criminal_justice"
    CONTENT_RECOMMENDATION = "content_recommendation"


class MitigationStage(str, Enum):
    """Stage at which mitigation is applied."""
    PRE_PROCESSING = "pre-processing"
    IN_PROCESSING = "in-processing"
    POST_PROCESSING = "post-processing"
    RETRAINING = "retraining"


class MitigationStatus(str, Enum):
    """Status of a mitigation pipeline run."""
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


# ── Prediction Schemas ────────────────────────────────────────────────────────

class PredictionResult(BaseModel):
    """A single model prediction output."""
    label: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)


class SessionContext(BaseModel):
    """Tenant and use case context for a prediction event."""
    tenant_id: str
    use_case: UseCase


class PredictionEvent(BaseModel):
    """
    A single prediction event logged by the FairOps SDK.
    This is the fundamental data unit flowing through the entire pipeline.
    """
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_version: str
    timestamp: datetime
    features: dict[str, Any]
    prediction: PredictionResult
    ground_truth: Optional[str] = None
    demographic_tags: list[str] = Field(default_factory=list)
    session_context: SessionContext

    @field_validator("model_id")
    @classmethod
    def model_id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("model_id must not contain spaces")
        return v


# ── Fairness Metric Schemas ──────────────────────────────────────────────────

class FairnessMetric(BaseModel):
    """Result of a single fairness metric computation."""
    name: str
    value: float
    threshold: float
    breached: bool
    confidence_interval: tuple[float, float]
    severity: Severity
    groups_compared: tuple[str, str]
    sample_sizes: tuple[int, int]
    p_value: float


class DemographicSlice(BaseModel):
    """Fairness statistics for a single demographic slice."""
    attribute: str
    group_value: str
    count: int
    positive_rate: float
    metrics: dict[str, float]


# ── Bias Audit Schemas ───────────────────────────────────────────────────────

class BiasAuditResult(BaseModel):
    """
    Complete result of a bias audit run.
    Produced by the auditor service after computing all 12 fairness metrics.
    """
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_version: str
    audit_timestamp: datetime = Field(default_factory=datetime.utcnow)
    window_start: datetime
    window_end: datetime
    sample_size: int
    metrics: dict[str, FairnessMetric]
    overall_severity: Severity
    protected_attributes: list[str]
    demographic_slices: list[DemographicSlice]
    triggered_mitigation: bool = False
    mitigation_id: Optional[str] = None


# ── Mitigation Schemas ───────────────────────────────────────────────────────

class MitigationRecord(BaseModel):
    """
    Record of an automated mitigation pipeline execution.
    Written to Cloud Spanner as an immutable audit trail.
    """
    mitigation_id: str = Field(default_factory=lambda: str(uuid4()))
    audit_id: str
    model_id: str
    model_version_before: str
    model_version_after: Optional[str] = None
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    algorithm_used: str
    stage: MitigationStage
    metrics_before: dict[str, float]
    metrics_after: Optional[dict[str, float]] = None
    accuracy_before: float
    accuracy_after: Optional[float] = None
    accuracy_delta: Optional[float] = None
    status: MitigationStatus = MitigationStatus.QUEUED
    promoted_to_production: bool = False
    vertex_pipeline_run_id: Optional[str] = None
    error_message: Optional[str] = None


# ── API Response Envelope ────────────────────────────────────────────────────

class ApiResponse(BaseModel):
    """Standard API response envelope. All endpoints return this."""
    status: str = "success"
    data: Optional[Any] = None
    error: Optional[dict] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
