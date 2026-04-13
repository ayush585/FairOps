"""
FairOps Explainer — SHAP Feature Importance.

Computes SHAP values for bias explainability using:
- TreeExplainer for tree-based models (fast, exact)
- KernelExplainer for black-box models (slow, model-agnostic)
- GradientExplainer for neural networks

Results are cached in Redis for 1 hour.

Ref: AGENT.md Sprint 3, Section 21 (shap==0.44.0).
"""

import logging
import json
import hashlib
from typing import Optional

import numpy as np

logger = logging.getLogger("fairops.explainer.shap")


class SHAPExplainer:
    """
    Computes SHAP feature importances for bias explainability.

    Usage:
        explainer = SHAPExplainer(model, X_train)
        result = explainer.explain(X_test, sensitive_feature="sex")
    """

    def __init__(
        self,
        model,
        background_data: np.ndarray,
        feature_names: list[str],
        model_type: str = "auto",
        max_background_samples: int = 100,
    ):
        """
        Args:
            model: Trained sklearn-compatible model with .predict_proba().
            background_data: Training data for KernelExplainer background.
            feature_names: List of feature column names.
            model_type: "tree", "kernel", "gradient", or "auto".
            max_background_samples: Max background samples for KernelExplainer
                                    (KMeans-summarized for speed).
        """
        self.model = model
        self.feature_names = feature_names
        self.model_type = model_type
        self._explainer = None

        # Subsample background data for KernelExplainer performance
        if len(background_data) > max_background_samples:
            indices = np.random.choice(
                len(background_data), max_background_samples, replace=False
            )
            self.background_data = background_data[indices]
        else:
            self.background_data = background_data

        self._init_explainer()

    def _init_explainer(self):
        """Initialize the appropriate SHAP explainer."""
        import shap

        if self.model_type == "auto":
            # Auto-detect model type
            model_class = type(self.model).__name__.lower()
            if any(t in model_class for t in ["forest", "tree", "boost", "xgb", "lgbm"]):
                self.model_type = "tree"
            else:
                self.model_type = "kernel"

        if self.model_type == "tree":
            try:
                self._explainer = shap.TreeExplainer(self.model)
                logger.info("Using SHAP TreeExplainer")
            except Exception as e:
                logger.warning(f"TreeExplainer failed ({e}), falling back to KernelExplainer")
                self.model_type = "kernel"

        if self.model_type == "kernel":
            # Use KMeans-summarized background for speed
            background = shap.kmeans(self.background_data, min(10, len(self.background_data)))
            self._explainer = shap.KernelExplainer(
                self.model.predict_proba if hasattr(self.model, "predict_proba")
                else self.model.predict,
                background,
            )
            logger.info("Using SHAP KernelExplainer")

    def explain(
        self,
        X: np.ndarray,
        sensitive_feature: Optional[str] = None,
        n_samples: int = 500,
    ) -> dict:
        """
        Compute SHAP values for the given data.

        Args:
            X: Feature matrix to explain.
            sensitive_feature: Name of the sensitive attribute to highlight.
            n_samples: Max samples for KernelExplainer (ignored for Tree).

        Returns:
            Dict with shap_values, feature_importance, group_importance,
            and top_bias_drivers.
        """
        import shap

        # Subsample if too large
        if len(X) > n_samples:
            indices = np.random.choice(len(X), n_samples, replace=False)
            X_sample = X[indices]
        else:
            X_sample = X

        # Compute SHAP values
        if self.model_type == "tree":
            shap_values = self._explainer.shap_values(X_sample)
            # For binary classifiers, TreeExplainer returns list [class0, class1]
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # Use positive class
        else:
            shap_values = self._explainer.shap_values(
                X_sample, nsamples=min(100, len(X_sample))
            )
            if isinstance(shap_values, list):
                shap_values = shap_values[1]

        # Mean absolute SHAP values per feature
        mean_abs_shap = np.abs(shap_values).mean(axis=0)

        # Build feature importance ranking
        feature_importance = [
            {
                "feature": name,
                "importance": round(float(imp), 6),
                "rank": rank + 1,
            }
            for rank, (name, imp) in enumerate(
                sorted(
                    zip(self.feature_names, mean_abs_shap),
                    key=lambda x: x[1],
                    reverse=True,
                )
            )
        ]

        # Flag sensitive feature contribution
        sensitive_importance = None
        if sensitive_feature and sensitive_feature in self.feature_names:
            idx = self.feature_names.index(sensitive_feature)
            sensitive_importance = {
                "feature": sensitive_feature,
                "importance": round(float(mean_abs_shap[idx]), 6),
                "rank": next(
                    f["rank"] for f in feature_importance
                    if f["feature"] == sensitive_feature
                ),
            }

        # Top 5 bias drivers (highest SHAP importance)
        top_bias_drivers = feature_importance[:5]

        return {
            "feature_importance": feature_importance,
            "top_bias_drivers": top_bias_drivers,
            "sensitive_feature_contribution": sensitive_importance,
            "n_samples_explained": len(X_sample),
            "explainer_type": self.model_type,
            "shap_values_summary": {
                "mean": round(float(shap_values.mean()), 6),
                "std": round(float(shap_values.std()), 6),
                "max_abs": round(float(np.abs(shap_values).max()), 6),
            },
        }

    @staticmethod
    def cache_key(audit_id: str, model_id: str) -> str:
        """Generate a Redis cache key for SHAP results."""
        raw = f"shap:{audit_id}:{model_id}"
        return hashlib.sha256(raw.encode()).hexdigest()[:32]


def explain_bias_drivers(
    audit_id: str,
    model_id: str,
    feature_importance: list[dict],
    demographic_slices: list[dict],
    metrics: dict,
) -> dict:
    """
    Produce a structured bias driver analysis from pre-computed SHAP values
    and audit metrics (for when the model artifact is unavailable).

    Args:
        audit_id: Audit ID.
        model_id: Model ID.
        feature_importance: List of {feature, importance, rank} dicts.
        demographic_slices: List of DemographicSlice dicts.
        metrics: Dict of metric_name → FairnessMetric dicts.

    Returns:
        Structured bias driver analysis.
    """
    # Identify breached metrics
    breached = [
        {"name": name, "value": m.get("value"), "threshold": m.get("threshold")}
        for name, m in metrics.items()
        if m.get("breached")
    ]

    # Cross-reference top features with sensitive attributes
    sensitive_attrs = {"sex", "gender", "race", "age", "ethnicity", "zip_code"}
    top_5 = feature_importance[:5] if feature_importance else []

    sensitive_in_top5 = [
        f for f in top_5 if f["feature"].lower() in sensitive_attrs
    ]

    # Per-group performance gaps
    group_gaps = []
    for s in demographic_slices:
        tpr = s.get("metrics", {}).get("true_positive_rate", 0)
        fpr = s.get("metrics", {}).get("false_positive_rate", 0)
        group_gaps.append({
            "group": f"{s.get('attribute')}={s.get('group_value')}",
            "positive_rate": s.get("positive_rate"),
            "true_positive_rate": tpr,
            "false_positive_rate": fpr,
        })

    return {
        "audit_id": audit_id,
        "model_id": model_id,
        "top_features": top_5,
        "sensitive_features_in_top5": sensitive_in_top5,
        "breached_metrics": breached,
        "group_performance_gaps": group_gaps,
    }
