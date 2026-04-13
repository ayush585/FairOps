"""
Unit tests for severity classification.

Ref: AGENT.md Section 7.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "auditor"))

from fairops_sdk.schemas import FairnessMetric, Severity
from severity import classify_overall_severity, get_required_action


def _make_metric(name, value, threshold, breached, p_value=0.001) -> FairnessMetric:
    """Helper to create a FairnessMetric for testing."""
    return FairnessMetric(
        name=name,
        value=value,
        threshold=threshold,
        breached=breached,
        confidence_interval=(value - 0.02, value + 0.02),
        severity=Severity.MEDIUM,  # Will be overridden by classifier
        groups_compared=("Male", "Female"),
        sample_sizes=(500, 500),
        p_value=p_value,
    )


class TestSeverityClassification:
    def test_pass_no_breaches(self):
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.05, 0.10, False),
            "disparate_impact_ratio": _make_metric("disparate_impact_ratio", 0.90, 0.80, False),
        }
        assert classify_overall_severity(metrics) == Severity.PASS

    def test_critical_di_below_065(self):
        """CRITICAL: disparate_impact_ratio < 0.65"""
        metrics = {
            "disparate_impact_ratio": _make_metric("disparate_impact_ratio", 0.38, 0.80, True),
        }
        assert classify_overall_severity(metrics) == Severity.CRITICAL

    def test_critical_3x_threshold(self):
        """CRITICAL: any metric > 3x threshold"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.35, 0.10, True),
        }
        # 0.35 / 0.10 = 3.5x → CRITICAL
        assert classify_overall_severity(metrics) == Severity.CRITICAL

    def test_critical_3_plus_breached(self):
        """CRITICAL: 3+ metrics breached simultaneously"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.15, 0.10, True),
            "equalized_odds_difference": _make_metric("equalized_odds_difference", 0.12, 0.08, True),
            "equal_opportunity_difference": _make_metric("equal_opportunity_difference", 0.08, 0.05, True),
        }
        assert classify_overall_severity(metrics) == Severity.CRITICAL

    def test_high_di_in_065_080(self):
        """HIGH: disparate_impact_ratio in [0.65, 0.80)"""
        metrics = {
            "disparate_impact_ratio": _make_metric("disparate_impact_ratio", 0.72, 0.80, True),
        }
        assert classify_overall_severity(metrics) == Severity.HIGH

    def test_high_2x_threshold(self):
        """HIGH: metric value in (2x, 3x) threshold"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.25, 0.10, True),
        }
        # 0.25 / 0.10 = 2.5x → HIGH
        assert classify_overall_severity(metrics) == Severity.HIGH

    def test_high_2_breached(self):
        """HIGH: exactly 2 metrics breached"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.12, 0.10, True),
            "equalized_odds_difference": _make_metric("equalized_odds_difference", 0.10, 0.08, True),
        }
        assert classify_overall_severity(metrics) == Severity.HIGH

    def test_medium_1_breached_significant(self):
        """MEDIUM: 1 breached, < 2x threshold, p_value < 0.05"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.15, 0.10, True, p_value=0.01),
        }
        assert classify_overall_severity(metrics) == Severity.MEDIUM

    def test_low_breached_but_not_significant(self):
        """LOW: breached but p_value > 0.05"""
        metrics = {
            "demographic_parity_difference": _make_metric("demographic_parity_difference", 0.12, 0.10, True, p_value=0.15),
        }
        assert classify_overall_severity(metrics) == Severity.LOW


class TestRequiredAction:
    def test_critical_triggers_pipeline(self):
        action = get_required_action(Severity.CRITICAL)
        assert action["action"] == "TRIGGER_PIPELINE"
        assert action["delay_seconds"] == 0
        assert action["notify"] is True

    def test_high_queues_pipeline(self):
        action = get_required_action(Severity.HIGH)
        assert action["action"] == "QUEUE_PIPELINE"
        assert action["delay_seconds"] == 3600

    def test_pass_logs_clean(self):
        action = get_required_action(Severity.PASS)
        assert action["action"] == "LOG_CLEAN"
        assert action["notify"] is False
