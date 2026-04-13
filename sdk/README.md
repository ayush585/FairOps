# FairOps SDK

**FairOps SDK** is the standalone client library for integrating machine learning prediction streams into the FairOps compliance pipeline. It enables real-time transmission of prediction events, probabilities, ground truths, and sensitive demographic cuts seamlessly to Google BigQuery and the FairOps Engine.

## Installation

You can install the SDK via pip:

```bash
pip install fairops-sdk
```

## Quick Start

Integrating your model takes literally 3 lines of code:

```python
from fairops_sdk import FairOpsClient

# 1. Initialize mapping your GCP tracking configurations
client = FairOpsClient(
    project_id="your-gcp-project-id",
    # topic_id="fairops-predictions" # Uses default if omitted
)

# 2. Extract your features / scores
features = {"income": 45000, "credit": "Good"}
demographics = {"race": "White", "sex": "Female"}

# 3. Stream the prediction to the Auditor Pipeline
client.log_prediction(
    model_id="credit-risk-v1",
    prediction_label=1,
    prediction_score=0.88,
    features=features,
    demographic_tags=demographics,
    ground_truth=1  # Optional: Log if doing delayed ground-truth syncing
)
```

## Why FairOps?
The `fairops-sdk` is an asynchronous, non-blocking telemetry client. When you call `log_prediction`, the payload is aggressively validated using PyDantic schemas before being offloaded to a background thread to prevent any latency injection on your actual API inference gateways. 

It handles network retries, connection backoffs, and strict typing automatically.

## Requirements
- Python 3.11+
- `google-cloud-pubsub`
- `pydantic >= 2.6.0`

## Authors & License
Maintained by the FairOps Open Source team. Licensed under Apache 2.0.
