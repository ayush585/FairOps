"""
FairOps Mitigation Engine — In-Processing Algorithms.

Mitigates bias during the model training phase.
Uses Fairlearn's ExponentiatedGradient approach to enforce
fairness constraints (Demographic Parity / Equalized Odds)
while minimizing error.

Ref: AGENT.md Sprint 4, Section 15.
"""

import logging
from typing import Optional, Literal
import numpy as np
import pandas as pd

logger = logging.getLogger("fairops.mitigation.in_processing")


def apply_exponentiated_gradient(
    estimator,
    X: np.ndarray | pd.DataFrame,
    y: np.ndarray | pd.Series,
    sensitive_features: np.ndarray | pd.Series,
    constraint: Literal["demographic_parity", "equalized_odds"] = "demographic_parity",
    eps: float = 0.01,
    max_iter: int = 50,
):
    """
    Train a mitigated model using Exponentiated Gradient.

    Args:
        estimator: Sklearn-compatible base estimator (must support sample_weight).
        X: Training features.
        y: Training labels.
        sensitive_features: Training sensitive attributes.
        constraint: Fairness constraint to enforce.
        eps: Allowed fairness violation.
        max_iter: Max iterations for optimization.

    Returns:
        Fitted ExponentiatedGradient model.
    """
    try:
        from fairlearn.reductions import ExponentiatedGradient
        from fairlearn.reductions import DemographicParity, EqualizedOdds

        logger.info(
            f"Starting ExponentiatedGradient mitigation (constraint={constraint}, eps={eps})"
        )

        # Select constraint
        if constraint == "equalized_odds":
            fairness_constraint = EqualizedOdds(difference_bound=eps)
        else:
            fairness_constraint = DemographicParity(difference_bound=eps)

        # Initialize and fit
        mitigator = ExponentiatedGradient(
            estimator=estimator,
            constraints=fairness_constraint,
            eps=eps,
            max_iter=max_iter,
        )

        mitigator.fit(X, y, sensitive_features=sensitive_features)

        logger.info("ExponentiatedGradient mitigation complete.")
        return mitigator

    except ImportError:
        logger.error("fairlearn is required for in_processing mitigation.")
        raise
    except Exception as e:
        logger.error(f"In-processing mitigation failed: {e}", exc_info=True)
        raise
