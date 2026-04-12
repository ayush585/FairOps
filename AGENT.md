# AGENT.md — FairOps
> Production build instructions for AI coding agents
> Project: FairOps — Real-Time ML Bias Monitoring & Mitigation Pipeline
> Hackathon: Google Solution Challenge 2026 | Track: Unbiased AI Decision
> Team: Toro Bees
> Stack: GCP-native | Vertex AI | Gemini Pro | Python 3.11

---

## 0. Agent Operating Rules

1. **Read this entire file before writing a single line of code.**
2. **Work strictly sprint by sprint.** Each sprint has a Definition of Done (DoD). Do not start Sprint N+1 until Sprint N's DoD passes — all listed tests pass and the described behavior is manually verifiable.
3. **No mocks, no stubs, no demo shortcuts.** This is a real production system. Every GCP service call is real. Every API is real.
4. **When in doubt, check the schema.** All data contracts are in Section 5. If a service produces or consumes data not matching those schemas, it is wrong.
5. **Fail loudly.** No silent exception swallowing. Every service must log errors with full stack traces to Cloud Logging. Unhandled exceptions should crash the service, not hide the bug.
6. **Write tests as you go.** Every function in `auditor/metrics/` and `sdk/` must have a unit test written in the same sprint as the function.
7. **Infrastructure is code.** Every GCP resource must exist in Terraform. Never create resources manually in the console.

---

## 1. System Architecture — Full Data Flow

```
Deployed ML Model
      |
      v  (FairOps SDK — 3 lines of integration code)
Cloud Pub/Sub [fairops-predictions-ingest]
      |
      v
Cloud Dataflow [FairOps Stream Processor — Apache Beam]
      |  schema validation + demographic enrichment + PII redaction (Cloud DLP)
      v
BigQuery [fairops_raw.predictions  +  fairops_enriched.demographics]
      |
      v  (Cloud Scheduler — every 15 min per model)
Cloud Run [fairops-auditor]
      |  computes 12 fairness metrics + severity classification
      v
BigQuery [fairops_metrics.bias_audits]
      |
      |--- severity = CRITICAL/HIGH ----------------------------->
      |                                                           |
      v                                                    Vertex AI Pipelines
Cloud Run [fairops-explainer]                          [10-step mitigation DAG]
      |  SHAP + Gemini Pro narrative                             |
      v                                                    Vertex AI Model Registry
Cloud Spanner [fairops-audit-ledger]  <---- immutable audit trail from all services
      |
      v
Looker Studio [real-time fairness dashboard via BigQuery BI Engine]
```

Every component in this diagram must be implemented and deployed. No placeholders.

---

## 2. GCP Project Bootstrap

### Enable APIs
```bash
gcloud services enable \
  pubsub.googleapis.com \
  dataflow.googleapis.com \
  bigquery.googleapis.com \
  bigquerystorage.googleapis.com \
  aiplatform.googleapis.com \
  run.googleapis.com \
  spanner.googleapis.com \
  cloudbuild.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  dlp.googleapis.com \
  monitoring.googleapis.com \
  logging.googleapis.com \
  cloudkms.googleapis.com \
  artifactregistry.googleapis.com \
  iamcredentials.googleapis.com \
  cloudtasks.googleapis.com
```

### Service Accounts

| SA Name | Bindings | Used By |
|---------|----------|---------|
| `fairops-stream-processor` | BigQuery Data Editor, Pub/Sub Subscriber, DLP User | Dataflow |
| `fairops-auditor` | BigQuery Data Editor, Spanner Database User, Cloud Run Invoker | Auditor |
| `fairops-explainer` | BigQuery Data Viewer, Vertex AI User, Secret Manager Accessor | Explainer |
| `fairops-mitigator` | Vertex AI Pipelines Runner, BigQuery Data Editor, Storage Admin | Mitigation Pipeline |
| `fairops-gateway` | Cloud Run Invoker (all services), Secret Manager Accessor | API Gateway |
| `fairops-notifier` | Secret Manager Accessor | Notifier |

All inter-service authentication uses **Workload Identity Federation**. Zero service account key files. Zero `GOOGLE_APPLICATION_CREDENTIALS` JSON in production.

---

## 3. Repository Structure

