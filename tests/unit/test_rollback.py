"""
Unit tests for Rollback checks.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "mitigation"))

def test_no_rollback_on_improvement():
    from rollback import evaluate_mitigation_degradation

    metrics_before = {"demographic_parity_difference": 0.25}
    metrics_after = {"demographic_parity_difference": 0.05} # huge fairness improvement

    result = evaluate_mitigation_degradation(
        accuracy_before=0.90,
        accuracy_after=0.85, # 5% drop is within 15% threshold
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        max_accuracy_drop=0.15
    )

    assert result["roll_back"] is False
    assert result["severe_degradation"] is False
    assert result["fairness_improved"] is True


def test_rollback_on_severe_degradation():
    from rollback import evaluate_mitigation_degradation

    metrics_before = {"demographic_parity_difference": 0.25}
    metrics_after = {"demographic_parity_difference": 0.05}

    result = evaluate_mitigation_degradation(
        accuracy_before=0.90,
        accuracy_after=0.70, # 20% drop!
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        max_accuracy_drop=0.15
    )

    assert result["roll_back"] is True
    assert result["severe_degradation"] is True
    assert "unacceptable accuracy drop" in result["reason"]


def test_rollback_when_fairness_gets_worse():
    from rollback import evaluate_mitigation_degradation

    metrics_before = {"disparate_impact_ratio": 0.85}
    metrics_after = {"disparate_impact_ratio": 0.70} # distance from 1.0 increased

    result = evaluate_mitigation_degradation(
        accuracy_before=0.90,
        accuracy_after=0.88,
        metrics_before=metrics_before,
        metrics_after=metrics_after,
        max_accuracy_drop=0.15
    )

    assert result["roll_back"] is True
    assert result["severe_degradation"] is False
    assert result["fairness_improved"] is False
    assert "failed to improve" in result["reason"]
