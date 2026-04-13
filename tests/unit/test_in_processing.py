"""
Unit tests for In-Processing algorithms.

Tests fairness constraint enforcement using ExponentiatedGradient.
"""

import pytest
import numpy as np
import pandas as pd
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "mitigation"))


@pytest.fixture
def biased_dataset():
    """Create a synthetically biased dataset."""
    from sklearn.datasets import make_classification

    np.random.seed(42)
    X, y = make_classification(n_samples=500, n_features=5, random_state=42)
    
    # Intentionally skew sensitive attribute based on label to create bias
    sensitive = np.where(y == 1, np.random.choice([0, 1], p=[0.2, 0.8], size=500),
                                 np.random.choice([0, 1], p=[0.8, 0.2], size=500))
    return X, y, sensitive


def test_exponentiated_gradient_fit_demographic_parity(biased_dataset):
    from sklearn.linear_model import LogisticRegression
    from algorithms.in_processing import apply_exponentiated_gradient

    X, y, sensitive = biased_dataset
    estimator = LogisticRegression(random_state=42)
    
    mitigator = apply_exponentiated_gradient(
        estimator=estimator,
        X=X,
        y=y,
        sensitive_features=sensitive,
        constraint="demographic_parity",
        eps=0.05,
        max_iter=5
    )
    
    assert mitigator is not None
    # Verify predict method exists which indicates a fitted ExponentiatedGradient
    assert hasattr(mitigator, "predict")
    
    preds = mitigator.predict(X)
    assert preds.shape == y.shape


def test_exponentiated_gradient_fit_equalized_odds(biased_dataset):
    from sklearn.linear_model import LogisticRegression
    from algorithms.in_processing import apply_exponentiated_gradient

    X, y, sensitive = biased_dataset
    estimator = LogisticRegression(random_state=42)
    
    mitigator = apply_exponentiated_gradient(
        estimator=estimator,
        X=X,
        y=y,
        sensitive_features=sensitive,
        constraint="equalized_odds",
        eps=0.05,
        max_iter=5
    )
    
    assert mitigator is not None
    assert hasattr(mitigator, "predict")