```
fairops/
├── CLAUDE.md
├── README.md
├── .env.example
├── .gitignore
├── cloudbuild.yaml
│
├── infra/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── terraform.tfvars.example
│   └── modules/
│       ├── pubsub/          # topic + subscription + dead-letter
│       ├── bigquery/        # all datasets + tables
│       ├── cloudrun/        # all 6 services
│       ├── spanner/         # instance + database + DDL
│       ├── vertex/          # pipeline root bucket + metadata store
│       ├── scheduler/       # cron audit triggers
│       ├── monitoring/      # custom metrics + alert policies
│       └── iam/             # all service accounts + bindings
│
├── sdk/
│   ├── fairops_sdk/
│   │   ├── __init__.py
│   │   ├── client.py        # main SDK entry point
│   │   ├── publisher.py     # Pub/Sub prediction log publisher
│   │   └── schemas.py       # all Pydantic schemas
│   ├── pyproject.toml
│   └── tests/
│       └── test_schemas.py
│
├── services/
│   ├── shared/
│   │   ├── logging.py       # structured Cloud Logging
│   │   ├── tracing.py       # OpenTelemetry
│   │   ├── auth.py          # JWT validation + Workload Identity helpers
│   │   ├── bigquery.py      # shared BQ client factory
│   │   ├── spanner.py       # shared Spanner client factory
│   │   └── errors.py        # custom exception hierarchy
│   │
│   ├── gateway/
│   │   ├── main.py
│   │   ├── routers/
│   │   │   ├── audits.py
│   │   │   ├── models.py
│   │   │   ├── predictions.py
│   │   │   ├── compliance.py
│   │   │   └── metrics.py       # Prometheus scrape endpoint
│   │   ├── middleware/
│   │   │   ├── auth.py
│   │   │   ├── rate_limit.py
│   │   │   └── request_id.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── auditor/
│   │   ├── main.py
│   │   ├── audit_runner.py
│   │   ├── metrics/
│   │   │   ├── fairness.py       # all 12 metrics
│   │   │   ├── significance.py   # bootstrap CI + chi-square
│   │   │   └── drift.py          # CUSUM + ADWIN
│   │   ├── severity.py
│   │   ├── slicing.py            # demographic slice construction
│   │   ├── bq_writer.py
│   │   ├── spanner_writer.py
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── explainer/
│   │   ├── main.py
│   │   ├── shap_service.py
│   │   ├── gemini_service.py
│   │   ├── counterfactual.py     # DiCE counterfactuals
│   │   ├── pdf_generator.py      # reportlab PDF export
│   │   ├── prompts/
│   │   │   ├── bias_narrative.txt
│   │   │   └── compliance_report.txt
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   │
│   ├── stream_processor/
│   │   ├── pipeline.py           # Apache Beam entry point
│   │   ├── transforms/
│   │   │   ├── schema_validator.py
│   │   │   ├── demographic_enricher.py
│   │   │   ├── pii_redactor.py       # Cloud DLP integration
│   │   │   └── dead_letter_handler.py
│   │   ├── dataflow_runner.py
│   │   └── requirements.txt
│   │
│   └── notifier/
│       ├── main.py
│       ├── channels/
│       │   ├── slack.py
│       │   ├── email.py
│       │   └── pagerduty.py
│       ├── Dockerfile
│       └── requirements.txt
│
├── pipelines/
│   ├── mitigation_pipeline.py    # full 10-step KFP v2 DAG
│   ├── compile_pipeline.py       # compile + upload to GCS
│   ├── components/
│   │   ├── data_prep.py
│   │   ├── preprocessing_mitigation.py
│   │   ├── inprocessing_mitigation.py
│   │   ├── postprocessing_mitigation.py
│   │   ├── model_retrain.py
│   │   ├── fairness_evaluation.py
│   │   ├── accuracy_gate.py
│   │   ├── pareto_optimization.py
│   │   ├── ab_validation.py
│   │   ├── model_promotion.py
│   │   └── audit_record.py
│   └── requirements.txt
│
├── omniml/
│   ├── __init__.py
│   ├── model.py                  # OmniMLModel base class
│   ├── registry.py
│   ├── frameworks/
│   │   ├── sklearn_adapter.py
│   │   ├── pytorch_adapter.py
│   │   ├── xgboost_adapter.py
│   │   └── tensorflow_adapter.py
│   └── vertex_bridge.py
│
├── dbt/
│   ├── dbt_project.yml
│   └── models/
│       ├── staging/
│       │   ├── stg_predictions.sql
│       │   └── stg_audits.sql
│       └── marts/
│           ├── fairness_dashboard.sql
│           └── compliance_summary.sql
│
└── tests/
    ├── unit/
    │   ├── test_metrics.py
    │   ├── test_severity.py
    │   ├── test_schemas.py
    │   ├── test_slicing.py
    │   └── test_drift.py
    ├── integration/
    │   ├── test_audit_pipeline.py
    │   ├── test_mitigation_pipeline.py
    │   └── test_api_gateway.py
    ├── load/
    │   └── locustfile.py
    └── conftest.py
```

---

## 4. Environment Variables

```bash
# GCP Core
GCP_PROJECT_ID=fairops-prod
GCP_REGION=us-central1

# Pub/Sub
PUBSUB_TOPIC_ID=fairops-predictions-ingest
PUBSUB_SUBSCRIPTION_ID=fairops-predictions-sub
PUBSUB_DEAD_LETTER_TOPIC_ID=fairops-predictions-dlq

# BigQuery
BQ_DATASET_RAW=fairops_raw
BQ_DATASET_ENRICHED=fairops_enriched
BQ_DATASET_METRICS=fairops_metrics

# Cloud Spanner
SPANNER_INSTANCE_ID=fairops-audit
SPANNER_DATABASE_ID=fairops-ledger

# Vertex AI
VERTEX_PIPELINE_ROOT=gs://fairops-pipelines-${GCP_PROJECT_ID}/
VERTEX_LOCATION=us-central1
VERTEX_PIPELINE_SA=fairops-mitigator@${GCP_PROJECT_ID}.iam.gserviceaccount.com

# Gemini (key fetched from Secret Manager at runtime — never hardcoded)
GEMINI_MODEL=gemini-pro

# JWT (secret fetched from Secret Manager at runtime)
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=60

# Redis (Memorystore internal VPC IP)
REDIS_HOST=10.x.x.x
REDIS_PORT=6379

# Service URLs (Cloud Run sets these; override for local dev)
AUDITOR_URL=https://fairops-auditor-xxx.run.app
EXPLAINER_URL=https://fairops-explainer-xxx.run.app
NOTIFIER_URL=https://fairops-notifier-xxx.run.app

# Audit scheduling
AUDIT_SCHEDULE_CRON=*/15 * * * *
AUDIT_WINDOW_HOURS=1
AUDIT_MIN_SAMPLE_SIZE=100
```

**Secrets stored in Secret Manager only** (never in env or code):
- `fairops/jwt-secret`
- `fairops/gemini-api-key`
- `fairops/slack-webhook-url`

---

## 5. Core Data Schemas

All in `sdk/fairops_sdk/schemas.py`. Use Pydantic v2. Import from here in every service — never redefine.

