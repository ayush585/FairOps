"""
FairOps Mitigation Engine — Rollback and Degradation Analyzer.

Automated guardrail module that analyzes performance drops
in accuracy after a mitigation process. If a model sacrifices
too much accuracy (e.g. >15% drop) to achieve fairness, it is
flagged.

Ref: AGENT.md Sprint 4.
"""

import logging

logger = logging.getLogger("fairops.mitigation.rollback")


def evaluate_mitigation_degradation(
    accuracy_before: float,
    accuracy_after: float,
    metrics_before: dict[str, float],
    metrics_after: dict[str, float],
    max_accuracy_drop: float = 0.15,
) -> dict:
    """
    Evaluates whether a mitigated model should proceed to production,
    or be rolled back due to severe accuracy degradation.

    Args:
        accuracy_before: General performance accuracy before mitigation.
        accuracy_after: General performance accuracy after mitigation.
        metrics_before: Raw dictionary of fairness metric results strings before.
        metrics_after: Raw dictionary of fairness metric results strings after.
        max_accuracy_drop: Maximum acceptable drop in accuracy (absolute value).
                           A 15% drop corresponds to 0.15.

    Returns:
        Dict indicating rollback status and reasoning.
    """
    if accuracy_after < 0 or accuracy_before < 0:
        raise ValueError("Accuracy metrics cannot be negative.")

    accuracy_delta = accuracy_after - accuracy_before
    severe_degradation = accuracy_delta < (-abs(max_accuracy_drop))

    # Evaluate if any fairness metric successfully improved
    fairness_improved = False
    
    # Minimal simplistic fairness check (in real production this checks threshold bounds strictly)
    if "disparate_impact_ratio" in metrics_before and "disparate_impact_ratio" in metrics_after:
        # DIR improvement means it moved closer to 1.0
        dist_before = abs(1.0 - metrics_before["disparate_impact_ratio"])
        dist_after = abs(1.0 - metrics_after["disparate_impact_ratio"])
        if dist_after < dist_before:
            fairness_improved = True
            
    if "demographic_parity_difference" in metrics_before and "demographic_parity_difference" in metrics_after:
        # DPD improvement means it moved closer to 0.0
        if metrics_after["demographic_parity_difference"] < metrics_before["demographic_parity_difference"]:
            fairness_improved = True

    roll_back = False
    reason = "Mitigation evaluated successfully."

    if severe_degradation:
        roll_back = True
        reason = (
            f"Mitigation resulted in an unacceptable accuracy drop of "
            f"{abs(accuracy_delta) * 100:.2f}%. Maximum allowed drop is "
            f"{abs(max_accuracy_drop) * 100:.2f}%."
        )
    elif not fairness_improved and (metrics_before and metrics_after):
        roll_back = True
        reason = "Mitigation failed to improve primary fairness parameters across groups."

    logger.info(f"Rollback evaluation: roll_back={roll_back}, reason={reason}")

    return {
        "roll_back": roll_back,
        "reason": reason,
        "accuracy_delta": accuracy_delta,
        "severe_degradation": severe_degradation,
        "fairness_improved": fairness_improved,
    }
