"""
Unit tests for all 12 FairOps fairness metrics.

Uses hand-crafted biased arrays with known expected values
to verify each metric computes correctly.

Ref: AGENT.md Sprint 2 DoD.
"""

import pytest
import numpy as np
import sys
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "auditor"))

from fairops_sdk.schemas import FairnessMetric, Severity
from metrics.fairness import (
    demographic_parity_difference,
    equalized_odds_difference,
    equal_opportunity_difference,
    disparate_impact_ratio,
    average_odds_difference,
    statistical_parity_subgroup_lift,
    predictive_parity_difference,
    calibration_gap,
    individual_fairness_score,
    counterfactual_fairness,
    intersectional_bias_score,
    temporal_drift_index,
    compute_all_metrics,
    THRESHOLDS,
)


# ── Fixtures: Hand-crafted biased arrays ─────────────────────────────────────

@pytest.fixture
def heavily_biased_data():
    """
    Simulates UCI Adult-like data with heavy gender bias.
    Male: 70% positive rate, Female: 25% positive rate.
    Disparate impact ≈ 0.36 (well below 0.80 EEOC threshold).
    """
    np.random.seed(42)
    n = 1000

    # 500 Male, 500 Female
    sensitive = np.array(["Male"] * 500 + ["Female"] * 500)

    # Ground truth: balanced base rates
    y_true = np.array([1] * 250 + [0] * 250 + [1] * 250 + [0] * 250)

    # Predictions: biased toward Male
    # Male: 70% predicted positive
    male_preds = np.array([1] * 350 + [0] * 150)
    # Female: 25% predicted positive
    female_preds = np.array([1] * 125 + [0] * 375)
    y_pred = np.concatenate([male_preds, female_preds])

    # Scores corresponding to predictions
    y_score = np.where(y_pred == 1,
                       np.random.uniform(0.5, 0.95, n),
                       np.random.uniform(0.05, 0.45, n))

    return y_true, y_pred, y_score, sensitive, "Male"


@pytest.fixture
def mildly_biased_data():
    """
    Mildly biased data: Male 55% positive, Female 48% positive.
    DPD ≈ 0.07, DI ≈ 0.87 — within acceptable range.
    """
    np.random.seed(123)
    n = 1000

    sensitive = np.array(["Male"] * 500 + ["Female"] * 500)
    y_true = np.array([1] * 250 + [0] * 250 + [1] * 250 + [0] * 250)

    male_preds = np.array([1] * 275 + [0] * 225)
    female_preds = np.array([1] * 240 + [0] * 260)
    y_pred = np.concatenate([male_preds, female_preds])

    y_score = np.where(y_pred == 1,
                       np.random.uniform(0.5, 0.9, n),
                       np.random.uniform(0.1, 0.5, n))

    return y_true, y_pred, y_score, sensitive, "Male"


@pytest.fixture
def unbiased_data():
    """
    No bias: both groups have identical positive rates of 50%.
    """
    np.random.seed(456)
    n = 1000

    sensitive = np.array(["Male"] * 500 + ["Female"] * 500)
    y_true = np.array([1] * 250 + [0] * 250 + [1] * 250 + [0] * 250)
    y_pred = np.array([1] * 250 + [0] * 250 + [1] * 250 + [0] * 250)

    y_score = np.where(y_pred == 1,
                       np.random.uniform(0.5, 0.9, n),
                       np.random.uniform(0.1, 0.5, n))

    return y_true, y_pred, y_score, sensitive, "Male"


# ── Test: All metrics return FairnessMetric ──────────────────────────────────

