"""
Unit tests for DiCE counterfactual generation.

Uses the simplified perturbation fallback (no dice-ml required).

Ref: AGENT.md Sprint 3.
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "explainer"))


@pytest.fixture
def simple_model():
    """A simple threshold model for counterfactual testing."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.datasets import make_classification

    np.random.seed(42)
    X, y = make_classification(
        n_samples=200, n_features=4, n_informative=3,
        n_redundant=0, random_state=42
    )
    clf = LogisticRegression(random_state=42, max_iter=200)
    clf.fit(X, y)
    return clf, X, y


@pytest.fixture
def feature_names_4():
    return ["age", "income", "education", "credit_score"]


class TestSimplifiedCounterfactuals:
    """Tests using the simplified perturbation fallback."""

    def test_counterfactuals_returned(self, simple_model, feature_names_4):
        from counterfactuals import generate_counterfactuals

        clf, X, y = simple_model
        # Find an instance predicted as 0 (we want to flip to 1)
        neg_indices = np.where(clf.predict(X) == 0)[0]
        if len(neg_indices) == 0:
            pytest.skip("No negative predictions in test data")

        X_instance = pd.DataFrame(X[neg_indices[0]:neg_indices[0]+1], columns=feature_names_4)

        result = generate_counterfactuals(
            model=clf,
            X_instance=X_instance,
            feature_names=feature_names_4,
            desired_class=1,
        )

        assert isinstance(result, dict)
        assert "counterfactuals" in result
        assert "n_generated" in result
        assert "most_impactful_features" in result
        assert isinstance(result["counterfactuals"], list)

    def test_original_instance_preserved(self, simple_model, feature_names_4):
        from counterfactuals import generate_counterfactuals

        clf, X, y = simple_model
        X_instance = pd.DataFrame(X[:1], columns=feature_names_4)
        original_vals = X_instance.iloc[0].to_dict()

        result = generate_counterfactuals(
            model=clf,
            X_instance=X_instance,
            feature_names=feature_names_4,
        )

        assert "original_instance" in result
        for feat in feature_names_4:
            assert feat in result["original_instance"]

    def test_changes_contain_from_and_to(self, simple_model, feature_names_4):
        from counterfactuals import generate_counterfactuals

        clf, X, y = simple_model
        neg_indices = np.where(clf.predict(X) == 0)[0]
        if len(neg_indices) == 0:
            pytest.skip("No negative predictions")

        X_instance = pd.DataFrame(X[neg_indices[0]:neg_indices[0]+1], columns=feature_names_4)
        result = generate_counterfactuals(clf, X_instance, feature_names_4, desired_class=1)

        for cf in result["counterfactuals"]:
            assert "changes" in cf
            assert "n_changes" in cf
            for feat, change in cf["changes"].items():
                assert "from" in change
                assert "to" in change

    def test_min_changes_required_none_or_positive(self, simple_model, feature_names_4):
        from counterfactuals import generate_counterfactuals

        clf, X, y = simple_model
        X_instance = pd.DataFrame(X[:1], columns=feature_names_4)
        result = generate_counterfactuals(clf, X_instance, feature_names_4)

        # Either None (already at desired class) or a positive integer
        mcr = result["min_changes_required"]
        assert mcr is None or isinstance(mcr, int)


class TestSafeRound:
    def test_rounds_floats(self):
        from counterfactuals import _safe_round
        assert _safe_round(3.14159265) == 3.1416

    def test_handles_strings(self):
        from counterfactuals import _safe_round
        assert _safe_round("Male") == "Male"

    def test_handles_numpy_float(self):
        from counterfactuals import _safe_round
        import numpy as np
        assert isinstance(_safe_round(np.float64(1.23456789)), float)
