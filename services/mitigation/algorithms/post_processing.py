"""
FairOps Mitigation Engine — Post-Processing Algorithms.

Mitigates bias applied to predictions of an already-trained model.
Uses Fairlearn's ThresholdOptimizer to find group-specific thresholds
that balance fairness constraints against predictive performance.

Ref: AGENT.md Sprint 4, Section 15.
"""

import logging
from typing import Optional, Literal
import numpy as np
import pandas as pd

logger = logging.getLogger("fairops.mitigation.post_processing")


def apply_threshold_optimizer(
    estimator,
    X: np.ndarray | pd.DataFrame,
    y: np.ndarray | pd.Series,
    sensitive_features: np.ndarray | pd.Series,
    constraint: Literal["demographic_parity", "equalized_odds"] = "demographic_parity",
    objective: str = "accuracy_score",
    prefit: bool = False,
):
    """
    Train a mitigated post-processing wrapper using ThresholdOptimizer.

    Args:
        estimator: Sklearn-compatible base estimator (must support predict_proba or decision_function).
                   If prefit=True, the estimator must already be fitted.
        X: Validation features to fine-tune thresholds.
        y: Validation labels.
        sensitive_features: Validation sensitive attributes.
        constraint: Fairness constraint to enforce.
        objective: Metric to optimize (e.g. 'accuracy_score', 'balanced_accuracy_score').
        prefit: If True, do not call fit() on the base estimator, only calibrate thresholds.

    Returns:
        Fitted ThresholdOptimizer wrapper.
    """
    try:
        from fairlearn.postprocessing import ThresholdOptimizer

        logger.info(
            f"Starting ThresholdOptimizer post-processing (constraint={constraint}, "
            f"objective={objective}, prefit={prefit})"
        )

        # Initialize
        mitigator = ThresholdOptimizer(
            estimator=estimator,
            constraints=constraint,
            objective=objective,
            prefit=prefit,
            predict_method="predict_proba" if hasattr(estimator, "predict_proba") else "auto",
        )

        # Fit thresholds based on validation set
        mitigator.fit(X, y, sensitive_features=sensitive_features)

        logger.info("ThresholdOptimizer mitigation complete.")
        return mitigator

    except ImportError:
        logger.error("fairlearn is required for post_processing mitigation.")
        raise
    except Exception as e:
        logger.error(f"Post-processing mitigation failed: {e}", exc_info=True)
        raise
