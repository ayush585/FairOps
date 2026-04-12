# FairOps

> **Real-Time ML Bias Monitoring & Mitigation Pipeline**
> Google Solution Challenge 2026 | Track: Unbiased AI Decision
> Team: Toro Bees | Stack: GCP-native | Vertex AI | Gemini Pro | Python 3.11

---

## What is FairOps?

FairOps is a **production-grade** bias monitoring and automated mitigation platform for deployed machine learning models. It provides:

- **Real-time bias detection** across 12 fairness metrics
- **Automated mitigation** via Vertex AI Pipelines (AIF360 algorithms)
- **Explainable AI** narratives powered by Gemini Pro + SHAP
- **Immutable audit ledger** on Cloud Spanner for regulatory compliance
- **Regulatory reporting** (EU AI Act, EEOC 4/5ths Rule, GDPR Article 22)

### 3-Line Integration

```python
from fairops_sdk import FairOpsClient

client = FairOpsClient("my-project", "hiring-model", "v1", use_case="hiring")
client.log_prediction(features={"age": 35, "sex": "Male"}, prediction={"label": "approved", "score": 0.87, "threshold": 0.5})
```

---

## Architecture

```
Deployed ML Model
      |
      v  (FairOps SDK — 3 lines of integration code)
Cloud Pub/Sub [fairops-predictions-ingest]
      |
      v
Cloud Dataflow [Stream Processor — Apache Beam]
      |  schema validation + demographic enrichment + PII redaction (Cloud DLP)
      v
BigQuery [fairops_raw.predictions + fairops_enriched.demographics]
      |
      v  (Cloud Scheduler — every 15 min)
Cloud Run [fairops-auditor]
      |  computes 12 fairness metrics + severity classification
      v
BigQuery [fairops_metrics.bias_audits]
      |
      |--- severity = CRITICAL/HIGH -----> Vertex AI Pipelines [10-step mitigation DAG]
      |                                         |
      v                                    Vertex AI Model Registry
Cloud Run [fairops-explainer]
      |  SHAP + Gemini Pro narrative
      v
Cloud Spanner [immutable audit ledger]
      |
      v
Looker Studio Dashboard [real-time fairness monitoring]
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud SDK (`gcloud`)
- Terraform >= 1.5.0
- Docker (for local service development)

### 1. Clone & Configure

```bash
cp .env.example .env
# Edit .env with your GCP project ID
```

### 2. Deploy Infrastructure

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your project ID

terraform init
terraform plan
terraform apply
```

### 3. Install SDK

```bash
cd sdk
pip install -e ".[dev]"
```

### 4. Run Tests

```bash
pytest sdk/tests/ -v
pytest tests/unit/ -v
```

### 5. Run Gateway Locally

```bash
cd services/gateway
pip install -r requirements.txt
uvicorn main:app --reload --port 8080
```

---

## The 12 Fairness Metrics

| # | Metric | Threshold | Breach |
|---|--------|-----------|--------|
| 1 | Demographic Parity Difference | 0.10 | > |
| 2 | Equalized Odds Difference | 0.08 | > |
| 3 | Equal Opportunity Difference | 0.05 | > |
| 4 | Disparate Impact Ratio | 0.80 | < |
| 5 | Average Odds Difference | 0.07 | > |
| 6 | Statistical Parity Subgroup Lift | 1.25 | > |
| 7 | Predictive Parity Difference | 0.08 | > |
| 8 | Calibration Gap | 0.05 | > |
| 9 | Individual Fairness Score | 0.85 | < |
| 10 | Counterfactual Fairness | 0.06 | > |
| 11 | Intersectional Bias Score | 0.12 | > |
| 12 | Temporal Drift Index | 5.0 | > |

---

## GCP Cost Optimization Tips (Student Free Tier)

- **BigQuery**: 10GB storage free, 1TB query free/month
- **Pub/Sub**: 10GB free/month
- **Cloud Run**: 2M requests free/month, 360k vCPU-seconds free
- **Cloud Spanner**: Consider using Firestore in dev ($0 for free tier) and Spanner in prod
- **Apply for Google Cloud for Education credits**: $300 free trial for new accounts
- **Solution Challenge teams** may receive additional GCP credits

---

## License

Apache 2.0

---

*FairOps | Google Solution Challenge 2026 | Real GCP stack. No shortcuts.*
