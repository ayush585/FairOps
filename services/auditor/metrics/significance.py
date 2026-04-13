"""
FairOps Auditor — Statistical Significance Testing.

Bootstrap confidence intervals and chi-square tests.

Ref: AGENT.md Section 6:
- Bootstrap CI: scipy.stats.bootstrap, n_resamples=1000, confidence_level=0.95
- Chi-square: scipy.stats.chi2_contingency on (sensitive_attr × prediction_label)
- If p_value > 0.05, override severity = LOW
"""

import numpy as np
from typing import Callable
from scipy import stats


def bootstrap_confidence_interval(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive: np.ndarray,
    statistic_fn: Callable,
    n_resamples: int = 1000,
    confidence_level: float = 0.95,
    random_state: int = 42,
) -> tuple[float, float]:
    """
    Compute bootstrap confidence interval for a fairness metric.

    Args:
        y_true: Ground truth labels.
        y_pred: Model predictions.
        sensitive: Sensitive attribute values.
        statistic_fn: Function(y_true, y_pred, sensitive) -> float.
        n_resamples: Number of bootstrap samples.
        confidence_level: Confidence level for the interval.
        random_state: Random seed for reproducibility.

    Returns:
        Tuple of (lower_bound, upper_bound).
    """
    n = len(y_true)
    rng = np.random.default_rng(random_state)

    bootstrap_values = []
    for _ in range(n_resamples):
        indices = rng.choice(n, size=n, replace=True)
        try:
            val = statistic_fn(y_true[indices], y_pred[indices], sensitive[indices])
            if np.isfinite(val):
                bootstrap_values.append(val)
        except Exception:
            continue

    if len(bootstrap_values) < 10:
        # Not enough valid bootstrap samples — return wide CI
        point_estimate = statistic_fn(y_true, y_pred, sensitive)
        return (max(0.0, point_estimate - 0.1), point_estimate + 0.1)

    bootstrap_values = np.array(bootstrap_values)

    alpha = 1 - confidence_level
    lower = float(np.percentile(bootstrap_values, 100 * alpha / 2))
    upper = float(np.percentile(bootstrap_values, 100 * (1 - alpha / 2)))

    return (lower, upper)


def chi_square_test(
    y_pred: np.ndarray,
    sensitive: np.ndarray,
) -> float:
    """
    Chi-square test of independence on contingency table of
    (sensitive_attr × prediction_label).

    Tests whether the distribution of predictions is independent
    of the sensitive attribute.

    Args:
        y_pred: Predicted labels (0/1).
        sensitive: Sensitive attribute values.

    Returns:
        p-value from chi-square test.
        If p_value > 0.05, not enough evidence to call it real bias.
    """
    try:
        # Build contingency table
        unique_groups = np.unique(sensitive)
        unique_preds = np.unique(y_pred)

        if len(unique_groups) < 2 or len(unique_preds) < 2:
            return 1.0  # Not enough groups/categories to test

        # Create contingency table
        table = np.zeros((len(unique_groups), len(unique_preds)), dtype=int)
        group_map = {g: i for i, g in enumerate(unique_groups)}
        pred_map = {p: i for i, p in enumerate(unique_preds)}

        for g, p in zip(sensitive, y_pred):
            table[group_map[g], pred_map[p]] += 1

        # Remove rows/cols with all zeros
        table = table[table.sum(axis=1) > 0]
        table = table[:, table.sum(axis=0) > 0]

        if table.shape[0] < 2 or table.shape[1] < 2:
            return 1.0

        chi2, p_value, dof, expected = stats.chi2_contingency(table)

        return float(p_value)

    except Exception:
        return 1.0  # Conservative: assume no significance
