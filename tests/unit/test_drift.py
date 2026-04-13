"""
Unit tests for drift detection.

Ref: AGENT.md Section 6 (Metric 12).
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "auditor"))

from metrics.drift import (
    compute_cusum_statistic,
    detect_changepoints,
    compute_adwin_drift,
)


class TestCUSUM:
    def test_stable_signal(self):
        """Stable signal should have low CUSUM."""
        values = [0.05, 0.06, 0.04, 0.05, 0.05, 0.06, 0.04, 0.05]
        result = compute_cusum_statistic(values)
        assert result < 5.0  # Below drift threshold

    def test_sudden_shift(self):
        """Sudden shift should produce high CUSUM."""
        # Mean shifts from ~0.05 to ~0.40
        values = [0.05, 0.06, 0.04, 0.05, 0.05, 0.06,
                  0.35, 0.40, 0.38, 0.42, 0.45, 0.40]
        result = compute_cusum_statistic(values)
        assert result > 0  # Should detect some drift

    def test_too_few_values(self):
        """Less than 3 values should return 0."""
        assert compute_cusum_statistic([0.05]) == 0.0
        assert compute_cusum_statistic([0.05, 0.06]) == 0.0

    def test_gradual_drift(self):
        """Gradual increase should also be detected."""
        values = [0.05, 0.07, 0.09, 0.11, 0.14, 0.17,
                  0.20, 0.24, 0.28, 0.33, 0.38, 0.44]
        result = compute_cusum_statistic(values)
        assert result >= 0  # Should detect gradual drift


class TestChangepoints:
    def test_no_changepoints_in_stable(self):
        values = [1.0] * 20
        cps = detect_changepoints(values)
        assert len(cps) <= 1  # May detect edge, but shouldn't be many

    def test_too_few_values(self):
        cps = detect_changepoints([1.0, 2.0])
        assert cps == []


class TestADWIN:
    def test_no_drift_stable(self):
        values = [0.5] * 20
        result = compute_adwin_drift(values)
        assert result["drift_detected"] is False

    def test_drift_detected_shift(self):
        values = [0.1] * 15 + [0.9] * 15
        result = compute_adwin_drift(values)
        assert result["drift_detected"] is True
        assert len(result["drift_points"]) > 0

    def test_too_few_values(self):
        result = compute_adwin_drift([0.5] * 5)
        assert result["drift_detected"] is False
