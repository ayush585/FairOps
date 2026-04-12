"""
FairOps SDK — 3-line integration for ML bias monitoring.

Usage:
    from fairops_sdk import FairOpsClient

    client = FairOpsClient(project_id="fairops-prod", model_id="my-model", model_version="v1")
    client.log_prediction(features={"age": 35, "sex": "Male"}, prediction={"label": "approved", "score": 0.87, "threshold": 0.5})
"""

__version__ = "0.1.0"

# Schemas are always available (no GCP dependencies)
from fairops_sdk.schemas import (
    PredictionEvent,
    PredictionResult,
    SessionContext,
    BiasAuditResult,
    FairnessMetric,
    DemographicSlice,
    MitigationRecord,
    ApiResponse,
    Severity,
    UseCase,
    MitigationStage,
    MitigationStatus,
)

# Client and Publisher require GCP dependencies — import lazily
try:
    from fairops_sdk.client import FairOpsClient
    from fairops_sdk.publisher import PredictionPublisher
except ImportError:
    FairOpsClient = None  # type: ignore
    PredictionPublisher = None  # type: ignore

__all__ = [
    "FairOpsClient",
    "PredictionPublisher",
    "PredictionEvent",
    "PredictionResult",
    "SessionContext",
    "BiasAuditResult",
    "FairnessMetric",
    "DemographicSlice",
    "MitigationRecord",
    "ApiResponse",
    "Severity",
    "UseCase",
    "MitigationStage",
    "MitigationStatus",
]