```python
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Any
from datetime import datetime
from enum import Enum
from uuid import uuid4


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    PASS = "PASS"

class UseCase(str, Enum):
    HIRING = "hiring"
    LENDING = "lending"
    HEALTHCARE = "healthcare"
    CRIMINAL_JUSTICE = "criminal_justice"
    CONTENT_RECOMMENDATION = "content_recommendation"

class MitigationStage(str, Enum):
    PRE_PROCESSING = "pre-processing"
    IN_PROCESSING = "in-processing"
    POST_PROCESSING = "post-processing"
    RETRAINING = "retraining"

class MitigationStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class PredictionResult(BaseModel):
    label: str
    score: float = Field(ge=0.0, le=1.0)
    threshold: float = Field(ge=0.0, le=1.0)

class SessionContext(BaseModel):
    tenant_id: str
    use_case: UseCase

class PredictionEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_version: str
    timestamp: datetime
    features: dict[str, Any]
    prediction: PredictionResult
    ground_truth: Optional[str] = None
    demographic_tags: list[str] = Field(default_factory=list)
    session_context: SessionContext

    @field_validator("model_id")
    @classmethod
    def model_id_no_spaces(cls, v: str) -> str:
        if " " in v:
            raise ValueError("model_id must not contain spaces")
        return v


class FairnessMetric(BaseModel):
    name: str
    value: float
    threshold: float
    breached: bool
    confidence_interval: tuple[float, float]
    severity: Severity
    groups_compared: tuple[str, str]
    sample_sizes: tuple[int, int]
    p_value: float

class DemographicSlice(BaseModel):
    attribute: str
    group_value: str
    count: int
    positive_rate: float
    metrics: dict[str, float]

class BiasAuditResult(BaseModel):
    audit_id: str = Field(default_factory=lambda: str(uuid4()))
    model_id: str
    model_version: str
    audit_timestamp: datetime = Field(default_factory=datetime.utcnow)
    window_start: datetime
    window_end: datetime
    sample_size: int
    metrics: dict[str, FairnessMetric]
    overall_severity: Severity
    protected_attributes: list[str]
    demographic_slices: list[DemographicSlice]
    triggered_mitigation: bool = False
    mitigation_id: Optional[str] = None


class MitigationRecord(BaseModel):
    mitigation_id: str = Field(default_factory=lambda: str(uuid4()))
    audit_id: str
    model_id: str
    model_version_before: str
    model_version_after: Optional[str] = None
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    algorithm_used: str
    stage: MitigationStage
    metrics_before: dict[str, float]
    metrics_after: Optional[dict[str, float]] = None
    accuracy_before: float
    accuracy_after: Optional[float] = None
    accuracy_delta: Optional[float] = None
    status: MitigationStatus = MitigationStatus.QUEUED
    promoted_to_production: bool = False
    vertex_pipeline_run_id: Optional[str] = None
    error_message: Optional[str] = None


class ApiResponse(BaseModel):
    status: str = "success"
    data: Optional[Any] = None
    error: Optional[dict] = None
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

---

## 6. The 12 Fairness Metrics

Implement in `services/auditor/metrics/fairness.py`.

Each function signature:
```python
def metric_name(
    y_true: np.ndarray,       # ground truth 0/1
    y_pred: np.ndarray,       # model predictions 0/1
    y_score: np.ndarray,      # probabilities
    sensitive: np.ndarray,    # string array of group values
    privileged_group: str     # which value is "privileged"
) -> FairnessMetric
```

| # | Metric | Implementation | Threshold | Breach direction |
|---|--------|---------------|-----------|-----------------|
| 1 | `demographic_parity_difference` | `fairlearn.metrics.demographic_parity_difference` | 0.10 | > |
| 2 | `equalized_odds_difference` | `fairlearn.metrics.equalized_odds_difference` | 0.08 | > |
| 3 | `equal_opportunity_difference` | `|TPR_privileged - TPR_unprivileged|` using `fairlearn.metrics.true_positive_rate` | 0.05 | > |
| 4 | `disparate_impact_ratio` | `P(y_pred=1 | G=unpriv) / P(y_pred=1 | G=priv)` | 0.80 | < |
| 5 | `average_odds_difference` | `0.5 * (FPR_diff + TPR_diff)` | 0.07 | > |
| 6 | `statistical_parity_subgroup_lift` | `max(positive_rates) / min(positive_rates)` across all unique groups | 1.25 | > |
| 7 | `predictive_parity_difference` | `|precision(G=priv) - precision(G=unpriv)|` | 0.08 | > |
| 8 | `calibration_gap` | Mean absolute difference in P(y=1 | score bin, G) across 10 score bins | 0.05 | > |
| 9 | `individual_fairness_score` | `1 - mean(|f(x)-f(x')| / ||x-x'||)` over 500 random same-label pairs | 0.85 | < |
| 10 | `counterfactual_fairness` | `|P(y_pred=1 | do(G=priv)) - P(y_pred=1 | do(G=unpriv))|` via nearest-neighbor counterfactual approximation | 0.06 | > |
| 11 | `intersectional_bias_score` | Compute demographic_parity_difference for every (attr_a val, attr_b val) cross-product group; return max | 0.12 | > |
| 12 | `temporal_drift_index` | CUSUM statistic on rolling window of metric 1 over time using `ruptures` library | 5.0 | > |

**Confidence intervals:** `scipy.stats.bootstrap` with n_resamples=1000, confidence_level=0.95. Attach `confidence_interval` tuple to every metric.

**Statistical significance:** Chi-square test (`scipy.stats.chi2_contingency`) on contingency table of (sensitive_attr × prediction_label). If `p_value > 0.05`, override `severity = LOW` regardless of metric value — not enough evidence to call it real bias.

---

## 7. Severity Classification

In `services/auditor/severity.py`:

```
CRITICAL  → disparate_impact_ratio < 0.65
            OR any metric value > 3x its threshold
            OR 3+ metrics breached simultaneously
            Action: immediately trigger Vertex AI Pipeline (synchronous call)

HIGH      → disparate_impact_ratio in [0.65, 0.80)
            OR any metric value in (2x, 3x) threshold
            OR exactly 2 metrics breached
            Action: push to Cloud Tasks queue with 1-hour delay

MEDIUM    → exactly 1 metric breached, value < 2x threshold, p_value < 0.05
            Action: log to BQ + dashboard highlight + include in next retrain

LOW       → metric appears breached but p_value > 0.05 (statistical noise)
            Action: log to audit trail only

PASS      → no metrics breached
            Action: log clean audit result to BQ
```

---

## 8. Demographic Enrichment

In `services/stream_processor/transforms/demographic_enricher.py`.

**When direct labels are present in features:**
Map raw values to standardized demographic tags via lookup dictionaries.
```python
GENDER_MAP = {"M": "MALE", "F": "FEMALE", "male": "MALE", "female": "FEMALE", "0": "MALE", "1": "FEMALE"}
AGE_BINS = [(0,18,"AGE_UNDER_18"), (18,30,"AGE_18_30"), (30,40,"AGE_30_40"),
            (40,50,"AGE_40_50"), (50,60,"AGE_50_60"), (60,999,"AGE_60_PLUS")]
```

**When direct labels are absent (proxy mode):**
1. Gender: `gender_guesser` library on first name field. Store as probability dict — `{"MALE": 0.82, "FEMALE": 0.18}` — never as a hard label.
2. Race: `surgeo` library (BISG — Bayesian Improved Surname Geocoding) on surname + ZIP code. Output is a probability distribution.
3. Income: ACS 2022 PUMS median household income by ZIP code bracket.

All proxies must:
- Be stored as probability distributions, never hard labels
- Have a `proxy_quality_score: float` attached
- Set `is_proxy: true` in the enriched record

**PII Redaction:** Every record passes through Cloud DLP before writing to BigQuery. Detect: emails, phone numbers, SSNs, full names. Action: tokenize (consistent token per value, not delete — cohort fairness analysis still needs to work).

---

## 9. Mitigation Pipeline — Full 10-Step Vertex AI KFP v2 DAG

Define in `pipelines/mitigation_pipeline.py`. Each step is a `@component` decorated function. Use KFP v2 artifact types (`Input[Dataset]`, `Output[Model]`, etc.) — not raw GCS path strings.

### Algorithm Selection
```python
def select_algorithm(audit: BiasAuditResult) -> dict:
    m = audit.metrics
    if m["demographic_parity_difference"].breached and m["disparate_impact_ratio"].breached:
        return {"algorithm": "Reweighing", "stage": "pre-processing", "fallback": "LFR"}
    if m["disparate_impact_ratio"].value < 0.65:
        return {"algorithm": "DisparateImpactRemover", "stage": "pre-processing", "fallback": "Reweighing"}
    if m["equalized_odds_difference"].breached:
        return {"algorithm": "AdversarialDebiasing", "stage": "in-processing", "fallback": "PrejudiceRemover"}
    if m["calibration_gap"].breached:
        return {"algorithm": "CalibratedEqOddsPostprocessing", "stage": "post-processing", "fallback": "RejectOptionClassification"}
    if m["temporal_drift_index"].breached:
        return {"algorithm": "FullRetrain", "stage": "retraining", "fallback": "SlidingWindowRetrain"}
    if m["intersectional_bias_score"].breached:
        return {"algorithm": "MultiGroupReweighing", "stage": "pre-processing", "fallback": "AdversarialDebiasing"}
```

### Pipeline Steps

**Step 1 — trigger_validation**
Fetch audit result from BigQuery. Validate it is < 2 hours old (reject stale triggers). Output: `validated_audit_json`, `algorithm_config`.

**Step 2 — data_preparation**
Pull training data from `fairops_raw.predictions` for the model's training window. Compute sample weights if Reweighing is selected. Output: Parquet file to GCS.

**Step 3 — preprocessing_mitigation** *(skip if stage != pre-processing)*
Apply AIF360 algorithm:
- Reweighing: `aif360.algorithms.preprocessing.Reweighing`
- DIR: `aif360.algorithms.preprocessing.DisparateImpactRemover`
- LFR: `aif360.algorithms.preprocessing.LFR`

Input MUST be converted to `BinaryLabelDataset` via `OmniMLModel.to_aif360_dataset()` before calling any AIF360 algorithm.

**Step 4 — model_retrain**
Retrain using same architecture as original model. Add fairness regularization term `λ=0.1` to loss. Save retrained model to GCS via OmniML. Output: `retrained_model_gcs_path`, `train_accuracy`.

**Step 5 — fairness_evaluation**
Run full 12-metric audit on held-out validation set. Compare all metrics vs pre-mitigation baseline. Output: `post_mitigation_metrics_json`, `fairness_improvement_pct`.

**Step 6 — accuracy_gate**
If `accuracy_delta > 2%`, fail → branch to Step 7. If `accuracy_delta <= 2%`, proceed to Step 8.

**Step 7 — pareto_optimization** *(only if Step 6 fails)*
NSGA-II multi-objective optimization using `pymoo`:
- Objective 1: minimize sum of fairness metric violations
- Objective 2: maximize model accuracy
- Search space: regularization `λ ∈ [0.01, 1.0]`, decision threshold `∈ [0.3, 0.7]`
- Budget: 50 evaluations
- Output: pareto-optimal hyperparams + retrained model

**Step 8 — ab_validation**
Shadow deploy to Vertex AI Endpoint at 10% traffic. Collect predictions for 24 hours. Compare fairness + accuracy vs current production model. Output: `ab_result (pass/fail)`.

**Step 9 — model_promotion** *(only if Step 8 passes)*
Upload to Vertex AI Model Registry with tag `fairops-mitigated-{timestamp}`. Update OmniML registry. Swap Vertex AI Endpoint to 100% new model. Write `MODEL_PROMOTED` event to Cloud Spanner.

**Step 10 — audit_record**
Write complete `MitigationRecord` to Cloud Spanner (immutable, INSERT only). Write summary to `fairops_metrics.mitigation_log`. Trigger notifier service. Output: `mitigation_record_id`.

---

## 10. BigQuery DDL

```sql
-- fairops_raw.predictions
CREATE TABLE fairops_raw.predictions (
    event_id            STRING NOT NULL,
    model_id            STRING NOT NULL,
    model_version       STRING NOT NULL,
    timestamp           TIMESTAMP NOT NULL,
    features            JSON,
    prediction_label    STRING,
    prediction_score    FLOAT64,
    prediction_threshold FLOAT64,
    ground_truth        STRING,
    demographic_tags    ARRAY<STRING>,
    tenant_id           STRING,
    use_case            STRING,
    ingested_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(timestamp)
CLUSTER BY model_id, prediction_label;

-- fairops_enriched.demographics
CREATE TABLE fairops_enriched.demographics (
    event_id              STRING NOT NULL,
    model_id              STRING NOT NULL,
    timestamp             TIMESTAMP NOT NULL,
    gender_distribution   JSON,
    race_distribution     JSON,
    age_bin               STRING,
    income_bracket        STRING,
    proxy_quality_score   FLOAT64,
    is_proxy              BOOL,
    zip_code              STRING,
    enriched_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(timestamp)
CLUSTER BY model_id;

-- fairops_metrics.bias_audits
CREATE TABLE fairops_metrics.bias_audits (
    audit_id             STRING NOT NULL,
    model_id             STRING NOT NULL,
    model_version        STRING,
    audit_timestamp      TIMESTAMP NOT NULL,
    window_start         TIMESTAMP,
    window_end           TIMESTAMP,
    sample_size          INT64,
    overall_severity     STRING,
    metrics              JSON,
    demographic_slices   JSON,
    protected_attributes ARRAY<STRING>,
    triggered_mitigation BOOL,
    mitigation_id        STRING,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(audit_timestamp)
CLUSTER BY model_id, overall_severity;

-- fairops_metrics.mitigation_log
CREATE TABLE fairops_metrics.mitigation_log (
    mitigation_id          STRING NOT NULL,
    audit_id               STRING NOT NULL,
    model_id               STRING NOT NULL,
    model_version_before   STRING,
    model_version_after    STRING,
    triggered_at           TIMESTAMP NOT NULL,
    algorithm_used         STRING,
    stage                  STRING,
    metrics_before         JSON,
    metrics_after          JSON,
    accuracy_before        FLOAT64,
    accuracy_after         FLOAT64,
    accuracy_delta         FLOAT64,
    status                 STRING,
    promoted_to_production BOOL,
    vertex_pipeline_run_id STRING,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(triggered_at)
CLUSTER BY model_id, status;

-- fairops_metrics.fairness_timeseries
CREATE TABLE fairops_metrics.fairness_timeseries (
    model_id     STRING NOT NULL,
    metric_name  STRING NOT NULL,
    metric_value FLOAT64,
    severity     STRING,
    recorded_at  TIMESTAMP NOT NULL
)
PARTITION BY DATE(recorded_at)
CLUSTER BY model_id, metric_name;
```

---

## 11. Cloud Spanner DDL

```sql
CREATE TABLE AuditEvents (
    EventId        STRING(36)  NOT NULL,
    EventType      STRING(50)  NOT NULL,
    ModelId        STRING(100) NOT NULL,
    TenantId       STRING(100) NOT NULL,
    EventTimestamp TIMESTAMP   NOT NULL,
    Payload        JSON        NOT NULL,
    ActorServiceId STRING(100),
    IpAddress      STRING(50),
) PRIMARY KEY (EventId);

CREATE INDEX AuditEventsByModel  ON AuditEvents (ModelId,  EventTimestamp DESC);
CREATE INDEX AuditEventsByTenant ON AuditEvents (TenantId, EventTimestamp DESC);
```

**INSERT ONLY policy.** Zero `UPDATE` or `DELETE` ever issued against this table. Enforce via IAM: grant only `spanner.databases.write` without DML mutation permissions.

Valid `EventType` values: `AUDIT_COMPLETED`, `MITIGATION_TRIGGERED`, `MITIGATION_COMPLETED`, `MODEL_PROMOTED`, `BIAS_ALERT_SENT`.

---

## 12. API — Full Endpoint Spec

All responses use `ApiResponse` envelope from Section 5.

```
POST   /v1/predictions/ingest
  Body:        PredictionEvent | list[PredictionEvent] (max 500)
  Action:      Publish to Pub/Sub
  Returns:     { "event_ids": [...], "queued": N }
  Auth:        API Key (X-Api-Key header)
  Rate limit:  10,000 req/min

POST   /v1/models/{model_id}/audit
  Body:        { "window_hours": int = 1, "protected_attributes": list[str] }
  Action:      Pull BQ data → run 12 metrics → write results → if CRITICAL/HIGH trigger pipeline
  Returns:     BiasAuditResult
  Auth:        Bearer JWT
  SLA:         < 30s for up to 100k predictions

GET    /v1/audits/{audit_id}
  Returns:     BiasAuditResult
  Auth:        Bearer JWT

GET    /v1/audits/{audit_id}/explain
  Query:       ?include_shap=true&include_counterfactuals=true
  Action:      SHAP computation (cached in Redis 1hr) + Gemini Pro call (cached in Redis 1hr)
  Returns:     { "narrative": str, "shap_plot_gcs_url": str, "counterfactuals": list }
  Auth:        Bearer JWT

GET    /v1/audits/{audit_id}/shap
  Returns:     { "feature_importance": dict, "slice_importances": dict, "plot_gcs_url": str }
  Auth:        Bearer JWT

POST   /v1/models/{model_id}/mitigate
  Body:        { "audit_id": str, "algorithm": str (optional — auto-select if omitted) }
  Action:      Trigger Vertex AI Pipeline run
  Returns:     { "mitigation_id": str, "pipeline_run_id": str, "status": "queued" }
  Auth:        Bearer JWT + ROLE_ADMIN

GET    /v1/models/{model_id}/mitigate/{mitigation_id}
  Returns:     MitigationRecord with current status
  Auth:        Bearer JWT

GET    /v1/models/{model_id}/drift
  Query:       ?window_days=30&metrics=demographic_parity_difference,...
  Returns:     time series of metric values + CUSUM drift detection output
  Auth:        Bearer JWT

GET    /v1/compliance/report/{model_id}
  Query:       ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&format=pdf|json
  Action:      Gemini generates narrative → reportlab renders PDF
  Returns:     application/pdf binary or JSON
  Auth:        Bearer JWT + ROLE_COMPLIANCE

GET    /v1/metrics/fairness/{model_id}
  Returns:     Prometheus text format for Cloud Monitoring scraping
  Auth:        Internal Cloud Run audience verification (no JWT)
```

---

## 13. Gemini Integration

In `services/explainer/gemini_service.py`. Use `google.generativeai` SDK. Fetch API key from Secret Manager at service startup — cache in memory, do not re-fetch per request.

```python
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def generate_bias_narrative(audit: BiasAuditResult, shap_features: dict) -> str:
    prompt = load_prompt("bias_narrative.txt").format(
        model_id=audit.model_id,
        window_start=audit.window_start.isoformat(),
        window_end=audit.window_end.isoformat(),
        sample_size=audit.sample_size,
        metrics_json=json.dumps(
            {k: {"value": round(v.value, 4), "threshold": v.threshold, "breached": v.breached}
             for k, v in audit.metrics.items()}, indent=2
        ),
        shap_features=json.dumps(shap_features, indent=2)
    )
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            temperature=0.2,
            max_output_tokens=1500,
        )
    )
    return response.text
```

### bias_narrative.txt
```
You are an expert AI fairness auditor. Analyze this bias audit result and write a clear, factual report for a compliance officer who is NOT a data scientist.

Model: {model_id}
Audit period: {window_start} to {window_end}
Predictions analyzed: {sample_size}

Bias metrics:
{metrics_json}

Top influential features (SHAP):
{shap_features}

Write EXACTLY these 5 sections with EXACTLY these headers:

## SUMMARY
Two sentences. What happened. How serious it is.

## ROOT CAUSE
Which specific features are driving the bias? Name them. Which data patterns are responsible?

## AFFECTED GROUPS
Who is being harmed? By how much? Cite specific numbers from the metrics above.

## IMMEDIATE ACTION REQUIRED
What must be done in the next 24 hours?

## REGULATORY EXPOSURE
Which regulations are potentially violated? Cite specific articles. EU AI Act Article numbers, EEOC 4/5ths rule, GDPR Article 22, India DPDPA provisions as applicable.

Use plain English. No jargon. Be direct. State facts, not possibilities.
```

### compliance_report.txt
```
Generate a formal AI bias regulatory compliance report.

Audit data:
{audit_json}

Mitigation actions taken:
{mitigation_json}

Structure exactly as follows:

1. EXECUTIVE SUMMARY (3-4 sentences)
2. AUDIT FINDINGS (all 12 metrics: name, value, threshold, PASS/BREACH)
3. EU AI ACT ASSESSMENT (Title III — which articles apply, are they violated?)
4. EEOC 4/5THS RULE ASSESSMENT (hiring use cases — is the 80% rule violated?)
5. RIGHT TO EXPLANATION STATUS (GDPR Art. 22 / DPDPA — is per-individual explanation available?)
6. REMEDIATION ACTIONS TAKEN (algorithm, metrics before/after, accuracy delta)
7. OUTSTANDING RISKS
8. CERTIFICATION STATEMENT

Professional language. All metric values verbatim from the audit data. Specific regulation citations only — no generic statements.
```

---

## 14. SHAP Integration

In `services/explainer/shap_service.py`:

```python
import shap

def compute_shap_values(
    model,                    # fitted sklearn-compatible estimator
    X_sample: pd.DataFrame,   # 500-1000 row sample
    sensitive_attr: str       # column name of sensitive attribute
) -> dict:
    # TreeExplainer for tree-based models (RF, XGBoost, LightGBM)
    # Fall back to KernelExplainer(nsamples=100) for non-tree models
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_sample)
        # For binary classification: shap_values is a list[ndarray] — use index [1] for positive class
        if isinstance(shap_values, list):
            shap_values = shap_values[1]
    except Exception:
        explainer = shap.KernelExplainer(model.predict_proba, shap.sample(X_sample, 100))
        shap_values = explainer.shap_values(X_sample, nsamples=100)[:, :, 1]

    feature_importance = dict(zip(
        X_sample.columns,
        np.abs(shap_values).mean(axis=0).tolist()
    ))

    slice_importances = {}
    for group in X_sample[sensitive_attr].unique():
        mask = X_sample[sensitive_attr] == group
        slice_importances[str(group)] = dict(zip(
            X_sample.columns,
            np.abs(shap_values[mask]).mean(axis=0).tolist()
        ))

    plot_gcs_url = _upload_shap_beeswarm_to_gcs(shap_values, X_sample)

    return {
        "feature_importance": feature_importance,
        "slice_importances": slice_importances,
        "plot_gcs_url": plot_gcs_url,
        "top_bias_drivers": sorted(feature_importance.items(), key=lambda x: -x[1])[:5]
    }
```

---

## 15. OmniML Model Class

Implement fully for sklearn. Stub `raise NotImplementedError` for PyTorch/TensorFlow/XGBoost — they get real adapters in a future sprint.

```python
class OmniMLModel:
    SUPPORTED_FRAMEWORKS = ["sklearn", "xgboost", "pytorch", "tensorflow"]

    def __init__(self, model_id: str, framework: str, model_obj: Any,
                 feature_names: list[str], label_col: str,
                 sensitive_features: list[str]):
        ...

    def predict(self, X: pd.DataFrame) -> np.ndarray: ...
    def predict_proba(self, X: pd.DataFrame) -> np.ndarray: ...
    def get_feature_names(self) -> list[str]: ...

    def to_aif360_dataset(self, X: pd.DataFrame, y: pd.Series,
                          privileged_groups: list[dict]) -> BinaryLabelDataset:
        """Convert to AIF360 BinaryLabelDataset. Required before any AIF360 algorithm."""
        df = X.copy()
        df[self.label_col] = y
        return BinaryLabelDataset(
            df=df,
            label_names=[self.label_col],
            protected_attribute_names=self.sensitive_features,
            privileged_protected_attributes=[
                [g[f] for f in self.sensitive_features] for g in privileged_groups
            ]
        )

    def save_to_gcs(self, gcs_path: str) -> str: ...
    
    @classmethod
    def load_from_gcs(cls, gcs_path: str) -> "OmniMLModel": ...

    def register_to_vertex(self, display_name: str, serving_container_image: str) -> str:
        """Upload model artifact to Vertex AI Model Registry. Returns resource name."""
        ...

    def get_metadata(self) -> dict:
        return {
            "model_id": self.model_id,
            "framework": self.framework,
            "feature_names": self.feature_names,
            "sensitive_features": self.sensitive_features,
            "created_at": datetime.utcnow().isoformat()
        }
```

---

## 16. Structured Logging

Every service must use this. Zero `print()` statements anywhere.

```python
# services/shared/logging.py
import google.cloud.logging
import logging
import json

def setup_logging(service_name: str) -> logging.Logger:
    client = google.cloud.logging.Client()
    client.setup_logging()
    logger = logging.getLogger(service_name)
    logger.setLevel(logging.INFO)
    return logger

def log_event(logger: logging.Logger, event_type: str, model_id: str,
              request_id: str, **kwargs):
    logger.info(json.dumps({
        "event_type": event_type,
        "model_id": model_id,
        "request_id": request_id,
        **kwargs
    }))
```

Every log entry must include `event_type`, `model_id`, `request_id`. These become structured filter fields in Cloud Logging.

---

## 17. Terraform — Key Non-Obvious Resources

```hcl
# Pub/Sub with dead-letter
resource "google_pubsub_topic" "predictions_ingest" {
  name                       = "fairops-predictions-ingest"
  message_retention_duration = "604800s"  # 7 days
}

resource "google_pubsub_subscription" "predictions_sub" {
  name  = "fairops-predictions-sub"
  topic = google_pubsub_topic.predictions_ingest.name
  ack_deadline_seconds = 60
  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "600s"
  }
  expiration_policy { ttl = "" }
}

# Cloud Spanner — deletion protection on
resource "google_spanner_instance" "audit_ledger" {
  name         = "fairops-audit"
  config       = "regional-us-central1"
  display_name = "FairOps Immutable Audit Ledger"
  num_nodes    = 1
}

resource "google_spanner_database" "fairops_ledger" {
  instance            = google_spanner_instance.audit_ledger.name
  name                = "fairops-ledger"
  deletion_protection = true
  ddl                 = [ /* DDL from Section 11 */ ]
}

# Cloud Monitoring — alert on CRITICAL bias
resource "google_monitoring_alert_policy" "critical_bias" {
  display_name = "FairOps Critical Bias Detected"
  combiner     = "OR"
  conditions {
    display_name = "Critical severity gauge > 0"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/fairops/bias_severity\" AND metric.labels.severity=\"CRITICAL\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
    }
  }
  notification_channels = [var.slack_notification_channel_id]
}

