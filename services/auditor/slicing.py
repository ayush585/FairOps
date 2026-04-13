"""
FairOps Auditor — Demographic Slice Construction.

Constructs demographic slices from enriched prediction data
for per-group fairness analysis.

Ref: AGENT.md Section 5 (DemographicSlice schema).
"""

import numpy as np
import logging
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
from fairops_sdk.schemas import DemographicSlice

logger = logging.getLogger("fairops.auditor.slicing")


def build_demographic_slices(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive: np.ndarray,
    attribute_name: str,
    metric_values: Optional[dict[str, float]] = None,
) -> list[DemographicSlice]:
    """
    Build DemographicSlice objects for each unique group in the sensitive attribute.

    Args:
        y_true: Ground truth labels (0/1).
        y_pred: Predicted labels (0/1).
        sensitive: Sensitive attribute values (e.g., ["Male", "Female", ...]).
        attribute_name: Name of the sensitive attribute (e.g., "sex").
        metric_values: Optional pre-computed metrics per group.

    Returns:
        List of DemographicSlice objects, one per unique group.
    """
    groups = np.unique(sensitive)
    slices = []

    for group in groups:
        mask = sensitive == group
        group_count = int(mask.sum())

        if group_count == 0:
            continue

        group_preds = y_pred[mask]
        group_truth = y_true[mask]

        # Compute positive rate (selection rate)
        positive_rate = float(group_preds.mean())

        # Compute per-group metrics
        group_metrics = _compute_group_metrics(group_truth, group_preds)

        if metric_values:
            group_metrics.update({
                k: v for k, v in metric_values.items()
                if isinstance(v, (int, float))
            })

        slices.append(DemographicSlice(
            attribute=attribute_name,
            group_value=str(group),
            count=group_count,
            positive_rate=round(positive_rate, 6),
            metrics=group_metrics,
        ))

    logger.info(
        f"Built {len(slices)} demographic slices for attribute '{attribute_name}'",
        extra={"groups": [s.group_value for s in slices]},
    )

    return slices


def _compute_group_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, float]:
    """Compute basic performance metrics for a demographic group."""
    metrics = {}

    total = len(y_true)
    if total == 0:
        return metrics

    metrics["count"] = float(total)
    metrics["positive_rate"] = float(y_pred.mean())
    metrics["base_rate"] = float(y_true.mean())

    # Confusion matrix components
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    tn = int(((y_true == 0) & (y_pred == 0)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    fn = int(((y_true == 1) & (y_pred == 0)).sum())

    metrics["true_positive_rate"] = tp / max(tp + fn, 1)
    metrics["false_positive_rate"] = fp / max(fp + tn, 1)
    metrics["true_negative_rate"] = tn / max(tn + fp, 1)
    metrics["false_negative_rate"] = fn / max(fn + tp, 1)
    metrics["precision"] = tp / max(tp + fp, 1)
    metrics["accuracy"] = (tp + tn) / max(total, 1)

    return {k: round(v, 6) for k, v in metrics.items()}


def build_intersectional_slices(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    sensitive_a: np.ndarray,
    sensitive_b: np.ndarray,
    attr_a_name: str,
    attr_b_name: str,
) -> list[DemographicSlice]:
    """
    Build intersectional demographic slices from two sensitive attributes.

    Creates slices for every (attr_a_val, attr_b_val) cross-product.

    Args:
        y_true: Ground truth labels.
        y_pred: Predicted labels.
        sensitive_a: First sensitive attribute values.
        sensitive_b: Second sensitive attribute values.
        attr_a_name: Name of first attribute.
        attr_b_name: Name of second attribute.

    Returns:
        List of DemographicSlice objects for each cross-product group.
    """
    cross_attr = f"{attr_a_name}×{attr_b_name}"
    cross_groups = np.array([
        f"{a}_{b}" for a, b in zip(sensitive_a, sensitive_b)
    ])

    return build_demographic_slices(y_true, y_pred, cross_groups, cross_attr)
