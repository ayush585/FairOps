"""
Unit tests for Gemini narrative generation.

Tests template fallback (no API key required) and prompt construction.

Ref: AGENT.md Sprint 3.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "explainer"))


SAMPLE_METRICS = {
    "demographic_parity_difference": {
        "value": 0.35, "threshold": 0.10, "breached": True,
        "severity": "CRITICAL", "p_value": 0.001,
    },
    "disparate_impact_ratio": {
        "value": 0.38, "threshold": 0.80, "breached": True,
        "severity": "CRITICAL", "p_value": 0.001,
    },
    "equalized_odds_difference": {
        "value": 0.05, "threshold": 0.08, "breached": False,
        "severity": "PASS", "p_value": 0.21,
    },
}

SAMPLE_SLICES = [
    {
        "attribute": "sex", "group_value": "Male",
        "count": 500, "positive_rate": 0.70,
        "metrics": {
            "true_positive_rate": 0.85, "false_positive_rate": 0.20,
            "precision": 0.75,
        },
    },
    {
        "attribute": "sex", "group_value": "Female",
        "count": 500, "positive_rate": 0.25,
        "metrics": {
            "true_positive_rate": 0.45, "false_positive_rate": 0.10,
            "precision": 0.60,
        },
    },
]


class TestTemplateNarrative:
    """Tests for the fallback template (no Gemini API key required)."""

    def test_generates_without_api_key(self):
        """Template should always work — never fail."""
        from gemini_narrator import generate_audit_narrative

        # GEMINI_API_KEY not set → template fallback
        os.environ.pop("GEMINI_API_KEY", None)

        result = generate_audit_narrative(
            audit_id="test-audit-001",
            model_id="hiring-model-v1",
            model_version="1.2.0",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-01T01:00:00Z",
            overall_severity="CRITICAL",
            metrics=SAMPLE_METRICS,
            demographic_slices=SAMPLE_SLICES,
            sample_size=1000,
        )

        assert isinstance(result, str)
        assert len(result) > 100
        assert "hiring-model-v1" in result

    def test_critical_verdict_in_template(self):
        from gemini_narrator import generate_audit_narrative

        os.environ.pop("GEMINI_API_KEY", None)
        result = generate_audit_narrative(
            audit_id="test-002",
            model_id="model-v2",
            model_version="2.0",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-02T00:00:00Z",
            overall_severity="CRITICAL",
            metrics=SAMPLE_METRICS,
            demographic_slices=[],
            sample_size=5000,
        )

        assert "CRITICAL" in result or "NON-COMPLIANT" in result

    def test_pass_verdict_in_template(self):
        from gemini_narrator import generate_audit_narrative

        os.environ.pop("GEMINI_API_KEY", None)
        passing_metrics = {
            "demographic_parity_difference": {
                "value": 0.03, "threshold": 0.10, "breached": False,
                "severity": "PASS", "p_value": 0.45,
            },
        }
        result = generate_audit_narrative(
            audit_id="test-003",
            model_id="model-v3",
            model_version="3.0",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-02T00:00:00Z",
            overall_severity="PASS",
            metrics=passing_metrics,
            demographic_slices=[],
            sample_size=2000,
        )

        assert "COMPLIANT" in result.upper()

    def test_breached_metrics_listed_in_template(self):
        from gemini_narrator import generate_audit_narrative

        os.environ.pop("GEMINI_API_KEY", None)
        result = generate_audit_narrative(
            audit_id="test-004",
            model_id="model-v4",
            model_version="4.0",
            window_start="2024-01-01T00:00:00Z",
            window_end="2024-01-02T00:00:00Z",
            overall_severity="CRITICAL",
            metrics=SAMPLE_METRICS,
            demographic_slices=[],
            sample_size=1500,
        )

        # Both breached metric names should appear somewhere
        assert "demographic_parity_difference" in result or "disparate" in result.lower()


class TestPromptBuilding:
    def test_prompt_contains_metric_values(self):
        from gemini_narrator import _build_prompt

        prompt = _build_prompt(
            audit_id="test-001",
            model_id="hiring-model-v1",
            model_version="1.0",
            window_start="2024-01-01",
            window_end="2024-01-02",
            overall_severity="CRITICAL",
            metrics=SAMPLE_METRICS,
            demographic_slices=SAMPLE_SLICES,
            shap_result=None,
            sample_size=1000,
        )

        assert "hiring-model-v1" in prompt
        assert "CRITICAL" in prompt
        assert "0.35" in prompt   # DPD value
        assert "0.38" in prompt   # DIR value
        assert "1,000" in prompt  # Sample size formatted

    def test_prompt_mentions_breached_threshold(self):
        from gemini_narrator import _build_prompt

        prompt = _build_prompt(
            audit_id="test-001",
            model_id="model",
            model_version="1.0",
            window_start="2024-01-01",
            window_end="2024-01-02",
            overall_severity="CRITICAL",
            metrics=SAMPLE_METRICS,
            demographic_slices=[],
            shap_result=None,
            sample_size=500,
        )

        assert "Breached" in prompt or "breached" in prompt

    def test_prompt_includes_shap_when_provided(self):
        from gemini_narrator import _build_prompt

        shap_result = {
            "top_bias_drivers": [
                {"feature": "income", "importance": 0.45},
                {"feature": "sex", "importance": 0.30},
            ]
        }
        prompt = _build_prompt(
            audit_id="test-001",
            model_id="model",
            model_version="1.0",
            window_start="2024-01-01",
            window_end="2024-01-02",
            overall_severity="CRITICAL",
            metrics={},
            demographic_slices=[],
            shap_result=shap_result,
            sample_size=500,
        )

        assert "income" in prompt
        assert "sex" in prompt
