"""
Locust Load Testing for FairOps.

Simulates 10,000 predictions/second of ingestion load onto the SDK/streaming 
APIs to ensure the underlying BigQuery, Redis caching, and Spanner infrastructure 
does not bottleneck heavily or breach < 5% error rates.

Ref: AGENT.md Sprint 6.
"""

import uuid
import json
import random
import time
from datetime import datetime, timezone
from locust import HttpUser, task, between, events


class FairOpsLoadTester(HttpUser):
    # Simulated wait time between requests per simulated user
    wait_time = between(0.01, 0.05)

    @task
    def simulate_prediction_ingestion(self):
        """Simulates the SDK pushing a prediction event to a streaming endpoint."""
        
        # In a real environment, this would target the Cloud Run container
        # hosting the SDK ingestion endpoint. We use a mocked /v1/predictions/log endpoint.
        
        event_id = str(uuid.uuid4())
        
        payload = {
            "event_id": event_id,
            "model_id": "credit-risk-v3",
            "model_version": "3.1.0",
            "prediction_label": random.choice([0, 1]),
            "prediction_score": round(random.uniform(0.1, 0.9), 4),
            "prediction_threshold": 0.5,
            "ground_truth": random.choice([0, 1]), # For simulated continuous learning
            "demographic_tags": {
                "sex": random.choice(["Male", "Female"]),
                "race": random.choice(["White", "Black", "Hispanic", "Asian"]),
                "age_bin": random.choice(["AGE_18_30", "AGE_30_40", "AGE_40_65", "AGE_65_PLUS"])
            },
            "features": {
                "income": random.randint(30000, 150000),
                "credit_history": random.choice(["Good", "Poor", "Fair"]),
                "loan_amount": random.randint(1000, 50000)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        # Catch response logic to ensure < 5% error rate metrics
        with self.client.post(
            "/v1/predictions/log", 
            json=payload, 
            catch_response=True,
            timeout=2.0
        ) as response:
            if response.status_code == 200 or response.status_code == 201:
                response.success()
            else:
                response.failure(f"Failed with status: {response.status_code}")

# Use the Locust UI or run headless: `locust -f locustfile.py --headless -u 1000 -r 100 --run-time 1m`