# Cloud Scheduler — audit every 15 min per model
resource "google_cloud_scheduler_job" "audit_trigger" {
  name      = "fairops-audit-trigger"
  schedule  = "*/15 * * * *"
  time_zone = "UTC"
  http_target {
    uri         = "${var.auditor_url}/v1/models/${var.model_id}/audit"
    http_method = "POST"
    oidc_token  { service_account_email = var.auditor_sa_email }
  }
}
```

---

## 18. CI/CD — Cloud Build

```yaml
steps:
  - name: 'python:3.11'
    id: unit-tests
    entrypoint: bash
    args:
      - -c
      - |
        pip install -r sdk/requirements-dev.txt
        pytest tests/unit/ -v --cov=services --cov=sdk --cov-fail-under=70

  - name: 'gcr.io/cloud-builders/docker'
    id: build-gateway
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/fairops/gateway:$COMMIT_SHA', 'services/gateway/']

  - name: 'gcr.io/cloud-builders/docker'
    id: build-auditor
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/fairops/auditor:$COMMIT_SHA', 'services/auditor/']

  - name: 'gcr.io/cloud-builders/docker'
    id: build-explainer
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/fairops/explainer:$COMMIT_SHA', 'services/explainer/']

  - name: 'gcr.io/cloud-builders/docker'
    id: build-notifier
    args: ['build', '-t', 'us-central1-docker.pkg.dev/$PROJECT_ID/fairops/notifier:$COMMIT_SHA', 'services/notifier/']

  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', '--all-tags', 'us-central1-docker.pkg.dev/$PROJECT_ID/fairops/gateway']

  - name: 'gcr.io/google.com/cloudsdktool/cloud-sdk'
    id: deploy-gateway
    entrypoint: gcloud
    args:
      - run
      - deploy
      - fairops-gateway
      - --image=us-central1-docker.pkg.dev/$PROJECT_ID/fairops/gateway:$COMMIT_SHA
      - --region=us-central1
      - --service-account=fairops-gateway@$PROJECT_ID.iam.gserviceaccount.com
      - --no-allow-unauthenticated
      - --min-instances=1
      - --max-instances=100
      - --memory=2Gi

  # Repeat deploy step for auditor, explainer, notifier

  - name: 'python:3.11'
    id: compile-pipeline
    entrypoint: bash
    args:
      - -c
      - |
        pip install kfp==2.6.0 google-cloud-aiplatform==1.43.0
        python pipelines/compile_pipeline.py

