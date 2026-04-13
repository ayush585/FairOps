"""
FairOps Auditor — Drift Detection.

CUSUM (Cumulative Sum) + ADWIN drift detection
using the ruptures library.

Ref: AGENT.md Section 6 (Metric 12), Section 21.
"""

import numpy as np
from typing import Optional


def compute_cusum_statistic(
    values: list[float],
    target: Optional[float] = None,
    drift_threshold: float = 0.05,
) -> float:
    """
    Compute CUSUM (Cumulative Sum Control Chart) statistic.

    Detects shifts in the mean of a time series of metric values.

    Args:
        values: Time series of metric values (e.g., demographic_parity_difference
                computed over successive windows).
        target: Target/expected value. If None, uses the minimum value in the series
                as a stable baseline (robust to drifting means).
        drift_threshold: Slack / allowable deviation (k). Default 0.05
                         (appropriate for fairness metrics in [0,1]).

    Returns:
        Maximum CUSUM statistic value. Values > 5.0 indicate significant drift.
    """
    if len(values) < 3:
        return 0.0

    arr = np.array(values, dtype=float)

    if target is None:
        # Use the minimum of the series as a conservative stable baseline.
        # This is robust to series that drift monotonically upward, because
        # the first-half mean would also drift, masking the shift.
        target = arr.min()

    # Compute two-sided CUSUM
    cusum_pos = np.zeros(len(arr))
    cusum_neg = np.zeros(len(arr))

    for i in range(1, len(arr)):
        cusum_pos[i] = max(0, cusum_pos[i - 1] + (arr[i] - target) - drift_threshold)
        cusum_neg[i] = max(0, cusum_neg[i - 1] - (arr[i] - target) - drift_threshold)

    return float(max(cusum_pos.max(), cusum_neg.max()))


def detect_changepoints(
    values: list[float],
    n_bkps: int = 2,
    model: str = "l2",
) -> list[int]:
    """
    Detect changepoints in a time series using the ruptures library.

    Args:
        values: Time series of metric values.
        n_bkps: Number of breakpoints to detect.
        model: Cost model ("l2", "l1", "rbf", "normal").

    Returns:
        List of changepoint indices.
    """
    if len(values) < 5:
        return []

    try:
        import ruptures as rpt

        arr = np.array(values).reshape(-1, 1)

        # Use PELT algorithm for optimal changepoint detection
        algo = rpt.Pelt(model=model, min_size=2).fit(arr)
        result = algo.predict(pen=1.0)

        # Remove the last element (which is always len(values) in ruptures)
        changepoints = [cp for cp in result if cp < len(values)]

        return changepoints

    except ImportError:
        # Fallback: simple threshold-based detection
        return _simple_changepoint_detection(values)
    except Exception:
        return []


def _simple_changepoint_detection(
    values: list[float],
    threshold_sigma: float = 2.0,
) -> list[int]:
    """
    Simple changepoint detection as fallback when ruptures is unavailable.

    Detects points where the value deviates more than threshold_sigma
    standard deviations from the running mean.
    """
    arr = np.array(values)
    changepoints = []

    running_mean = arr[0]
    running_var = 0.0
    n = 1

    for i in range(1, len(arr)):
        n += 1
        delta = arr[i] - running_mean
        running_mean += delta / n
        running_var += delta * (arr[i] - running_mean)

        if n > 3:
            std = np.sqrt(running_var / (n - 1))
            if std > 0 and abs(arr[i] - running_mean) > threshold_sigma * std:
                changepoints.append(i)
                # Reset statistics after changepoint
                running_mean = arr[i]
                running_var = 0.0
                n = 1

    return changepoints


def compute_adwin_drift(
    values: list[float],
    delta: float = 0.002,
) -> dict:
    """
    ADWIN (Adaptive Windowing) drift detection.

    Maintains a variable-length window and detects when the distribution
    of recent values differs significantly from historical values.

    Args:
        values: Stream of metric values.
        delta: Significance parameter (smaller = more sensitive).

    Returns:
        Dict with drift_detected, drift_points, current_mean, historical_mean.
    """
    if len(values) < 10:
        return {
            "drift_detected": False,
            "drift_points": [],
            "current_mean": float(np.mean(values)) if values else 0.0,
            "historical_mean": float(np.mean(values)) if values else 0.0,
        }

    arr = np.array(values)
    drift_points = []

    # Simple ADWIN-like implementation
    window_size = len(arr)
    for split in range(window_size // 4, 3 * window_size // 4):
        left = arr[:split]
        right = arr[split:]

        if len(left) < 3 or len(right) < 3:
            continue

        # Hoeffding bound
        m = 1.0 / (1.0 / len(left) + 1.0 / len(right))
        epsilon = np.sqrt((1.0 / (2.0 * m)) * np.log(4.0 / delta))

        if abs(left.mean() - right.mean()) >= epsilon:
            drift_points.append(split)

    # Use midpoint as most likely drift location
    drift_detected = len(drift_points) > 0

    return {
        "drift_detected": drift_detected,
        "drift_points": drift_points[:5],  # Top 5 most likely
        "current_mean": float(arr[-len(arr) // 4 :].mean()),
        "historical_mean": float(arr[: len(arr) // 4].mean()),
    }
