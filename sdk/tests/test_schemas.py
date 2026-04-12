"""
Unit tests for FairOps SDK schemas.

Tests all Pydantic v2 models with valid and invalid data to ensure
data contracts are enforced correctly.

Ref: AGENT.md Section 5, Sprint 1 DoD.
"""

import pytest
from datetime import datetime, timezone
from uuid import UUID

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


# ── Enum Tests ────────────────────────────────────────────────────────────────

class TestSeverityEnum:
    def test_all_values_exist(self):
        assert Severity.CRITICAL == "CRITICAL"
        assert Severity.HIGH == "HIGH"
        assert Severity.MEDIUM == "MEDIUM"
        assert Severity.LOW == "LOW"
        assert Severity.PASS == "PASS"

    def test_severity_from_string(self):
        assert Severity("CRITICAL") == Severity.CRITICAL

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError):
            Severity("INVALID")


class TestUseCaseEnum:
    def test_all_values_exist(self):
        assert UseCase.HIRING == "hiring"
        assert UseCase.LENDING == "lending"
        assert UseCase.HEALTHCARE == "healthcare"
        assert UseCase.CRIMINAL_JUSTICE == "criminal_justice"
        assert UseCase.CONTENT_RECOMMENDATION == "content_recommendation"


class TestMitigationStageEnum:
    def test_all_values_exist(self):
        assert MitigationStage.PRE_PROCESSING == "pre-processing"
        assert MitigationStage.IN_PROCESSING == "in-processing"
        assert MitigationStage.POST_PROCESSING == "post-processing"
        assert MitigationStage.RETRAINING == "retraining"


class TestMitigationStatusEnum:
    def test_all_values_exist(self):
        assert MitigationStatus.QUEUED == "queued"
        assert MitigationStatus.IN_PROGRESS == "in_progress"
        assert MitigationStatus.SUCCESS == "success"
        assert MitigationStatus.FAILED == "failed"
        assert MitigationStatus.ROLLED_BACK == "rolled_back"


# ── PredictionResult Tests ───────────────────────────────────────────────────

class TestPredictionResult:
    def test_valid_prediction(self):
        pr = PredictionResult(label="approved", score=0.87, threshold=0.5)
        assert pr.label == "approved"
        assert pr.score == 0.87
        assert pr.threshold == 0.5

    def test_score_boundary_zero(self):
        pr = PredictionResult(label="denied", score=0.0, threshold=0.5)
        assert pr.score == 0.0

    def test_score_boundary_one(self):
        pr = PredictionResult(label="approved", score=1.0, threshold=0.5)
        assert pr.score == 1.0

    def test_score_below_zero_raises(self):
        with pytest.raises(Exception):
            PredictionResult(label="denied", score=-0.1, threshold=0.5)

    def test_score_above_one_raises(self):
        with pytest.raises(Exception):
            PredictionResult(label="approved", score=1.1, threshold=0.5)

    def test_threshold_below_zero_raises(self):
        with pytest.raises(Exception):
            PredictionResult(label="approved", score=0.5, threshold=-0.1)

    def test_threshold_above_one_raises(self):
        with pytest.raises(Exception):
            PredictionResult(label="approved", score=0.5, threshold=1.1)


# ── SessionContext Tests ─────────────────────────────────────────────────────

class TestSessionContext:
    def test_valid_context(self):
        ctx = SessionContext(tenant_id="acme-corp", use_case=UseCase.HIRING)
        assert ctx.tenant_id == "acme-corp"
        assert ctx.use_case == UseCase.HIRING

    def test_use_case_from_string(self):
        ctx = SessionContext(tenant_id="acme-corp", use_case="hiring")
        assert ctx.use_case == UseCase.HIRING

    def test_invalid_use_case_raises(self):
        with pytest.raises(Exception):
            SessionContext(tenant_id="acme-corp", use_case="invalid_case")


# ── PredictionEvent Tests ────────────────────────────────────────────────────