class TestMetricReturnType:
    def test_all_return_fairness_metric(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = compute_all_metrics(y_true, y_pred, y_score, sensitive, priv)

        assert len(result) >= 10  # At least 10 of 12 should compute
        for name, metric in result.items():
            assert isinstance(metric, FairnessMetric), f"{name} is not FairnessMetric"
            assert metric.name == name
            assert isinstance(metric.value, float)
            assert isinstance(metric.threshold, float)
            assert isinstance(metric.breached, bool)
            assert len(metric.confidence_interval) == 2
            assert len(metric.groups_compared) == 2
            assert len(metric.sample_sizes) == 2
            assert isinstance(metric.p_value, float)


# ── Test: Metric 1 — Demographic Parity Difference ──────────────────────────

class TestDemographicParityDifference:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = demographic_parity_difference(y_true, y_pred, y_score, sensitive, priv)

        # Male 70%, Female 25% → DPD = |0.70 - 0.25| = 0.45
        assert result.name == "demographic_parity_difference"
        assert result.value == pytest.approx(0.45, abs=0.05)
        assert result.breached is True  # > 0.10 threshold
        assert result.threshold == 0.10

    def test_unbiased(self, unbiased_data):
        y_true, y_pred, y_score, sensitive, priv = unbiased_data
        result = demographic_parity_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.value == pytest.approx(0.0, abs=0.02)
        assert result.breached is False

    def test_confidence_interval_contains_value(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = demographic_parity_difference(y_true, y_pred, y_score, sensitive, priv)

        ci_low, ci_high = result.confidence_interval
        assert ci_low <= result.value <= ci_high


# ── Test: Metric 2 — Equalized Odds Difference ──────────────────────────────

class TestEqualizedOddsDifference:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = equalized_odds_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "equalized_odds_difference"
        assert result.breached is True  # > 0.08 threshold
        assert result.value > 0.08

    def test_unbiased(self, unbiased_data):
        y_true, y_pred, y_score, sensitive, priv = unbiased_data
        result = equalized_odds_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.value == pytest.approx(0.0, abs=0.05)


# ── Test: Metric 3 — Equal Opportunity Difference ───────────────────────────

class TestEqualOpportunityDifference:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = equal_opportunity_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "equal_opportunity_difference"
        assert result.breached is True  # > 0.05
        assert result.value > 0.05


# ── Test: Metric 4 — Disparate Impact Ratio ─────────────────────────────────

class TestDisparateImpactRatio:
    def test_heavily_biased_eeoc_violation(self, heavily_biased_data):
        """
        DoD anchor: disparate_impact_ratio ≈ 0.36 for UCI Adult-like data.
        Well below 0.80 EEOC 4/5ths rule threshold.
        """
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = disparate_impact_ratio(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "disparate_impact_ratio"
        # Female rate (0.25) / Male rate (0.70) ≈ 0.357
        assert result.value == pytest.approx(0.357, abs=0.05)
        assert result.breached is True  # < 0.80 threshold
        assert result.threshold == 0.80

    def test_unbiased(self, unbiased_data):
        y_true, y_pred, y_score, sensitive, priv = unbiased_data
        result = disparate_impact_ratio(y_true, y_pred, y_score, sensitive, priv)

        assert result.value == pytest.approx(1.0, abs=0.05)
        assert result.breached is False

    def test_mildly_biased_passes(self, mildly_biased_data):
        y_true, y_pred, y_score, sensitive, priv = mildly_biased_data
        result = disparate_impact_ratio(y_true, y_pred, y_score, sensitive, priv)

        # Female 48% / Male 55% ≈ 0.87 — above 0.80 threshold
        assert result.value > 0.80
        assert result.breached is False


# ── Test: Metric 5 — Average Odds Difference ────────────────────────────────

class TestAverageOddsDifference:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = average_odds_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "average_odds_difference"
        assert result.value > 0.07  # Breached
        assert result.breached is True


# ── Test: Metric 6 — Statistical Parity Subgroup Lift ────────────────────────

class TestStatisticalParitySubgroupLift:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = statistical_parity_subgroup_lift(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "statistical_parity_subgroup_lift"
        # max(0.70, 0.25) / min(0.70, 0.25) = 0.70/0.25 = 2.80
        assert result.value == pytest.approx(2.80, abs=0.2)
        assert result.breached is True  # > 1.25

    def test_unbiased(self, unbiased_data):
        y_true, y_pred, y_score, sensitive, priv = unbiased_data
        result = statistical_parity_subgroup_lift(y_true, y_pred, y_score, sensitive, priv)

        assert result.value == pytest.approx(1.0, abs=0.1)
        assert result.breached is False


# ── Test: Metric 7 — Predictive Parity Difference ───────────────────────────

class TestPredictiveParityDifference:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = predictive_parity_difference(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "predictive_parity_difference"
        assert isinstance(result.value, float)


# ── Test: Metric 8 — Calibration Gap ────────────────────────────────────────

class TestCalibrationGap:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = calibration_gap(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "calibration_gap"
        assert isinstance(result.value, float)
        assert result.value >= 0.0


# ── Test: Metric 9 — Individual Fairness Score ──────────────────────────────

class TestIndividualFairnessScore:
    def test_returns_valid_score(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = individual_fairness_score(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "individual_fairness_score"
        assert 0.0 <= result.value <= 1.0


# ── Test: Metric 10 — Counterfactual Fairness ───────────────────────────────

class TestCounterfactualFairness:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = counterfactual_fairness(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "counterfactual_fairness"
        # Male 70% vs Female 25% → diff = 0.45
        assert result.value == pytest.approx(0.45, abs=0.05)
        assert result.breached is True  # > 0.06

    def test_unbiased(self, unbiased_data):
        y_true, y_pred, y_score, sensitive, priv = unbiased_data
        result = counterfactual_fairness(y_true, y_pred, y_score, sensitive, priv)

        assert result.value == pytest.approx(0.0, abs=0.05)


# ── Test: Metric 11 — Intersectional Bias Score ─────────────────────────────

class TestIntersectionalBiasScore:
    def test_heavily_biased(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = intersectional_bias_score(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "intersectional_bias_score"
        assert result.value > 0.12  # Breached


# ── Test: Metric 12 — Temporal Drift Index ───────────────────────────────────

class TestTemporalDriftIndex:
    def test_no_drift(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        result = temporal_drift_index(y_true, y_pred, y_score, sensitive, priv)

        assert result.name == "temporal_drift_index"
        assert isinstance(result.value, float)

    def test_with_historical_drift(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        # Simulate drift: low values then sudden jump
        historical = [0.05, 0.06, 0.04, 0.05, 0.07, 0.06,
                      0.30, 0.35, 0.40, 0.38, 0.42, 0.45]
        result = temporal_drift_index(
            y_true, y_pred, y_score, sensitive, priv,
            historical_metrics=historical,
        )

        assert result.value > 0  # Should detect drift


# ── Test: compute_all_metrics ────────────────────────────────────────────────

class TestComputeAllMetrics:
    def test_returns_all_metrics(self, heavily_biased_data):
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        results = compute_all_metrics(y_true, y_pred, y_score, sensitive, priv)

        assert len(results) >= 10
        for name in [
            "demographic_parity_difference",
            "equalized_odds_difference",
            "disparate_impact_ratio",
            "counterfactual_fairness",
        ]:
            assert name in results

    def test_heavily_biased_triggers_critical(self, heavily_biased_data):
        """Sprint 2 DoD: DI ≈ 0.38 → CRITICAL severity."""
        y_true, y_pred, y_score, sensitive, priv = heavily_biased_data
        results = compute_all_metrics(y_true, y_pred, y_score, sensitive, priv)

        di = results["disparate_impact_ratio"]
        assert di.value < 0.65  # Should trigger CRITICAL
        assert di.breached is True
