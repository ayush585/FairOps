"""
Unit tests for SHAP explainer.

Tests both the real SHAPExplainer class (with a small sklearn model)
and the explain_bias_drivers proxy.

Ref: AGENT.md Sprint 3.
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "explainer"))


@pytest.fixture
def binary_classifier():
    """Train a small RandomForest for SHAP testing."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.datasets import make_classification

    np.random.seed(42)
    X, y = make_classification(
        n_samples=300, n_features=6, n_informative=4,
        n_redundant=0, random_state=42
    )
    clf = RandomForestClassifier(n_estimators=10, max_depth=4, random_state=42)
    clf.fit(X, y)
    return clf, X, y


@pytest.fixture
def feature_names():
    return ["age", "income", "education", "credit_score", "sex", "race"]


class TestSHAPExplainer:
    def test_tree_explainer_produces_importances(self, binary_classifier, feature_names):
        from shap_explainer import SHAPExplainer

        clf, X, y = binary_classifier
        explainer = SHAPExplainer(
            model=clf,
            background_data=X[:50],
            feature_names=feature_names,
            model_type="tree",
        )
        result = explainer.explain(X[:20], sensitive_feature="sex")

        assert "feature_importance" in result
        assert "top_bias_drivers" in result
        assert "sensitive_feature_contribution" in result
        assert len(result["feature_importance"]) == len(feature_names)

    def test_feature_importance_ranked(self, binary_classifier, feature_names):
        from shap_explainer import SHAPExplainer

        clf, X, y = binary_classifier
        explainer = SHAPExplainer(clf, X[:50], feature_names, model_type="tree")
        result = explainer.explain(X[:20])

        importances = result["feature_importance"]
        # Verify descending order by importance
        vals = [f["importance"] for f in importances]
        assert vals == sorted(vals, reverse=True)

    def test_sensitive_feature_highlighted(self, binary_classifier, feature_names):
        from shap_explainer import SHAPExplainer

        clf, X, y = binary_classifier
        explainer = SHAPExplainer(clf, X[:50], feature_names, model_type="tree")
        result = explainer.explain(X[:20], sensitive_feature="sex")

        sc = result["sensitive_feature_contribution"]
        assert sc is not None
        assert sc["feature"] == "sex"
        assert isinstance(sc["importance"], float)

    def test_top_bias_drivers_is_top_5(self, binary_classifier, feature_names):
        from shap_explainer import SHAPExplainer

        clf, X, y = binary_classifier
        explainer = SHAPExplainer(clf, X[:50], feature_names, model_type="tree")
        result = explainer.explain(X[:20])

        assert len(result["top_bias_drivers"]) == min(5, len(feature_names))

    def test_auto_detects_tree_model(self, binary_classifier, feature_names):
        from shap_explainer import SHAPExplainer

        clf, X, y = binary_classifier
        explainer = SHAPExplainer(clf, X[:50], feature_names, model_type="auto")
        # Should auto-detect as tree
        result = explainer.explain(X[:10])
        assert result["explainer_type"] == "tree"


class TestExplainBiasDrivers:
    def test_returns_structured_dict(self, feature_names):
        from shap_explainer import explain_bias_drivers

        feature_importance = [
            {"feature": "income", "importance": 0.45, "rank": 1},
            {"feature": "sex", "importance": 0.30, "rank": 2},
            {"feature": "race", "importance": 0.15, "rank": 3},
        ]
        metrics = {
            "demographic_parity_difference": {
                "value": 0.35, "threshold": 0.10, "breached": True
            },
            "disparate_impact_ratio": {
                "value": 0.38, "threshold": 0.80, "breached": True
            },
        }
        demographic_slices = [
            {
                "attribute": "sex", "group_value": "Male",
                "positive_rate": 0.70, "count": 500,
                "metrics": {"true_positive_rate": 0.85, "false_positive_rate": 0.20},
            },
        ]

        result = explain_bias_drivers(
            audit_id="test-audit-001",
            model_id="hiring-model-v1",
            feature_importance=feature_importance,
            demographic_slices=demographic_slices,
            metrics=metrics,
        )

        assert result["audit_id"] == "test-audit-001"
        assert result["model_id"] == "hiring-model-v1"
        assert len(result["breached_metrics"]) == 2
        assert len(result["group_performance_gaps"]) == 1

    def test_sensitive_features_in_top5_detected(self, feature_names):
        from shap_explainer import explain_bias_drivers

        feature_importance = [
            {"feature": "sex", "importance": 0.45, "rank": 1},  # Sensitive!
            {"feature": "income", "importance": 0.30, "rank": 2},
        ]

        result = explain_bias_drivers(
            audit_id="test-001",
            model_id="model-v1",
            feature_importance=feature_importance,
            demographic_slices=[],
            metrics={},
        )

        sensitive_in_top5 = result["sensitive_features_in_top5"]
        assert any(f["feature"] == "sex" for f in sensitive_in_top5)