class TestPredictionEvent:
    @pytest.fixture
    def valid_event_data(self):
        return {
            "model_id": "hiring-classifier-v2",
            "model_version": "v2.1.0",
            "timestamp": datetime.now(timezone.utc),
            "features": {"age": 35, "sex": "Male", "education": "Bachelors"},
            "prediction": PredictionResult(
                label="approved", score=0.87, threshold=0.5
            ),
            "session_context": SessionContext(
                tenant_id="acme-corp", use_case=UseCase.HIRING
            ),
        }

    def test_valid_event(self, valid_event_data):
        event = PredictionEvent(**valid_event_data)
        assert event.model_id == "hiring-classifier-v2"
        assert event.model_version == "v2.1.0"
        assert event.prediction.score == 0.87
        assert event.session_context.tenant_id == "acme-corp"

    def test_auto_generated_event_id(self, valid_event_data):
        event = PredictionEvent(**valid_event_data)
        # event_id should be a valid UUID
        UUID(event.event_id)

    def test_unique_event_ids(self, valid_event_data):
        event1 = PredictionEvent(**valid_event_data)
        event2 = PredictionEvent(**valid_event_data)
        assert event1.event_id != event2.event_id

    def test_model_id_with_spaces_raises(self, valid_event_data):
        valid_event_data["model_id"] = "model with spaces"
        with pytest.raises(Exception, match="model_id must not contain spaces"):
            PredictionEvent(**valid_event_data)

    def test_model_id_no_spaces_passes(self, valid_event_data):
        valid_event_data["model_id"] = "model-no-spaces_v2"
        event = PredictionEvent(**valid_event_data)
        assert event.model_id == "model-no-spaces_v2"

    def test_default_demographic_tags(self, valid_event_data):
        event = PredictionEvent(**valid_event_data)
        assert event.demographic_tags == []

    def test_custom_demographic_tags(self, valid_event_data):
        valid_event_data["demographic_tags"] = ["MALE", "AGE_30_40"]
        event = PredictionEvent(**valid_event_data)
        assert event.demographic_tags == ["MALE", "AGE_30_40"]

    def test_ground_truth_optional(self, valid_event_data):
        event = PredictionEvent(**valid_event_data)
        assert event.ground_truth is None

    def test_ground_truth_set(self, valid_event_data):
        valid_event_data["ground_truth"] = "approved"
        event = PredictionEvent(**valid_event_data)
        assert event.ground_truth == "approved"

    def test_serialization_roundtrip(self, valid_event_data):
        event = PredictionEvent(**valid_event_data)
        json_str = event.model_dump_json()
        reconstructed = PredictionEvent.model_validate_json(json_str)
        assert reconstructed.event_id == event.event_id
        assert reconstructed.model_id == event.model_id
        assert reconstructed.prediction.score == event.prediction.score

    def test_missing_required_fields_raises(self):
        with pytest.raises(Exception):
            PredictionEvent(model_id="test")


# ── FairnessMetric Tests ─────────────────────────────────────────────────────

class TestFairnessMetric:
    def test_valid_metric(self):
        metric = FairnessMetric(
            name="demographic_parity_difference",
            value=0.15,
            threshold=0.10,
            breached=True,
            confidence_interval=(0.12, 0.18),
            severity=Severity.HIGH,
            groups_compared=("Male", "Female"),
            sample_sizes=(500, 450),
            p_value=0.003,
        )
        assert metric.breached is True
        assert metric.severity == Severity.HIGH
        assert metric.confidence_interval == (0.12, 0.18)
        assert metric.groups_compared == ("Male", "Female")

    def test_passing_metric(self):
        metric = FairnessMetric(
            name="demographic_parity_difference",
            value=0.05,
            threshold=0.10,
            breached=False,
            confidence_interval=(0.02, 0.08),
            severity=Severity.PASS,
            groups_compared=("Male", "Female"),
            sample_sizes=(500, 450),
            p_value=0.12,
        )
        assert metric.breached is False
        assert metric.severity == Severity.PASS


# ── DemographicSlice Tests ───────────────────────────────────────────────────

class TestDemographicSlice:
    def test_valid_slice(self):
        ds = DemographicSlice(
            attribute="sex",
            group_value="Male",
            count=500,
            positive_rate=0.62,
            metrics={"demographic_parity_difference": 0.15},
        )
        assert ds.attribute == "sex"
        assert ds.count == 500
        assert ds.positive_rate == 0.62


