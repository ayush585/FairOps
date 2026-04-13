"""
End-to-End Simulation Test.

Simulates writing prediction events, aggregating them into audits,
evaluating metrics, firing telemetry, checking mitigations, and 
calling the Explainer.

Ref: AGENT.md Sprint 5.
"""

import pytest
import numpy as np
import pandas as pd
import datetime
from fastapi.testclient import TestClient

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Since this is an E2E test spanning multiple domains, we mock the network layers (BigQuery, Spanner) 
# to ensure it can pass in isolated GitHub Actions runners, but we load the exact real algorithms 
# and FastAPI endpoints.


class MockBigQueryClient:
    def insert_rows_json(self, table, json_rows):
        return [] # Success, no errors
        

@pytest.fixture
def mock_bq(monkeypatch):
    monkeypatch.setattr("services.shared.bigquery.get_bq_client", lambda: MockBigQueryClient())


def test_full_fairops_pipeline(mock_bq, monkeypatch):
    """
    Simulates the entire pipeline:
    SDK -> Auditor Engine -> Explainer/Slack Notifier -> Mitigation Evaluation
    """
    # ── 1. Create Biased Dataset (Simulating SDK Ingestion) ──
    from sklearn.datasets import make_classification
    X, y = make_classification(n_samples=1000, n_features=5, random_state=42)
    # Strong Bias:
    sensitive = np.where(y == 1, np.random.choice([0, 1], p=[0.05, 0.95], size=1000),
                                 np.random.choice([0, 1], p=[0.95, 0.05], size=1000))
                                 
    from sklearn.linear_model import LogisticRegression
    clf = LogisticRegression()
    clf.fit(X, y)
    y_pred = clf.predict(X)
    y_score = clf.predict_proba(X)[:, 1]

    # Add auditor to sys.path so its internal relative imports resolve correctly (e.g. `import metrics.fairness`)
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "auditor"))

    # ── 2. Run Auditor Engine ──
    from audit_runner import run_audit
    
    # Mock data fetching to return our biased data
    monkeypatch.setattr(
        "audit_runner._fetch_prediction_data", 
        lambda m, ws, we: pd.DataFrame({"ground_truth": y, "prediction_label": y_pred, "prediction_score": y_score, "sensitive_attr": sensitive})
    )
    # Mock Spanner writing
    monkeypatch.setattr("audit_runner._persist_results", lambda a, act, r: None)

    # We do NOT mock telemetry here -> let it hit the exception handlers if no real services are running
    # but the pipeline shouldn't crash.
    result = run_audit(
        model_id="e2e-biased-model",
        window_hours=1,
        protected_attributes=["sensitive_attr"],
    )
    
    # The bias was severe, so it must trigger CRITICAL.
    assert result.overall_severity.value == "CRITICAL"
    assert "demographic_parity_difference" in result.metrics
    assert result.metrics["demographic_parity_difference"].breached == True

    # ── 3. Run Explainer service manually ──
    # Checking if SHAP triggers accurately over this result
    from services.explainer.shap_explainer import SHAPExplainer
    explainer = SHAPExplainer(clf, X[:50], ["f1", "f2", "f3", "f4", "sensitive_attr"], model_type="tree")
    shap_results = explainer.explain(X[:20], sensitive_feature="sensitive_attr")
    assert "top_bias_drivers" in shap_results

    # ── 4. Notifier Trigger Verification ──
    # We test the FastAPI Notifier route locally using TestClient
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "notifier"))
    from main import app as notifier_app
    notifier_client = TestClient(notifier_app)
    
    notify_response = notifier_client.post(
        "/notify",
        json={
            "audit_id": result.audit_id,
            "model_id": "e2e-biased-model",
            "severity": "CRITICAL",
            "top_metric_name": "demographic_parity_difference",
            "top_metric_value": result.metrics["demographic_parity_difference"].value,
            "threshold": result.metrics["demographic_parity_difference"].threshold,
        }
    )
    assert notify_response.status_code == 200
    assert notify_response.json()["status"] == "success"

    # ── 5. Mitigation Verification ──
    from services.mitigation.rollback import evaluate_mitigation_degradation
    # Testing that if we successfully mitigate, no rollback is required
    eval_result = evaluate_mitigation_degradation(
        accuracy_before=0.88,
        accuracy_after=0.85, # Only 3% drop
        metrics_before={"disparate_impact_ratio": 0.20}, # Bad
        metrics_after={"disparate_impact_ratio": 0.90},  # Fixed
        max_accuracy_drop=0.15
    )
    assert eval_result["roll_back"] == False

    print("\n[E2E] Pipeline completed end-to-end flawlessly.")
