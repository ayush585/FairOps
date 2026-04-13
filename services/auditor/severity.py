"""
FairOps Auditor — Severity Classification.

Classifies overall audit severity and determines action.

Ref: AGENT.md Section 7:
  CRITICAL → DI < 0.65 OR any metric > 3x threshold OR 3+ breached → trigger pipeline
  HIGH     → DI in [0.65, 0.80) OR any in (2x, 3x) OR 2 breached → queue 1hr delay
  MEDIUM   → 1 breached < 2x, p_value < 0.05 → log + dashboard
  LOW      → breached but p_value > 0.05 → audit trail only
  PASS     → no breached → log clean result
"""

import logging

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
from fairops_sdk.schemas import FairnessMetric, Severity

from metrics.fairness import THRESHOLDS, BREACH_GREATER

logger = logging.getLogger("fairops.auditor.severity")


def classify_overall_severity(
    metrics: dict[str, FairnessMetric],
) -> Severity:
    """
    Classify the overall severity of a bias audit based on all metrics.

    Args:
        metrics: Dict of metric_name -> FairnessMetric from the audit.

    Returns:
        Overall Severity classification.
    """
    breached_metrics = {
        name: m for name, m in metrics.items() if m.breached
    }
    n_breached = len(breached_metrics)

    if n_breached == 0:
        return Severity.PASS

    # ── CRITICAL checks ──────────────────────────────────────────────────

    # Check: disparate_impact_ratio < 0.65
    di = metrics.get("disparate_impact_ratio")
    if di and di.value < 0.65:
        logger.warning(
            f"CRITICAL: disparate_impact_ratio = {di.value:.4f} (< 0.65)"
        )
        return Severity.CRITICAL

    # Check: any metric > 3x threshold
    for name, m in breached_metrics.items():
        threshold = THRESHOLDS.get(name, 0)
        if threshold > 0:
            if BREACH_GREATER.get(name, True):
                ratio = m.value / threshold
            else:
                ratio = threshold / max(m.value, 1e-10)

            if ratio > 3:
                logger.warning(
                    f"CRITICAL: {name} = {m.value:.4f} is >{3}x threshold {threshold}"
                )
                return Severity.CRITICAL

    # Check: 3+ metrics breached simultaneously
    if n_breached >= 3:
        logger.warning(
            f"CRITICAL: {n_breached} metrics breached simultaneously: "
            f"{list(breached_metrics.keys())}"
        )
        return Severity.CRITICAL

    # ── HIGH checks ──────────────────────────────────────────────────────

    # Check: disparate_impact_ratio in [0.65, 0.80)
    if di and 0.65 <= di.value < 0.80:
        logger.warning(
            f"HIGH: disparate_impact_ratio = {di.value:.4f} in [0.65, 0.80)"
        )
        return Severity.HIGH

    # Check: any metric in (2x, 3x) threshold
    for name, m in breached_metrics.items():
        threshold = THRESHOLDS.get(name, 0)
        if threshold > 0:
            if BREACH_GREATER.get(name, True):
                ratio = m.value / threshold
            else:
                ratio = threshold / max(m.value, 1e-10)

            if 2 < ratio <= 3:
                logger.warning(
                    f"HIGH: {name} = {m.value:.4f} is {ratio:.1f}x threshold"
                )
                return Severity.HIGH

    # Check: exactly 2 metrics breached
    if n_breached == 2:
        logger.warning(
            f"HIGH: 2 metrics breached: {list(breached_metrics.keys())}"
        )
        return Severity.HIGH

    # ── MEDIUM check ─────────────────────────────────────────────────────

    # Exactly 1 breached, < 2x threshold, p_value < 0.05
    if n_breached == 1:
        m = list(breached_metrics.values())[0]
        if m.p_value < 0.05:
            return Severity.MEDIUM

    # ── LOW ──────────────────────────────────────────────────────────────

    # Breached but p_value > 0.05 (statistical noise)
    all_noisy = all(m.p_value > 0.05 for m in breached_metrics.values())
    if all_noisy:
        return Severity.LOW

    return Severity.MEDIUM


def get_required_action(severity: Severity) -> dict:
    """
    Get the required action for a given severity level.

    Returns:
        Dict with action description and parameters.
    """
    actions = {
        Severity.CRITICAL: {
            "action": "TRIGGER_PIPELINE",
            "description": "Immediately trigger Vertex AI Pipeline (synchronous call)",
            "delay_seconds": 0,
            "notify": True,
            "log_to_bq": True,
            "log_to_spanner": True,
        },
        Severity.HIGH: {
            "action": "QUEUE_PIPELINE",
            "description": "Push to Cloud Tasks queue with 1-hour delay",
            "delay_seconds": 3600,
            "notify": True,
            "log_to_bq": True,
            "log_to_spanner": True,
        },
        Severity.MEDIUM: {
            "action": "LOG_AND_HIGHLIGHT",
            "description": "Log to BQ + dashboard highlight + include in next retrain",
            "delay_seconds": None,
            "notify": False,
            "log_to_bq": True,
            "log_to_spanner": True,
        },
        Severity.LOW: {
            "action": "LOG_ONLY",
            "description": "Log to audit trail only — statistical noise",
            "delay_seconds": None,
            "notify": False,
            "log_to_bq": False,
            "log_to_spanner": True,
        },
        Severity.PASS: {
            "action": "LOG_CLEAN",
            "description": "Log clean audit result to BQ",
            "delay_seconds": None,
            "notify": False,
            "log_to_bq": True,
            "log_to_spanner": True,
        },
    }
    return actions.get(severity, actions[Severity.PASS])
