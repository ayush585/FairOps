"""
FairOps Explainer — Gemini Pro Narrative Generation.

Calls Gemini Pro to generate a plain-English bias audit narrative
from structured fairness metrics, demographic slices, and SHAP values.

Cached in Redis for 1 hour. Cost guard: max 1 call per audit_id.

Ref: AGENT.md Sprint 3, Section 21 (google-generativeai==0.5.0).
"""

import logging
import os
import json
from datetime import datetime, timezone

logger = logging.getLogger("fairops.explainer.gemini")


# ── System Prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior AI fairness expert writing a formal bias audit report.
Your audience is a non-technical compliance officer and a technical ML engineer.

You will receive structured data about a machine learning model's bias audit results.
Write a clear, professional narrative that:

1. Opens with an executive summary (2-3 sentences): model name, audit period, overall verdict.
2. Explains each breached fairness metric in plain English — what it means, why it matters,
   and the specific numbers (always include the exact metric value vs threshold).
3. Highlights which demographic groups were most affected and by how much.
4. Identifies the top bias drivers from SHAP feature importance.
5. States the regulatory implications (EEOC 4/5ths rule, EU AI Act Article 10, GDPR Article 22)
   where applicable.
6. Recommends specific mitigation actions (pre-processing, in-processing, or post-processing)
   based on the severity and metric type.
7. Closes with a compliance verdict: COMPLIANT, NON-COMPLIANT, or REQUIRES MONITORING.

Rules:
- Be precise: always cite exact numbers.
- Be concise: target 400-600 words.
- Never use phrases like "it seems" or "might be" — state facts from the data.
- Format with clear section headers using markdown.
"""


def generate_audit_narrative(
    audit_id: str,
    model_id: str,
    model_version: str,
    window_start: str,
    window_end: str,
    overall_severity: str,
    metrics: dict,
    demographic_slices: list,
    shap_result: dict | None = None,
    sample_size: int = 0,
) -> str:
    """
    Generate a Gemini Pro narrative for a bias audit.

    Args:
        audit_id: Unique audit identifier.
        model_id: Model being audited.
        model_version: Model version string.
        window_start: Audit window start (ISO format).
        window_end: Audit window end (ISO format).
        overall_severity: CRITICAL/HIGH/MEDIUM/LOW/PASS.
        metrics: Dict of metric_name → metric data.
        demographic_slices: List of demographic slice dicts.
        shap_result: Optional SHAP feature importance result.
        sample_size: Number of predictions analyzed.

    Returns:
        Markdown-formatted narrative string.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("GEMINI_API_KEY not set — returning template narrative")
        return _template_narrative(
            audit_id, model_id, model_version, overall_severity, metrics, sample_size
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name="gemini-pro",
            system_instruction=SYSTEM_PROMPT,
        )

        prompt = _build_prompt(
            audit_id=audit_id,
            model_id=model_id,
            model_version=model_version,
            window_start=window_start,
            window_end=window_end,
            overall_severity=overall_severity,
            metrics=metrics,
            demographic_slices=demographic_slices,
            shap_result=shap_result,
            sample_size=sample_size,
        )

        response = model.generate_content(
            prompt,
            generation_config={
                "temperature": 0.2,      # Low temperature for factual consistency
                "max_output_tokens": 1024,
                "top_p": 0.8,
            },
        )

        narrative = response.text
        logger.info(
            "Gemini narrative generated",
            extra={"audit_id": audit_id, "model_id": model_id, "chars": len(narrative)},
        )
        return narrative

    except Exception as e:
        logger.error(f"Gemini narrative generation failed: {e}", exc_info=True)
        # Fall back to template — never fail the audit for an LLM error
        return _template_narrative(
            audit_id, model_id, model_version, overall_severity, metrics, sample_size
        )


