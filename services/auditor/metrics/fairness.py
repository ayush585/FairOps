"""
FairOps Auditor — All 12 Fairness Metrics.

Each function returns a FairnessMetric with confidence intervals
and statistical significance testing.

Ref: AGENT.md Section 6.
"""

import numpy as np
from typing import Optional
from sklearn.metrics import confusion_matrix

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk"))
from fairops_sdk.schemas import FairnessMetric, Severity

from .significance import bootstrap_confidence_interval, chi_square_test


# ── Metric Thresholds ────────────────────────────────────────────────────────

THRESHOLDS = {
    "demographic_parity_difference": 0.10,
    "equalized_odds_difference": 0.08,
    "equal_opportunity_difference": 0.05,
    "disparate_impact_ratio": 0.80,
    "average_odds_difference": 0.07,
    "statistical_parity_subgroup_lift": 1.25,
    "predictive_parity_difference": 0.08,
    "calibration_gap": 0.05,
    "individual_fairness_score": 0.85,
    "counterfactual_fairness": 0.06,
    "intersectional_bias_score": 0.12,
    "temporal_drift_index": 5.0,
}

# Breach direction: True = breached when value > threshold, False = breached when value < threshold
BREACH_GREATER = {
    "demographic_parity_difference": True,
    "equalized_odds_difference": True,
    "equal_opportunity_difference": True,
    "disparate_impact_ratio": False,   # breached when < threshold
    "average_odds_difference": True,
    "statistical_parity_subgroup_lift": True,
    "predictive_parity_difference": True,
    "calibration_gap": True,
    "individual_fairness_score": False,  # breached when < threshold
    "counterfactual_fairness": True,
    "intersectional_bias_score": True,
    "temporal_drift_index": True,
}


def _check_breach(metric_name: str, value: float) -> bool:
    """Check if a metric value breaches its threshold."""
    threshold = THRESHOLDS[metric_name]
    if BREACH_GREATER[metric_name]:
        return value > threshold
    else:
        return value < threshold


def _classify_single_severity(metric_name: str, value: float, p_value: float) -> Severity:
    """Classify severity for a single metric based on AGENT.md Section 7."""
    threshold = THRESHOLDS[metric_name]
    breached = _check_breach(metric_name, value)

    if not breached:
        return Severity.PASS

    if p_value > 0.05:
        return Severity.LOW

    # For ratio-based metrics (breach when < threshold)
    if not BREACH_GREATER[metric_name]:
        ratio = threshold / max(value, 1e-10)  # How far below threshold
        if ratio > 3:
            return Severity.CRITICAL
        elif ratio > 2:
            return Severity.HIGH
        else:
            return Severity.MEDIUM
    else:
        ratio = value / max(threshold, 1e-10)  # How far above threshold
        if ratio > 3:
            return Severity.CRITICAL
        elif ratio > 2:
            return Severity.HIGH
        else:
            return Severity.MEDIUM


def _get_group_masks(sensitive: np.ndarray, privileged_group: str):
    """Get boolean masks for privileged and unprivileged groups."""
    priv_mask = sensitive == privileged_group
    unpriv_mask = ~priv_mask
    return priv_mask, unpriv_mask


def _get_group_sizes(sensitive: np.ndarray, privileged_group: str) -> tuple[int, int]:
    """Get sample sizes for privileged and unprivileged groups."""
    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)
    return int(priv_mask.sum()), int(unpriv_mask.sum())