options:
  logging: CLOUD_LOGGING_ONLY
```

---

## 19. Sprint Plan

### Sprint 1 — Infrastructure + Data Ingestion
**Goal:** Real prediction event flows SDK → Pub/Sub → Dataflow → BigQuery.

- [ ] Terraform all infrastructure (`terraform apply` succeeds, all resources created)
- [ ] Implement all schemas in `sdk/fairops_sdk/schemas.py`
- [ ] Implement `sdk/fairops_sdk/publisher.py` — publish `PredictionEvent` to Cloud Pub/Sub
- [ ] Implement `services/stream_processor/pipeline.py` — Apache Beam on Dataflow:
  - Schema validation (malformed events → dead letter topic)
  - Demographic enrichment (direct label mapping; no proxy engine yet)
  - Write to `fairops_raw.predictions` + `fairops_enriched.demographics`
- [ ] Implement `POST /v1/predictions/ingest` in gateway
- [ ] Unit tests for all schemas (valid + invalid events)
- [ ] Publish 1000 UCI Adult prediction events via the SDK

**DoD:** A manually published Pub/Sub message appears as a row in `fairops_raw.predictions` within 60 seconds.

---

### Sprint 2 — Bias Detection Engine
**Goal:** Full 12-metric audit runs on BigQuery data, writes correct results.

- [ ] All 12 metric functions in `services/auditor/metrics/fairness.py`
- [ ] Bootstrap confidence intervals in `services/auditor/metrics/significance.py`
- [ ] CUSUM drift detection in `services/auditor/metrics/drift.py`
- [ ] Severity classifier in `services/auditor/severity.py`
- [ ] Demographic slice construction in `services/auditor/slicing.py`
- [ ] BQ writer in `services/auditor/bq_writer.py`
- [ ] Spanner writer in `services/auditor/spanner_writer.py` (writes `AUDIT_COMPLETED`)
- [ ] `POST /v1/models/{model_id}/audit` and `GET /v1/audits/{audit_id}` in gateway
- [ ] Unit test every metric with hand-crafted biased arrays (known expected values)
- [ ] Deploy auditor to Cloud Run

**DoD:** POST to `/v1/models/uci_adult_hiring/audit` returns `BiasAuditResult` with `disparate_impact_ratio` breached (value ≈ 0.38, threshold 0.80) and `overall_severity = CRITICAL`.

---

### Sprint 3 — Gemini Explainability + SHAP
**Goal:** Real Gemini-generated bias narrative returned from API.

- [ ] `services/explainer/shap_service.py` with TreeExplainer
- [ ] `services/explainer/gemini_service.py` with retry logic
- [ ] SHAP beeswarm plot → GCS upload
- [ ] Redis caching for SHAP + Gemini results (TTL 1 hour)
- [ ] `services/explainer/counterfactual.py` using DiCE
- [ ] `GET /v1/audits/{audit_id}/explain` and `GET /v1/audits/{audit_id}/shap`
- [ ] Gemini API key stored + fetched from Secret Manager
- [ ] Deploy explainer to Cloud Run

**DoD:** GET `/v1/audits/{audit_id}/explain` returns a Gemini narrative that names `sex` as the primary bias driver, cites a specific metric value, and mentions the EEOC 4/5ths rule violation.

---

### Sprint 4 — Vertex AI Mitigation Pipeline
**Goal:** Full automated detect → mitigate → promote loop running on real GCP.

- [ ] All 10 KFP v2 pipeline components in `pipelines/components/`
- [ ] Algorithm selector in `pipelines/mitigation_pipeline.py`
- [ ] `pipelines/compile_pipeline.py` compiles to YAML + uploads to GCS
- [ ] Reweighing mitigation fully implemented (AIF360)
- [ ] Accuracy gate with Pareto fallback (NSGA-II via pymoo)
- [ ] Model promotion to Vertex AI Model Registry
- [ ] Full `MitigationRecord` written to Cloud Spanner
- [ ] `POST /v1/models/{model_id}/mitigate` and status GET in gateway
- [ ] Cloud Scheduler set up to auto-trigger audits every 15 minutes
- [ ] Cloud Monitoring alert auto-triggers mitigation on CRITICAL

**DoD:** Full loop without manual intervention: ingestion → scheduler triggers audit → CRITICAL detected → Vertex AI Pipeline auto-starts → Reweighing applied → debiased model trained → `disparate_impact_ratio` improves from ≈0.38 to >0.80 → model promoted to Vertex AI Model Registry → MitigationRecord in Cloud Spanner.

---

### Sprint 5 — Dashboard, Alerts, Compliance PDF
**Goal:** Everything is visible and auditable.

- [ ] Looker Studio dashboard with BigQuery BI Engine:
  - Model Fairness Scorecard (gauges, all 12 metrics, RAG status)
  - Demographic Slice Drill-Down (bar chart, prediction rates per group with CIs)
  - Temporal Trend View (30-day bias metric line chart)
  - Intersectional Heatmap (group × attribute bias score matrix)
  - Mitigation History Timeline (before/after comparison per mitigation event)
- [ ] `services/notifier/` — Slack webhook on CRITICAL/HIGH with model ID, severity, top metric
- [ ] `GET /v1/compliance/report/{model_id}` — Gemini narrative + reportlab PDF
- [ ] Cloud Monitoring custom metrics (bias severity per model)
- [ ] Alert policy in Terraform (Section 17)
- [ ] End-to-end integration test

**DoD:** After a CRITICAL audit: Slack message received within 2 minutes. PDF compliance report generated with all 8 sections populated. Looker Studio shows the audit with correct RAG color.

---

### Sprint 6 — Security Hardening + Load Testing
**Goal:** Passes security checklist. Handles 10k predictions/second.

- [ ] Locust load test at 10k predictions/sec for 5 minutes — < 5% error rate
- [ ] Dataflow autoscaling verified under load
- [ ] Cloud Armor WAF on gateway (OWASP Top 10 ruleset) via Terraform
- [ ] VPC Service Controls for BigQuery + Cloud Storage
- [ ] Binary Authorization for all Cloud Run services
- [ ] Cloud DLP templates wired into stream processor (inspect + deidentify)
- [ ] AES-256 CMEK for BigQuery datasets via Cloud KMS
- [ ] All secrets confirmed in Secret Manager — zero in env files or code
- [ ] Least-privilege IAM audit: every service account binding reviewed
- [ ] End-to-end validation with all 4 datasets: COMPAS, HMDA, UCI Adult, ACS PUMS 2022

**DoD:** `gcloud` CLI verification passes for Cloud Armor, VPC SC, Binary Auth, CMEK. Load test shows < 5% error rate sustained at 10k req/sec.

---

## 20. Library Versions — Pin Exactly

```
aif360==0.6.1
fairlearn==0.10.0
shap==0.43.0
scikit-learn==1.4.0
xgboost==2.0.3
numpy==1.26.4
pandas==2.2.0
scipy==1.12.0
ruptures==1.1.9
pymoo==0.6.1.1
optuna==3.5.0
dice-ml==0.11
surgeo==1.0.2
gender-guesser==0.4.0

