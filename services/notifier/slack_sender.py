"""
FairOps Notifier Service — Slack Integrations.

Formats bias alerts as interactive Slack Block Kit payloads
and dispatches them to compliance teams.

Ref: AGENT.md Sprint 5.
"""

import os
import logging
import httpx
from typing import Optional

logger = logging.getLogger("fairops.notifier.slack")


async def send_slack_alert(
    model_id: str,
    audit_id: str,
    severity: str,
    top_metric_name: str,
    top_metric_value: float,
    threshold: float,
    dashboard_url: str = "https://lookerstudio.google.com/navigation/reporting",
) -> bool:
    """
    Send a Slack alert for a bias breach using Block Kit formating.

    Args:
        model_id: Model that breached.
        audit_id: Unique audit identifier.
        severity: Severe rating (e.g. CRITICAL, HIGH).
        top_metric_name: Name of the worst breached metric.
        top_metric_value: Value of the breached metric.
        threshold: The threshold that was crossed.
        dashboard_url: URL to the Looker Studio dashboard.

    Returns:
        True if sent successfully, False otherwise.
    """
    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    # Block Kit UI construction
    color = "#FF0000" if severity == "CRITICAL" else "#FF8C00"
    emoji = "🚨" if severity == "CRITICAL" else "⚠️"
    
    clean_metric_name = top_metric_name.replace("_", " ").title()

    payload = {
        "text": f"{emoji} Bias Alert: {severity} severity detected on {model_id}",
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"{emoji} FairOps Alert: {severity} Bias",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Model ID:*\n`{model_id}`"},
                            {"type": "mrkdwn", "text": f"*Audit ID:*\n`{audit_id}`"}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Key Violation:*\n*{clean_metric_name}*\nValue: `{top_metric_value:.3f}` (Threshold: `{threshold:.3f}`)"
                        }
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View Dashboard",
                                    "emoji": True
                                },
                                "url": dashboard_url,
                                "style": "danger" if severity == "CRITICAL" else "primary"
                            }
                        ]
                    }
                ]
            }
        ]
    }

    if not webhook_url:
        # Development mode mock
        logger.warning(
            f"SLACK_WEBHOOK_URL not set! Mocking Slack delivery for {model_id}..."
        )
        import json
        logger.info(f"MOCK SLACK PAYLOAD:\n{json.dumps(payload, indent=2)}")
        return True

    # Real HTTP dispatch
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(webhook_url, json=payload, timeout=5.0)
            resp.raise_for_status()
            logger.info(f"Slack alert sent for model {model_id}")
            return True
    except Exception as e:
        logger.error(f"Failed to send Slack alert: {e}", exc_info=True)
        return False