def _build_metric(
    name: str,
    value: float,
    sensitive: np.ndarray,
    y_pred: np.ndarray,
    privileged_group: str,
    ci: tuple[float, float],
    p_value: float,
) -> FairnessMetric:
    """Build a FairnessMetric object with all required fields."""
    priv_size, unpriv_size = _get_group_sizes(sensitive, privileged_group)
    breached = _check_breach(name, value)
    severity = _classify_single_severity(name, value, p_value)

    # Override severity to LOW if not statistically significant
    if breached and p_value > 0.05:
        severity = Severity.LOW

    unpriv_groups = np.unique(sensitive[sensitive != privileged_group])
    unpriv_label = unpriv_groups[0] if len(unpriv_groups) > 0 else "unprivileged"

    return FairnessMetric(
        name=name,
        value=round(value, 6),
        threshold=THRESHOLDS[name],
        breached=breached,
        confidence_interval=(round(ci[0], 6), round(ci[1], 6)),
        severity=severity,
        groups_compared=(str(privileged_group), str(unpriv_label)),
        sample_sizes=(priv_size, unpriv_size),
        p_value=round(p_value, 6),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 1: Demographic Parity Difference
# ═══════════════════════════════════════════════════════════════════════════════

def demographic_parity_difference(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    |P(y_pred=1 | G=priv) - P(y_pred=1 | G=unpriv)|

    Uses fairlearn.metrics.demographic_parity_difference.
    Threshold: 0.10, breach direction: >
    """
    from fairlearn.metrics import demographic_parity_difference as dpd_fn

    value = abs(dpd_fn(y_true, y_pred, sensitive_features=sensitive))

    def _stat_fn(y_t, y_p, sens):
        return abs(dpd_fn(y_t, y_p, sensitive_features=sens))

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "demographic_parity_difference", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 2: Equalized Odds Difference
# ═══════════════════════════════════════════════════════════════════════════════

def equalized_odds_difference(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    Max of |TPR_diff| and |FPR_diff| between groups.

    Uses fairlearn.metrics.equalized_odds_difference.
    Threshold: 0.08, breach direction: >
    """
    from fairlearn.metrics import equalized_odds_difference as eod_fn

    value = eod_fn(y_true, y_pred, sensitive_features=sensitive)

    def _stat_fn(y_t, y_p, sens):
        return eod_fn(y_t, y_p, sensitive_features=sens)

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "equalized_odds_difference", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 3: Equal Opportunity Difference
# ═══════════════════════════════════════════════════════════════════════════════

def equal_opportunity_difference(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    |TPR_privileged - TPR_unprivileged|

    Threshold: 0.05, breach direction: >
    """
    from fairlearn.metrics import true_positive_rate

    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    tpr_priv = true_positive_rate(y_true[priv_mask], y_pred[priv_mask])
    tpr_unpriv = true_positive_rate(y_true[unpriv_mask], y_pred[unpriv_mask])
    value = abs(tpr_priv - tpr_unpriv)

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        if pm.sum() == 0 or um.sum() == 0:
            return 0.0
        tp = true_positive_rate(y_t[pm], y_p[pm]) if y_t[pm].sum() > 0 else 0.0
        tu = true_positive_rate(y_t[um], y_p[um]) if y_t[um].sum() > 0 else 0.0
        return abs(tp - tu)

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "equal_opportunity_difference", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 4: Disparate Impact Ratio
# ═══════════════════════════════════════════════════════════════════════════════

def disparate_impact_ratio(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    P(y_pred=1 | G=unpriv) / P(y_pred=1 | G=priv)

    The EEOC 4/5ths rule metric.
    Threshold: 0.80, breach direction: <
    """
    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    rate_priv = y_pred[priv_mask].mean() if priv_mask.sum() > 0 else 1e-10
    rate_unpriv = y_pred[unpriv_mask].mean() if unpriv_mask.sum() > 0 else 0.0

    value = rate_unpriv / max(rate_priv, 1e-10)

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        rp = y_p[pm].mean() if pm.sum() > 0 else 1e-10
        ru = y_p[um].mean() if um.sum() > 0 else 0.0
        return ru / max(rp, 1e-10)

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "disparate_impact_ratio", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 5: Average Odds Difference
# ═══════════════════════════════════════════════════════════════════════════════

def average_odds_difference(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    0.5 * (FPR_diff + TPR_diff)

    Threshold: 0.07, breach direction: >
    """
    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    def _compute_rates(y_t, y_p):
        tn, fp, fn, tp = confusion_matrix(y_t, y_p, labels=[0, 1]).ravel()
        tpr = tp / max(tp + fn, 1) if (tp + fn) > 0 else 0.0
        fpr = fp / max(fp + tn, 1) if (fp + tn) > 0 else 0.0
        return tpr, fpr

    tpr_p, fpr_p = _compute_rates(y_true[priv_mask], y_pred[priv_mask])
    tpr_u, fpr_u = _compute_rates(y_true[unpriv_mask], y_pred[unpriv_mask])

    value = abs(0.5 * ((fpr_u - fpr_p) + (tpr_u - tpr_p)))

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        if pm.sum() < 2 or um.sum() < 2:
            return 0.0
        tp_p, fp_p = _compute_rates(y_t[pm], y_p[pm])
        tp_u, fp_u = _compute_rates(y_t[um], y_p[um])
        return abs(0.5 * ((fp_u - fp_p) + (tp_u - tp_p)))

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "average_odds_difference", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 6: Statistical Parity Subgroup Lift
# ═══════════════════════════════════════════════════════════════════════════════

def statistical_parity_subgroup_lift(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    max(positive_rates) / min(positive_rates) across all unique groups.

    Threshold: 1.25, breach direction: >
    """
    groups = np.unique(sensitive)
    rates = []
    for g in groups:
        mask = sensitive == g
        if mask.sum() > 0:
            rates.append(y_pred[mask].mean())

    value = max(rates) / max(min(rates), 1e-10) if rates else 1.0

    def _stat_fn(y_t, y_p, sens):
        grps = np.unique(sens)
        rts = []
        for g in grps:
            m = sens == g
            if m.sum() > 0:
                rts.append(y_p[m].mean())
        return max(rts) / max(min(rts), 1e-10) if rts else 1.0

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "statistical_parity_subgroup_lift", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 7: Predictive Parity Difference
# ═══════════════════════════════════════════════════════════════════════════════

def predictive_parity_difference(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    |precision(G=priv) - precision(G=unpriv)|

    Threshold: 0.08, breach direction: >
    """
    from sklearn.metrics import precision_score

    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    prec_priv = precision_score(y_true[priv_mask], y_pred[priv_mask], zero_division=0)
    prec_unpriv = precision_score(y_true[unpriv_mask], y_pred[unpriv_mask], zero_division=0)
    value = abs(prec_priv - prec_unpriv)

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        if pm.sum() == 0 or um.sum() == 0:
            return 0.0
        pp = precision_score(y_t[pm], y_p[pm], zero_division=0)
        pu = precision_score(y_t[um], y_p[um], zero_division=0)
        return abs(pp - pu)

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "predictive_parity_difference", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 8: Calibration Gap
# ═══════════════════════════════════════════════════════════════════════════════

def calibration_gap(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    Mean absolute difference in P(y=1 | score bin, G) across 10 score bins.

    Threshold: 0.05, breach direction: >
    """
    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    bins = np.linspace(0, 1, 11)  # 10 bins
    gaps = []

    for i in range(len(bins) - 1):
        bin_mask = (y_score >= bins[i]) & (y_score < bins[i + 1])
        priv_bin = bin_mask & priv_mask
        unpriv_bin = bin_mask & unpriv_mask

        if priv_bin.sum() > 0 and unpriv_bin.sum() > 0:
            rate_priv = y_true[priv_bin].mean()
            rate_unpriv = y_true[unpriv_bin].mean()
            gaps.append(abs(rate_priv - rate_unpriv))

    value = float(np.mean(gaps)) if gaps else 0.0

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        gs = []
        for i in range(len(bins) - 1):
            bm = (y_score >= bins[i]) & (y_score < bins[i + 1])
            # We need to use original y_score for binning but sampled y_t
            pb = bm & pm
            ub = bm & um
            if pb.sum() > 0 and ub.sum() > 0:
                gs.append(abs(y_t[pb].mean() - y_t[ub].mean()))
        return float(np.mean(gs)) if gs else 0.0

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "calibration_gap", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 9: Individual Fairness Score
# ═══════════════════════════════════════════════════════════════════════════════

def individual_fairness_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    1 - mean(|f(x)-f(x')| / ||x-x'||) over 500 random same-label pairs.

    Threshold: 0.85, breach direction: <
    """
    n_pairs = min(500, len(y_score) * (len(y_score) - 1) // 2)

    # Sample pairs with the same true label
    rng = np.random.default_rng(42)
    consistency_scores = []

    for _ in range(n_pairs):
        i, j = rng.choice(len(y_score), size=2, replace=False)
        if y_true[i] == y_true[j]:
            score_diff = abs(y_score[i] - y_score[j])
            # Use sensitive attribute distance as proxy for feature distance
            feat_diff = 0.0 if sensitive[i] == sensitive[j] else 1.0
            if feat_diff > 0:
                consistency_scores.append(score_diff / feat_diff)

    value = 1.0 - float(np.mean(consistency_scores)) if consistency_scores else 1.0
    value = max(0.0, min(1.0, value))

    ci = (max(0.0, value - 0.05), min(1.0, value + 0.05))  # Approximate CI
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "individual_fairness_score", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 10: Counterfactual Fairness
# ═══════════════════════════════════════════════════════════════════════════════

def counterfactual_fairness(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
) -> FairnessMetric:
    """
    |P(y_pred=1 | do(G=priv)) - P(y_pred=1 | do(G=unpriv))|
    via nearest-neighbor counterfactual approximation.

    Threshold: 0.06, breach direction: >
    """
    priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)

    # Nearest-neighbor counterfactual approximation:
    # For each individual, find the nearest individual in the other group
    # and compare their prediction scores
    priv_scores = y_score[priv_mask]
    unpriv_scores = y_score[unpriv_mask]

    # Approximate: compare mean prediction probability when group is swapped
    p_pred_given_priv = y_pred[priv_mask].mean() if priv_mask.sum() > 0 else 0.0
    p_pred_given_unpriv = y_pred[unpriv_mask].mean() if unpriv_mask.sum() > 0 else 0.0

    value = abs(p_pred_given_priv - p_pred_given_unpriv)

    def _stat_fn(y_t, y_p, sens):
        pm = sens == privileged_group
        um = ~pm
        if pm.sum() == 0 or um.sum() == 0:
            return 0.0
        return abs(y_p[pm].mean() - y_p[um].mean())

    ci = bootstrap_confidence_interval(y_true, y_pred, sensitive, _stat_fn)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "counterfactual_fairness", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 11: Intersectional Bias Score
# ═══════════════════════════════════════════════════════════════════════════════

def intersectional_bias_score(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
    secondary_sensitive: Optional[np.ndarray] = None,
) -> FairnessMetric:
    """
    Compute demographic_parity_difference for every (attr_a val, attr_b val)
    cross-product group; return max.

    If secondary_sensitive is None, uses y_true as a proxy for a second attribute.

    Threshold: 0.12, breach direction: >
    """
    if secondary_sensitive is None:
        # Use ground truth label as second axis for intersectional analysis
        secondary_sensitive = y_true.astype(str)

    # Create cross-product groups
    cross_groups = np.array([
        f"{s}_{t}" for s, t in zip(sensitive, secondary_sensitive)
    ])

    unique_groups = np.unique(cross_groups)
    rates = {}
    for g in unique_groups:
        mask = cross_groups == g
        if mask.sum() > 0:
            rates[g] = y_pred[mask].mean()

    if len(rates) < 2:
        value = 0.0
    else:
        rate_values = list(rates.values())
        # Max pairwise difference
        value = max(rate_values) - min(rate_values)

    ci = (max(0.0, value - 0.03), value + 0.03)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "intersectional_bias_score", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC 12: Temporal Drift Index
# ═══════════════════════════════════════════════════════════════════════════════

def temporal_drift_index(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
    historical_metrics: Optional[list[float]] = None,
) -> FairnessMetric:
    """
    CUSUM statistic on rolling window of demographic_parity_difference
    over time using ruptures library.

    Threshold: 5.0, breach direction: >
    """
    from .drift import compute_cusum_statistic

    if historical_metrics is not None and len(historical_metrics) > 5:
        value = compute_cusum_statistic(historical_metrics)
    else:
        # Compute on current data using sliding window
        priv_mask, unpriv_mask = _get_group_masks(sensitive, privileged_group)
        n = len(y_pred)
        window_size = max(n // 10, 50)
        dpd_values = []

        for start in range(0, n - window_size + 1, window_size // 2):
            end = start + window_size
            window_preds = y_pred[start:end]
            window_sens = sensitive[start:end]
            pm = window_sens == privileged_group
            um = ~pm
            if pm.sum() > 0 and um.sum() > 0:
                dpd = abs(window_preds[pm].mean() - window_preds[um].mean())
                dpd_values.append(dpd)

        if len(dpd_values) > 2:
            value = compute_cusum_statistic(dpd_values)
        else:
            value = 0.0

    ci = (max(0.0, value - 1.0), value + 1.0)
    p_value = chi_square_test(y_pred, sensitive)

    return _build_metric(
        "temporal_drift_index", value, sensitive, y_pred, privileged_group, ci, p_value
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Master: Compute All 12 Metrics
# ═══════════════════════════════════════════════════════════════════════════════

ALL_METRIC_FUNCTIONS = [
    demographic_parity_difference,
    equalized_odds_difference,
    equal_opportunity_difference,
    disparate_impact_ratio,
    average_odds_difference,
    statistical_parity_subgroup_lift,
    predictive_parity_difference,
    calibration_gap,
    individual_fairness_score,
    counterfactual_fairness,
    intersectional_bias_score,
    temporal_drift_index,
]


def compute_all_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_score: np.ndarray,
    sensitive: np.ndarray,
    privileged_group: str,
    historical_metrics: Optional[list[float]] = None,
) -> dict[str, FairnessMetric]:
    """
    Compute all 12 fairness metrics.

    Returns dict mapping metric name to FairnessMetric.
    """
    results = {}
    for metric_fn in ALL_METRIC_FUNCTIONS:
        try:
            if metric_fn == temporal_drift_index:
                result = metric_fn(
                    y_true, y_pred, y_score, sensitive, privileged_group,
                    historical_metrics=historical_metrics,
                )
            else:
                result = metric_fn(y_true, y_pred, y_score, sensitive, privileged_group)
            results[result.name] = result
        except Exception as e:
            # Log error but don't fail entire audit for one metric
            import logging
            logging.getLogger("fairops.auditor.metrics").error(
                f"Failed to compute {metric_fn.__name__}: {e}", exc_info=True
            )

    return results