fastapi==0.110.0
uvicorn[standard]==0.27.0
pydantic==2.6.0
python-jose[cryptography]==3.3.0
httpx==0.27.0
redis==5.0.1
tenacity==8.2.3

google-cloud-pubsub==2.20.0
google-cloud-bigquery==3.17.0
google-cloud-spanner==3.42.0
google-cloud-aiplatform==1.43.0
google-cloud-dlp==3.15.0
google-cloud-logging==3.9.0
google-cloud-secret-manager==2.18.0
google-cloud-storage==2.14.0
google-generativeai==0.4.0
apache-beam[gcp]==2.54.0

kfp==2.6.0

reportlab==4.1.0
PyMuPDF==1.23.0

opentelemetry-sdk==1.22.0
opentelemetry-exporter-gcp-trace==1.6.0

pytest==8.0.0
pytest-asyncio==0.23.0
pytest-cov==4.1.0
locust==2.23.1
```

---

## 21. Known Hard Problems — Read Before You Hit Them

**AIF360 dataset format:** Every AIF360 algorithm requires `BinaryLabelDataset`, not numpy arrays. Always convert via `OmniMLModel.to_aif360_dataset()`. The `privileged_protected_attributes` argument is a list-of-lists. Getting this wrong produces silently wrong mitigation with no error.

**SHAP multiclass output:** For binary classifiers, `shap.TreeExplainer.shap_values()` returns a `list[ndarray]`, one per class. Always use index `[1]` for the positive class in binary classification.

**KFP v2 component I/O:** Components communicate via typed KFP artifact types (`Input[Dataset]`, `Output[Model]`), not raw GCS path strings. Passing strings between components is KFP v1 syntax and will not work.

**Cloud Spanner write batching:** Use the `batch()` context manager. Never single-row inserts in a loop — the transaction cost will destroy performance.

**Gemini rate limits:** `gemini-pro` is 60 requests/minute on the standard tier. Use `tenacity` exponential backoff (already in the code spec). Cache responses in Redis — the same audit result should never trigger two Gemini calls.

**UCI Adult dataset quirks:** Raw column name is `sex` with values `Male`/`Female`. Income label is `income` with values ` <=50K` / ` >50K` (leading space — strip it before encoding). Privileged group is `Male`. A vanilla `RandomForestClassifier` on raw features gives `disparate_impact_ratio ≈ 0.35-0.42` — well below the 0.80 EEOC threshold. This is the demo anchor metric.

**BigQuery streaming vs batch:** Use streaming inserts for prediction events (real-time queryable). Use batch loads (GCS → BQ) for training data pulled into the mitigation pipeline. Streaming has per-row costs; batch is cheaper but has up to 90-minute availability delay.

**AIF360 + TensorFlow dependency conflict:** `aif360` pulls in TensorFlow. If this causes version conflicts with other packages, install AIF360 without extras: `pip install aif360 --no-deps` then manually add only the AIF360 dependencies you need (`fairlearn`, `numpy`, `pandas`, `scipy`, `scikit-learn`).

---

*FairOps | Google Solution Challenge 2026 | Real GCP stack. No shortcuts.*
