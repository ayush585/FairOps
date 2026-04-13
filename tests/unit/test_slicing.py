"""
Unit tests for demographic slice construction.

Ref: AGENT.md Section 5 (DemographicSlice schema).
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "auditor"))

from fairops_sdk.schemas import DemographicSlice
from slicing import build_demographic_slices, build_intersectional_slices


class TestBuildDemographicSlices:
    def test_two_groups(self):
        y_true = np.array([1, 1, 0, 0, 1, 1, 0, 0])
        y_pred = np.array([1, 1, 0, 0, 1, 0, 0, 0])
        sensitive = np.array(["Male", "Male", "Male", "Male",
                              "Female", "Female", "Female", "Female"])

        slices = build_demographic_slices(y_true, y_pred, sensitive, "sex")

        assert len(slices) == 2

        male_slice = next(s for s in slices if s.group_value == "Male")
        female_slice = next(s for s in slices if s.group_value == "Female")

        assert male_slice.count == 4
        assert female_slice.count == 4
        assert male_slice.attribute == "sex"
        assert male_slice.positive_rate == pytest.approx(0.5, abs=0.01)
        assert female_slice.positive_rate == pytest.approx(0.25, abs=0.01)

    def test_three_groups(self):
        y_true = np.array([1] * 6 + [0] * 6)
        y_pred = np.array([1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
        sensitive = np.array(["A"] * 4 + ["B"] * 4 + ["C"] * 4)

        slices = build_demographic_slices(y_true, y_pred, sensitive, "group")

        assert len(slices) == 3
        for s in slices:
            assert isinstance(s, DemographicSlice)
            assert s.count == 4

    def test_slice_metrics_computed(self):
        y_true = np.array([1, 1, 0, 0, 1, 0, 0, 0])
        y_pred = np.array([1, 1, 0, 0, 1, 0, 0, 0])
        sensitive = np.array(["A"] * 4 + ["B"] * 4)

        slices = build_demographic_slices(y_true, y_pred, sensitive, "group")

        for s in slices:
            assert "true_positive_rate" in s.metrics
            assert "false_positive_rate" in s.metrics
            assert "precision" in s.metrics
            assert "accuracy" in s.metrics

    def test_empty_group_excluded(self):
        y_true = np.array([1, 0, 1, 0])
        y_pred = np.array([1, 0, 1, 0])
        sensitive = np.array(["A", "A", "A", "A"])

        slices = build_demographic_slices(y_true, y_pred, sensitive, "group")

        assert len(slices) == 1
        assert slices[0].group_value == "A"


class TestBuildIntersectionalSlices:
    def test_cross_product(self):
        n = 100
        y_true = np.random.randint(0, 2, n)
        y_pred = np.random.randint(0, 2, n)
        attr_a = np.array(["Male", "Female"] * 50)
        attr_b = np.array(["White"] * 25 + ["Black"] * 25 + ["White"] * 25 + ["Black"] * 25)

        slices = build_intersectional_slices(
            y_true, y_pred, attr_a, attr_b, "sex", "race"
        )

        assert len(slices) == 4  # Male_White, Male_Black, Female_White, Female_Black
        for s in slices:
            assert "×" in s.attribute  # Intersectional marker
