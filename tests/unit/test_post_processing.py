"""
Unit tests for Post-Processing algorithms.

Tests fairness constraint enforcement using ThresholdOptimizer.
"""

import pytest
import numpy as np
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "mitigation"))


@pytest.fixture
def biased_dataset():
    from sklearn.datasets import make_classification
    np.random.seed(42)
    X, y = make_classification(n_samples=500, n_features=5, random_state=42)
    sensitive = np.where(y == 1, np.random.choice([0, 1], p=[0.2, 0.8], size=500),
                                 np.random.choice([0, 1], p=[0.8, 0.2], size=500))
    return X, y, sensitive


def test_threshold_optimizer_demographic_parity(biased_dataset):
    from sklearn.linear_model import LogisticRegression
    from algorithms.post_processing import apply_threshold_optimizer

    X, y, sensitive = biased_dataset
    estimator = LogisticRegression(random_state=42)
    
    mitigator = apply_threshold_optimizer(
        estimator=estimator,
        X=X,
        y=y,
        sensitive_features=sensitive,
        constraint="demographic_parity",
        prefit=False
    )
    
    assert mitigator is not None
    assert hasattr(mitigator, "predict")
    
    preds = mitigator.predict(X, sensitive_features=sensitive)
    assert preds.shape == y.shape


def test_threshold_optimizer_prefit(biased_dataset):
    from sklearn.linear_model import LogisticRegression
    from algorithms.post_processing import apply_threshold_optimizer

    X, y, sensitive = biased_dataset
    estimator = LogisticRegression(random_state=42)
    estimator.fit(X, y) # Prefit intentionally
    
    mitigator = apply_threshold_optimizer(
        estimator=estimator,
        X=X,
        y=y,
        sensitive_features=sensitive,
        constraint="equalized_odds",
        prefit=True
    )
    
    assert mitigator is not None
    assert hasattr(mitigator, "predict")