# ── BiasAuditResult Tests ───────────────────────────────────────────────────

class TestBiasAuditResult:
    @pytest.fixture
    def valid_audit_data(self):
        return {
            "model_id": "hiring-classifier",
            "model_version": "v2.1",
            "window_start": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "window_end": datetime(2024, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
            "sample_size": 1000,
            "metrics": {
                "demographic_parity_difference": FairnessMetric(
                    name="demographic_parity_difference",
                    value=0.15,
                    threshold=0.10,
                    breached=True,
                    confidence_interval=(0.12, 0.18),
                    severity=Severity.HIGH,
                    groups_compared=("Male", "Female"),
                    sample_sizes=(500, 500),
                    p_value=0.003,
                )
            },
            "overall_severity": Severity.HIGH,
            "protected_attributes": ["sex"],
            "demographic_slices": [
                DemographicSlice(
                    attribute="sex",
                    group_value="Male",
                    count=500,
                    positive_rate=0.62,
                    metrics={"demographic_parity_difference": 0.15},
                )
            ],
        }

    def test_valid_audit(self, valid_audit_data):
        audit = BiasAuditResult(**valid_audit_data)
        assert audit.model_id == "hiring-classifier"
        assert audit.overall_severity == Severity.HIGH
        assert audit.triggered_mitigation is False
        assert audit.mitigation_id is None

    def test_auto_generated_audit_id(self, valid_audit_data):
        audit = BiasAuditResult(**valid_audit_data)
        UUID(audit.audit_id)

    def test_audit_with_mitigation(self, valid_audit_data):
        valid_audit_data["triggered_mitigation"] = True
        valid_audit_data["mitigation_id"] = "mit-12345"
        audit = BiasAuditResult(**valid_audit_data)
        assert audit.triggered_mitigation is True
        assert audit.mitigation_id == "mit-12345"


# ── MitigationRecord Tests ──────────────────────────────────────────────────

class TestMitigationRecord:
    def test_valid_mitigation_record(self):
        record = MitigationRecord(
            audit_id="audit-123",
            model_id="hiring-classifier",
            model_version_before="v2.1",
            algorithm_used="Reweighing",
            stage=MitigationStage.PRE_PROCESSING,
            metrics_before={"disparate_impact_ratio": 0.38},
            accuracy_before=0.85,
        )
        assert record.status == MitigationStatus.QUEUED
        assert record.promoted_to_production is False
        assert record.model_version_after is None

    def test_completed_mitigation_record(self):
        record = MitigationRecord(
            audit_id="audit-123",
            model_id="hiring-classifier",
            model_version_before="v2.1",
            model_version_after="v2.2",
            algorithm_used="Reweighing",
            stage=MitigationStage.PRE_PROCESSING,
            metrics_before={"disparate_impact_ratio": 0.38},
            metrics_after={"disparate_impact_ratio": 0.85},
            accuracy_before=0.85,
            accuracy_after=0.83,
            accuracy_delta=-0.02,
            status=MitigationStatus.SUCCESS,
            promoted_to_production=True,
            vertex_pipeline_run_id="run-456",
        )
        assert record.status == MitigationStatus.SUCCESS
        assert record.promoted_to_production is True
        assert record.accuracy_delta == -0.02


# ── ApiResponse Tests ────────────────────────────────────────────────────────

class TestApiResponse:
    def test_default_success(self):
        response = ApiResponse()
        assert response.status == "success"
        assert response.data is None
        assert response.error is None
        UUID(response.request_id)

    def test_success_with_data(self):
        response = ApiResponse(data={"audit_id": "abc-123"})
        assert response.data == {"audit_id": "abc-123"}

    def test_error_response(self):
        response = ApiResponse(
            status="error",
            error={"code": 400, "message": "Invalid model_id"},
        )
        assert response.status == "error"
        assert response.error["code"] == 400

    def test_serialization_roundtrip(self):
        original = ApiResponse(data={"key": "value"})
        json_str = original.model_dump_json()
        reconstructed = ApiResponse.model_validate_json(json_str)
        assert reconstructed.request_id == original.request_id
        assert reconstructed.data == original.data