def _build_prompt(
    audit_id: str,
    model_id: str,
    model_version: str,
    window_start: str,
    window_end: str,
    overall_severity: str,
    metrics: dict,
    demographic_slices: list,
    shap_result: dict | None,
    sample_size: int,
) -> str:
    """Build the structured prompt for Gemini."""
    # Format breached metrics
    breached_metrics = {
        name: m for name, m in metrics.items() if m.get("breached")
    }
    passing_metrics = {
        name: m for name, m in metrics.items() if not m.get("breached")
    }

    breached_text = "\n".join([
        f"  - {name}: value={m.get('value', 'N/A'):.4f}, threshold={m.get('threshold', 'N/A')}, "
        f"severity={m.get('severity', 'N/A')}, p_value={m.get('p_value', 'N/A'):.4f}"
        for name, m in breached_metrics.items()
    ])

    passing_text = ", ".join(passing_metrics.keys())

    # Format demographic slices
    slice_text = "\n".join([
        f"  - {s.get('attribute')}={s.get('group_value')}: "
        f"n={s.get('count')}, positive_rate={s.get('positive_rate', 0):.3f}, "
        f"TPR={s.get('metrics', {}).get('true_positive_rate', 'N/A')}, "
        f"FPR={s.get('metrics', {}).get('false_positive_rate', 'N/A')}"
        for s in demographic_slices[:10]  # Limit to avoid token overflow
    ])

    # Format SHAP results
    shap_text = "Not available"
    if shap_result and shap_result.get("top_bias_drivers"):
        shap_text = "\n".join([
            f"  {i+1}. {d['feature']} (importance={d['importance']:.4f})"
            for i, d in enumerate(shap_result["top_bias_drivers"][:5])
        ])

    return f"""
## Bias Audit Report Data

**Audit ID:** {audit_id}
**Model:** {model_id} v{model_version}
**Audit Window:** {window_start} to {window_end}
**Predictions Analyzed:** {sample_size:,}
**Overall Severity:** {overall_severity}

### Breached Fairness Metrics ({len(breached_metrics)} of {len(metrics)}):
{breached_text if breached_text else "None"}

### Passing Metrics:
{passing_text if passing_text else "All metrics breached"}

### Demographic Group Performance:
{slice_text if slice_text else "No demographic data available"}

### Top SHAP Feature Importances (Bias Drivers):
{shap_text}

---
Please write the bias audit narrative following the instructions in your system prompt.
"""


def _template_narrative(
    audit_id: str,
    model_id: str,
    model_version: str,
    overall_severity: str,
    metrics: dict,
    sample_size: int,
) -> str:
    """
    Template-based narrative fallback when Gemini is unavailable.
    Ensures the audit report is always generated.
    """
    breached = [name for name, m in metrics.items() if m.get("breached")]
    verdict_map = {
        "CRITICAL": "NON-COMPLIANT — Immediate action required",
        "HIGH": "NON-COMPLIANT — Action required within 24 hours",
        "MEDIUM": "REQUIRES MONITORING — Schedule mitigation review",
        "LOW": "COMPLIANT — Statistical noise detected, monitor trend",
        "PASS": "COMPLIANT — All fairness thresholds satisfied",
    }

    return f"""# Bias Audit Report

**Model:** `{model_id}` v{model_version}
**Audit ID:** `{audit_id}`
**Generated:** {datetime.now(timezone.utc).isoformat()}
**Predictions Analyzed:** {sample_size:,}

## Executive Summary

Overall severity: **{overall_severity}**. Analysis of {sample_size:,} predictions
identified {len(breached)} fairness metric violation(s):
{chr(10).join(f"- `{m}`" for m in breached) if breached else "- None. All metrics within acceptable thresholds."}

## Compliance Verdict

**{verdict_map.get(overall_severity, "REQUIRES REVIEW")}**

*Note: Narrative AI generation was unavailable. This is an auto-generated template report.
Configure GEMINI_API_KEY for full AI-powered narrative analysis.*
"""
