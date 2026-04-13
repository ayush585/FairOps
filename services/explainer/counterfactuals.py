"""
FairOps Explainer — DiCE Counterfactual Generation.

Generates counterfactual examples showing what would need to change
for the model to produce a different prediction.

Uses the DiCE (Diverse Counterfactual Explanations) library.

Ref: AGENT.md Sprint 3, Section 21 (dice-ml==0.11).
"""

import logging
import numpy as np
import pandas as pd
from typing import Optional

logger = logging.getLogger("fairops.explainer.counterfactuals")


def generate_counterfactuals(
    model,
    X_instance: pd.DataFrame,
    feature_names: list[str],
    outcome_name: str = "prediction",
    continuous_features: Optional[list[str]] = None,
    n_counterfactuals: int = 5,
    desired_class: int = 1,
    proximity_weight: float = 0.5,
    diversity_weight: float = 1.0,
) -> dict:
    """
    Generate diverse counterfactual explanations for a prediction.

    Args:
        model: Sklearn-compatible model.
        X_instance: Single row DataFrame to explain.
        feature_names: All feature column names.
        outcome_name: Name of the target column.
        continuous_features: List of continuous feature names.
                             If None, inferred from dtype.
        n_counterfactuals: Number of diverse counterfactuals to generate.
        desired_class: Target class for counterfactuals (default 1 = positive).
        proximity_weight: Weight for proximity (smaller changes preferred).
        diversity_weight: Weight for diversity (varied explanations preferred).

    Returns:
        Dict with counterfactuals list and summary.
    """
    try:
        import dice_ml
        from dice_ml import Dice

        # Infer continuous features if not provided
        if continuous_features is None:
            continuous_features = [
                col for col in X_instance.columns
                if X_instance[col].dtype in [np.float32, np.float64, float]
            ]

        # Build DiCE data model
        dice_data = dice_ml.Data(
            dataframe=_build_background_df(X_instance, feature_names, outcome_name, model),
            continuous_features=continuous_features,
            outcome_name=outcome_name,
        )

        # Wrap model for DiCE
        dice_model = dice_ml.Model(model=model, backend="sklearn")

        # Initialize DiCE with genetic algorithm (faster than RANDOM for structured data)
        exp = Dice(dice_data, dice_model, method="genetic")

        # Generate counterfactuals
        cf_result = exp.generate_counterfactuals(
            X_instance,
            total_CFs=n_counterfactuals,
            desired_class=desired_class,
            proximity_weight=proximity_weight,
            diversity_weight=diversity_weight,
            verbose=False,
        )

        # Parse results
        cf_df = cf_result.cf_examples_list[0].final_cfs_df
        if cf_df is None or len(cf_df) == 0:
            return _empty_counterfactual_result(X_instance, feature_names)

        counterfactuals = []
        original = X_instance.iloc[0].to_dict()

        for _, row in cf_df.iterrows():
            changes = {}
            for feat in feature_names:
                if feat in row and feat in original:
                    orig_val = original[feat]
                    cf_val = row[feat]
                    if orig_val != cf_val:
                        changes[feat] = {
                            "from": _safe_round(orig_val),
                            "to": _safe_round(cf_val),
                            "delta": _safe_round(cf_val - orig_val)
                            if isinstance(cf_val, (int, float)) else None,
                        }

            counterfactuals.append({
                "changes": changes,
                "n_changes": len(changes),
                "predicted_outcome": int(row.get(outcome_name, desired_class)),
            })

        # Sort by fewest changes (closest to original)
        counterfactuals.sort(key=lambda x: x["n_changes"])

        # Identify most common feature changes (recurring themes)
        all_changed_features = [
            feat for cf in counterfactuals for feat in cf["changes"]
        ]
        feature_change_freq = {}
        for feat in all_changed_features:
            feature_change_freq[feat] = feature_change_freq.get(feat, 0) + 1

        most_impactful = sorted(
            feature_change_freq.items(), key=lambda x: x[1], reverse=True
        )[:3]

        return {
            "counterfactuals": counterfactuals,
            "n_generated": len(counterfactuals),
            "most_impactful_features": [f for f, _ in most_impactful],
            "min_changes_required": counterfactuals[0]["n_changes"] if counterfactuals else 0,
            "original_instance": {k: _safe_round(v) for k, v in original.items()},
        }

    except ImportError:
        logger.warning("dice-ml not installed — returning simplified counterfactuals")
        return _simplified_counterfactuals(model, X_instance, feature_names, desired_class)
    except Exception as e:
        logger.error(f"Counterfactual generation failed: {e}", exc_info=True)
        return _empty_counterfactual_result(X_instance, feature_names)


def _build_background_df(
    X_instance: pd.DataFrame,
    feature_names: list[str],
    outcome_name: str,
    model,
) -> pd.DataFrame:
    """Build background DataFrame for DiCE data model."""
    # Generate synthetic background data by perturbing the instance
    n_background = 50
    rng = np.random.default_rng(42)

    rows = []
    for _ in range(n_background):
        row = X_instance.iloc[0].copy()
        for col in X_instance.select_dtypes(include=[np.number]).columns:
            row[col] = row[col] * rng.uniform(0.5, 1.5)
        rows.append(row)

    df = pd.DataFrame(rows)
    df[outcome_name] = model.predict(df[feature_names])
    return df


def _simplified_counterfactuals(
    model,
    X_instance: pd.DataFrame,
    feature_names: list[str],
    desired_class: int,
) -> dict:
    """
    Simplified counterfactual generation without DiCE.

    Perturbs each numerical feature by ±10%, ±20%, ±30%
    and checks if the prediction changes.
    """
    original_pred = model.predict(X_instance)[0]
    original = X_instance.iloc[0].to_dict()
    counterfactuals = []

    numeric_features = [
        f for f in feature_names
        if isinstance(original.get(f), (int, float))
    ]

    for feat in numeric_features:
        for delta_pct in [0.1, 0.2, 0.3, -0.1, -0.2, -0.3]:
            perturbed = X_instance.copy()
            perturbed[feat] = perturbed[feat] * (1 + delta_pct)

            try:
                new_pred = model.predict(perturbed)[0]
                if new_pred == desired_class and original_pred != desired_class:
                    change_val = float(perturbed[feat].iloc[0])
                    counterfactuals.append({
                        "changes": {feat: {
                            "from": _safe_round(original[feat]),
                            "to": _safe_round(change_val),
                            "delta": _safe_round(change_val - original[feat]),
                        }},
                        "n_changes": 1,
                        "predicted_outcome": int(desired_class),
                    })
            except Exception:
                continue

        if len(counterfactuals) >= 5:
            break

    return {
        "counterfactuals": counterfactuals[:5],
        "n_generated": len(counterfactuals[:5]),
        "most_impactful_features": list({
            list(cf["changes"].keys())[0] for cf in counterfactuals[:3]
        }),
        "min_changes_required": 1 if counterfactuals else 0,
        "original_instance": {k: _safe_round(v) for k, v in original.items()},
        "method": "simplified_perturbation",
    }


def _empty_counterfactual_result(X_instance: pd.DataFrame, feature_names: list[str]) -> dict:
    return {
        "counterfactuals": [],
        "n_generated": 0,
        "most_impactful_features": [],
        "min_changes_required": None,
        "original_instance": X_instance.iloc[0].to_dict() if len(X_instance) > 0 else {},
    }


def _safe_round(value, decimals: int = 4):
    """Safely round a value for JSON serialization."""
    if isinstance(value, (int, float, np.floating, np.integer)):
        return round(float(value), decimals)
    return value
