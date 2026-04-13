"""
FairOps Explainer — PDF Compliance Report Generator.

Generates formal AI bias regulatory compliance reports using reportlab.
Gemini Pro provides the narrative; reportlab renders the PDF.

Covers:
- EEOC 4/5ths Rule (Disparate Impact < 0.80)
- EU AI Act Article 10 (training data diversity)
- GDPR Article 22 (automated decision-making)

Ref: AGENT.md Sprint 3, Section 21 (reportlab==4.1.0).
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("fairops.explainer.compliance_report")

# Color palette (FairOps brand)
COLORS = {
    "primary": (0.10, 0.14, 0.49),    # Deep indigo
    "critical": (0.85, 0.12, 0.12),   # Red
    "high": (0.90, 0.45, 0.00),       # Orange
    "medium": (0.95, 0.77, 0.06),     # Yellow
    "low": (0.20, 0.63, 0.33),        # Green
    "pass": (0.20, 0.63, 0.33),       # Green
    "light_gray": (0.95, 0.95, 0.95),
    "dark_gray": (0.30, 0.30, 0.30),
}

SEVERITY_COLORS = {
    "CRITICAL": COLORS["critical"],
    "HIGH": COLORS["high"],
    "MEDIUM": COLORS["medium"],
    "LOW": COLORS["low"],
    "PASS": COLORS["pass"],
}


def generate_pdf_report(
    model_id: str,
    model_version: str,
    start_date: str,
    end_date: str,
    overall_severity: str,
    sample_size: int,
    metrics: dict,
    demographic_slices: list,
    narrative: str,
    audit_ids: Optional[list[str]] = None,
) -> bytes:
    """
    Generate a formal PDF compliance report.

    Args:
        model_id: Model under review.
        model_version: Model version.
        start_date: Report period start (YYYY-MM-DD).
        end_date: Report period end (YYYY-MM-DD).
        overall_severity: Worst severity in the period.
        sample_size: Total predictions analyzed.
        metrics: Dict of metric_name → metric data.
        demographic_slices: List of demographic slice dicts.
        narrative: Gemini Pro narrative markdown text.
        audit_ids: List of audit IDs covered by this report.

    Returns:
        PDF bytes.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            HRFlowable, PageBreak,
        )
        from reportlab.lib.colors import HexColor, Color

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=2 * cm,
            leftMargin=2 * cm,
            topMargin=2 * cm,
            bottomMargin=2 * cm,
            title=f"FairOps Compliance Report — {model_id}",
            author="FairOps Automated Bias Monitoring",
        )

        styles = getSampleStyleSheet()

        # Custom styles
        title_style = ParagraphStyle(
            "FairOpsTitle",
            parent=styles["Title"],
            fontSize=22,
            textColor=Color(*COLORS["primary"]),
            spaceAfter=6,
        )
        heading1_style = ParagraphStyle(
            "FairOpsH1",
            parent=styles["Heading1"],
            fontSize=14,
            textColor=Color(*COLORS["primary"]),
            spaceBefore=12,
            spaceAfter=4,
        )
        heading2_style = ParagraphStyle(
            "FairOpsH2",
            parent=styles["Heading2"],
            fontSize=11,
            textColor=Color(*COLORS["dark_gray"]),
            spaceBefore=8,
            spaceAfter=2,
        )
        body_style = ParagraphStyle(
            "FairOpsBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=14,
            spaceAfter=4,
        )
        small_style = ParagraphStyle(
            "FairOpsSmall",
            parent=styles["Normal"],
            fontSize=8,
            textColor=Color(*COLORS["dark_gray"]),
        )

        severity_color = Color(*SEVERITY_COLORS.get(overall_severity, COLORS["dark_gray"]))

        elements = []

        # ── Cover Page ────────────────────────────────────────────────────────
        elements.append(Spacer(1, 1 * cm))
        elements.append(Paragraph("FairOps", title_style))
        elements.append(Paragraph("AI Bias Regulatory Compliance Report", styles["Heading2"]))
        elements.append(HRFlowable(width="100%", thickness=2, color=Color(*COLORS["primary"])))
        elements.append(Spacer(1, 0.5 * cm))

        # Report metadata table
        meta_data = [
            ["Model ID", model_id],
            ["Model Version", model_version],
            ["Report Period", f"{start_date} to {end_date}"],
            ["Predictions Analyzed", f"{sample_size:,}"],
            ["Overall Severity", overall_severity],
            ["Report Generated", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
            ["Audits Covered", str(len(audit_ids or []))],
        ]

        meta_table = Table(meta_data, colWidths=[5 * cm, 12 * cm])
        meta_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), Color(*COLORS["light_gray"])),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [Color(*COLORS["light_gray"]), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("TEXTCOLOR", (1, 4), (1, 4), severity_color),
            ("FONTNAME", (1, 4), (1, 4), "Helvetica-Bold"),
            ("FONTSIZE", (1, 4), (1, 4), 11),
            ("PADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(meta_table)
        elements.append(Spacer(1, 0.5 * cm))

        # ── Regulatory Framework ──────────────────────────────────────────────
        elements.append(Paragraph("Regulatory Framework", heading1_style))
        regs = [
            ["Regulation", "Relevant Metric", "Status"],
            [
                "EEOC 4/5ths Rule",
                "Disparate Impact Ratio (threshold: 0.80)",
                _get_metric_status(metrics, "disparate_impact_ratio"),
            ],
            [
                "EU AI Act Art. 10\n(High-Risk AI)",
                "Demographic Parity Diff (threshold: 0.10)",
                _get_metric_status(metrics, "demographic_parity_difference"),
            ],
            [
                "GDPR Art. 22\n(Automated Decisions)",
                "Counterfactual Fairness (threshold: 0.06)",
                _get_metric_status(metrics, "counterfactual_fairness"),
            ],
        ]
        reg_table = Table(regs, colWidths=[5 * cm, 8 * cm, 4 * cm])
        reg_table.setStyle(_metric_table_style(metrics))
        elements.append(reg_table)
        elements.append(Spacer(1, 0.3 * cm))

        # ── Fairness Metrics Table ────────────────────────────────────────────
        elements.append(Paragraph("Fairness Metrics Summary (All 12)", heading1_style))

        metric_rows = [["Metric", "Value", "Threshold", "Breach", "Severity", "p-value"]]
        for name, m in metrics.items():
            breach = "✗ YES" if m.get("breached") else "✓ PASS"
            sev = m.get("severity", "PASS")
            metric_rows.append([
                name.replace("_", " ").title(),
                f"{m.get('value', 0):.4f}",
                f"{m.get('threshold', 0):.4f}",
                breach,
                sev,
                f"{m.get('p_value', 1.0):.4f}",
            ])

        metrics_table = Table(metric_rows, colWidths=[5.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm])
        metrics_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("BACKGROUND", (0, 0), (-1, 0), Color(*COLORS["primary"])),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [Color(*COLORS["light_gray"]), colors.white]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ("PADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ]))
        elements.append(metrics_table)
        elements.append(Spacer(1, 0.3 * cm))

        # ── Demographic Slices ────────────────────────────────────────────────
        if demographic_slices:
            elements.append(Paragraph("Demographic Group Analysis", heading1_style))
            slice_rows = [["Group", "Count", "Positive Rate", "TPR", "FPR", "Precision"]]
            for s in demographic_slices[:15]:
                m = s.get("metrics", {})
                slice_rows.append([
                    f"{s.get('attribute')}={s.get('group_value')}",
                    str(s.get("count", 0)),
                    f"{s.get('positive_rate', 0):.3f}",
                    f"{m.get('true_positive_rate', 0):.3f}",
                    f"{m.get('false_positive_rate', 0):.3f}",
                    f"{m.get('precision', 0):.3f}",
                ])

            slice_table = Table(slice_rows, colWidths=[5*cm, 2*cm, 3*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            slice_table.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), Color(*COLORS["primary"])),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [Color(*COLORS["light_gray"]), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ("PADDING", (0, 0), (-1, -1), 4),
                ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ]))
            elements.append(slice_table)
            elements.append(Spacer(1, 0.3 * cm))

        # ── AI Narrative ──────────────────────────────────────────────────────
        elements.append(PageBreak())
        elements.append(Paragraph("AI-Generated Bias Analysis Narrative", heading1_style))
        elements.append(Paragraph(
            "The following narrative was generated by Gemini Pro based on the structured audit data above.",
            small_style
        ))
        elements.append(Spacer(1, 0.3 * cm))

        # Convert markdown narrative to reportlab paragraphs
        for line in narrative.split("\n"):
            line = line.strip()
            if not line:
                elements.append(Spacer(1, 0.15 * cm))
            elif line.startswith("## "):
                elements.append(Paragraph(line[3:], heading1_style))
            elif line.startswith("# "):
                elements.append(Paragraph(line[2:], title_style))
            elif line.startswith("**") and line.endswith("**"):
                elements.append(Paragraph(f"<b>{line[2:-2]}</b>", body_style))
            elif line.startswith("- "):
                elements.append(Paragraph(f"• {line[2:]}", body_style))
            else:
                # Safe rendering — strip markdown bold/italic
                clean = line.replace("**", "").replace("*", "").replace("`", "")
                elements.append(Paragraph(clean, body_style))

        # ── Footer ────────────────────────────────────────────────────────────
        elements.append(PageBreak())
        elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
        elements.append(Spacer(1, 0.2 * cm))
        elements.append(Paragraph(
            f"This report was automatically generated by FairOps v0.1.0 on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. "
            f"Audit IDs: {', '.join((audit_ids or [])[:5])}{'...' if len(audit_ids or []) > 5 else ''}.",
            small_style,
        ))

        doc.build(elements)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        logger.info(
            f"PDF report generated: {len(pdf_bytes)} bytes",
            extra={"model_id": model_id, "period": f"{start_date}/{end_date}"},
        )
        return pdf_bytes

    except ImportError:
        logger.error("reportlab not installed — cannot generate PDF")
        raise
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        raise


def _get_metric_status(metrics: dict, metric_name: str) -> str:
    """Get COMPLIANT/NON-COMPLIANT status for a metric."""
    m = metrics.get(metric_name, {})
    if not m:
        return "N/A"
    return "NON-COMPLIANT" if m.get("breached") else "COMPLIANT"


def _metric_table_style(metrics: dict) -> TableStyle:
    """Build table style for regulatory metrics table."""
    from reportlab.lib import colors
    from reportlab.lib.colors import Color

    return TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 0), (-1, 0), Color(*COLORS["primary"])),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [Color(*COLORS["light_gray"]), colors.white]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("PADDING", (0, 0), (-1, -1), 5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ])
