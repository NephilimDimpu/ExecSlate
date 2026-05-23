"""
ExecSlate — Analytics Workspace PDF Exporter
A lightweight PDF brief generated directly from a saved Analytics session.
Focused on the exploratory output (KPIs + charts + observations + notes),
not the full board-ready report (that's exports/export_functions.py).
"""

import base64
import io
import logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
)
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib import colors

logger = logging.getLogger("ExecSlate")


def _fmt_value(value, fmt, currency="$"):
    """Format a KPI value based on its declared format type."""
    try:
        v = float(value)
    except Exception:
        return str(value)
    if fmt == "currency":
        if abs(v) >= 1_000_000:
            return f"{currency}{v/1_000_000:.2f}M"
        if abs(v) >= 1_000:
            return f"{currency}{v/1_000:.1f}K"
        return f"{currency}{v:,.0f}"
    if fmt == "percent":
        return f"{v:.1f}%"
    if abs(v) >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v:,.0f}"
    return f"{v:,.0f}"


def _b64_to_image_flowable(b64_string, max_width_inches=6.5):
    """Decode a base64 PNG into a ReportLab Image flowable. Returns None on failure."""
    if not b64_string:
        return None
    try:
        raw = base64.b64decode(b64_string)
        bio = io.BytesIO(raw)
        img = Image(bio, width=max_width_inches * inch, height=(max_width_inches * 0.55) * inch)
        img.hAlign = 'CENTER'
        return img
    except Exception as e:
        logger.warning(f"Could not embed chart image: {e}")
        return None


def export_analytics_pdf(project, session, latest_draft, output_path):
    """
    Build a one-page-style PDF brief for the Analytics workspace.

    Args:
        project: project dict (client, period, etc.)
        session: latest analytics session dict (kpi_metrics, ai_insights, charts, ...)
        latest_draft: optional saved-draft dict with notes + selected_insights
        output_path: where to write the PDF
    """
    output_path = Path(output_path)
    doc = SimpleDocTemplate(
        str(output_path), pagesize=A4,
        leftMargin=0.6 * inch, rightMargin=0.6 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
        title=f"ExecSlate Analytics — {project.get('client', '')}",
    )

    styles = getSampleStyleSheet()
    brand = ParagraphStyle("Brand", parent=styles["Normal"],
                           fontName="Helvetica-Bold", fontSize=9,
                           textColor=colors.HexColor("#1e40af"),
                           alignment=TA_LEFT, spaceAfter=2)
    title = ParagraphStyle("Title", parent=styles["Title"], fontSize=20,
                           textColor=colors.HexColor("#0f172a"),
                           spaceAfter=4, alignment=TA_LEFT)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=10,
                         textColor=colors.HexColor("#64748b"), spaceAfter=14)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=12,
                        textColor=colors.HexColor("#0f172a"),
                        spaceBefore=14, spaceAfter=8)
    body = ParagraphStyle("Body", parent=styles["Normal"], fontSize=10,
                          textColor=colors.HexColor("#1e293b"),
                          leading=15, spaceAfter=5)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=14,
                            bulletIndent=2, spaceAfter=4)
    note = ParagraphStyle("Note", parent=body,
                          textColor=colors.HexColor("#475569"),
                          fontName="Helvetica-Oblique")

    story = []
    story.append(Paragraph("EXECSLATE — ANALYTICS BRIEF", brand))
    story.append(Paragraph(project.get("client") or "Untitled Project", title))
    period = project.get("period") or ""
    generated = datetime.now().strftime("%B %d, %Y")
    sub_text = f"Analytics workspace export &nbsp;·&nbsp; {period} &nbsp;·&nbsp; Generated {generated}"
    story.append(Paragraph(sub_text, sub))

    # ── Stat bar ──
    currency = session.get("currency") or project.get("currency") or "$"
    stat_cells = []
    if session.get("row_count"):
        stat_cells.append([Paragraph("<b>Rows</b>", body), Paragraph(f"{session['row_count']:,}", body)])
    if session.get("confidence"):
        stat_cells.append([Paragraph("<b>Confidence</b>", body), Paragraph(f"{session['confidence']}%", body)])
    if session.get("trend"):
        stat_cells.append([Paragraph("<b>Pattern</b>", body), Paragraph(session["trend"], body)])
    if session.get("growth_rate"):
        stat_cells.append([Paragraph("<b>Growth</b>", body),
                           Paragraph(f"{session['growth_rate']:.1f}%", body)])
    if session.get("primary_col"):
        primary_label = str(session["primary_col"]).replace("_", " ").title()
        stat_cells.append([Paragraph("<b>Primary KPI</b>", body), Paragraph(primary_label, body)])
    if stat_cells:
        stat_table = Table(stat_cells, colWidths=[1.4 * inch, 5.4 * inch])
        stat_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        story.append(stat_table)
        story.append(Spacer(1, 6))

    # ── KPIs ──
    kpis = session.get("kpi_metrics") or {}
    if kpis:
        story.append(Paragraph("Key Performance Indicators", h2))
        kpi_rows = [["Metric", "Total", "Average", "Direction"]]
        for key, m in list(kpis.items())[:10]:
            label = m.get("label") or key
            fmt = m.get("format", "number")
            val = _fmt_value(m.get("value"), fmt, currency) if "value" in m else _fmt_value(m.get("total", 0), fmt, currency)
            avg = _fmt_value(m.get("avg", 0), fmt, currency)
            direction = "↑ good" if m.get("direction") == "up_good" else ("↓ good" if m.get("direction") == "down_good" else "—")
            kpi_rows.append([label, val, avg, direction])
        kpi_table = Table(kpi_rows, colWidths=[2.5 * inch, 1.6 * inch, 1.6 * inch, 1.1 * inch])
        kpi_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e3a8a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (-1, 0), "LEFT"),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f8fafc")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
        ]))
        story.append(kpi_table)

    # ── Primary chart ──
    primary_img = _b64_to_image_flowable(session.get("revenue_chart_b64"))
    if primary_img:
        story.append(Spacer(1, 6))
        story.append(Paragraph("Primary View", h2))
        story.append(primary_img)

    # ── Breakdown chart ──
    breakdown_img = _b64_to_image_flowable(session.get("region_chart_b64"))
    if breakdown_img:
        story.append(Paragraph("Breakdown", h2))
        story.append(breakdown_img)

    # ── Observations ──
    insights = session.get("ai_insights") or []
    if insights:
        story.append(Paragraph("Observations", h2))
        for ins in insights:
            story.append(Paragraph(f"• {ins}", bullet))

    # ── Pinned + analyst notes from latest saved draft ──
    if latest_draft:
        pinned = latest_draft.get("selected_insights") or []
        notes_text = (latest_draft.get("notes") or "").strip()
        if pinned:
            story.append(Paragraph("Pinned for Decision", h2))
            for p in pinned:
                story.append(Paragraph(f"• {p}", bullet))
        if notes_text:
            story.append(Paragraph("Analyst Notes", h2))
            for line in notes_text.split("\n"):
                if line.strip():
                    story.append(Paragraph(line.strip(), body))

    # ── Footer ──
    story.append(Spacer(1, 18))
    footer = ParagraphStyle("Footer", parent=body, fontSize=8,
                            textColor=colors.HexColor("#94a3b8"),
                            alignment=TA_CENTER)
    story.append(Paragraph(
        f"Generated by ExecSlate · Analytics Workspace Export · {generated}",
        footer))

    doc.build(story)
    return output_path
