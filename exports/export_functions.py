"""
ExecSlate Export Functions — Consulting-Grade PDF, PPT, DOCX
Phase A: Export Polish
"""
import os, re, logging
from datetime import datetime
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak,
    Table, TableStyle, HRFlowable
)
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib import colors
from reportlab.platypus.doctemplate import PageTemplate, BaseDocTemplate, Frame
from reportlab.platypus.tableofcontents import TableOfContents

from pptx import Presentation
from pptx.util import Inches, Pt as PptPt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR

import enhanced_analysis as ea

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).parent.parent

# ═══════════════════ BRAND PALETTE ═══════════════════
BRAND = {
    "navy":     "#0f172a",
    "dark":     "#1e293b",
    "slate":    "#334155",
    "gray":     "#64748b",
    "light":    "#f1f5f9",
    "lighter":  "#f8fafc",
    "accent":   "#3b82f6",
    "green":    "#10b981",
    "red":      "#ef4444",
    "white":    "#ffffff",
    "border":   "#e2e8f0",
}

def _hex(key):
    return colors.HexColor(BRAND[key])


# ╔════════════════════════════════════════════════════════════╗
# ║                   PDF EXPORT (ReportLab)                  ║
# ╚════════════════════════════════════════════════════════════╝

class _PDFWithHeaderFooter(SimpleDocTemplate):
    """PDF template with branded header/footer and page numbers."""

    def __init__(self, *args, project=None, user_plan="free", **kwargs):
        self._project = project or {}
        self._user_plan = user_plan
        super().__init__(*args, **kwargs)

    def afterPage(self):
        canvas = self.canv
        w, h = self.pagesize
        page_num = canvas.getPageNumber()

        # ── Footer line ──
        canvas.setStrokeColor(_hex("border"))
        canvas.setLineWidth(0.5)
        canvas.line(50, 42, w - 50, 42)

        # Left: confidential
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(_hex("gray"))
        canvas.drawString(50, 30, "STRICTLY CONFIDENTIAL")

        # Center: page
        canvas.setFont("Helvetica", 8)
        canvas.drawCentredString(w / 2, 30, f"- {page_num} -")

        # Right: brand
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(_hex("navy"))
        canvas.drawRightString(w - 50, 30, "■ EXECSLATE")

        # Watermark for free
        if self._user_plan in ("free", "demo"):
            canvas.saveState()
            canvas.setFont("Helvetica-Bold", 60)
            canvas.setFillColor(colors.Color(0, 0, 0, alpha=0.03))
            canvas.translate(w / 2, h / 2)
            canvas.rotate(45)
            canvas.drawCentredString(0, 0, "DRAFT / TRIAL")
            canvas.restoreState()


def _pdf_cover_page(Story, styles, project, currency):
    """Build a professional dark cover page."""
    # Spacer to push content down for vertical centering (Premium feel)
    Story.append(Spacer(1, 140))

    # Brand mark with Blue Accent Square
    brand_style = ParagraphStyle(
        'BrandMark', parent=styles['Normal'],
        fontSize=18, textColor=_hex("navy"),
        alignment=TA_CENTER, spaceAfter=16,
        fontName='Helvetica-Bold'
    )
    Story.append(Paragraph(f'<font color="{BRAND["accent"]}">■</font> &nbsp;E X E C S L A T E', brand_style))

    # Divider Line (Sleek minimalist)
    Story.append(Spacer(1, 20))
    Story.append(HRFlowable(
        width="20%", thickness=3, color=_hex("accent"),
        spaceAfter=30, hAlign='CENTER'
    ))

    # Title
    title_style = ParagraphStyle(
        'CoverTitle', parent=styles['Heading1'],
        fontSize=36, leading=42, alignment=TA_CENTER,
        textColor=_hex("navy"), spaceAfter=16,
        fontName='Helvetica-Bold'
    )
    Story.append(Paragraph(project.get('report_title', 'Executive Performance Report'), title_style))

    # Client name
    client_style = ParagraphStyle(
        'CoverClient', parent=styles['Normal'],
        fontSize=24, alignment=TA_CENTER,
        textColor=_hex("slate"), spaceAfter=10,
        fontName='Helvetica'
    )
    Story.append(Paragraph(project.get('client', 'Client'), client_style))

    # Period
    period_style = ParagraphStyle(
        'CoverPeriod', parent=styles['Normal'],
        fontSize=16, alignment=TA_CENTER,
        textColor=_hex("gray"), spaceAfter=50,
        fontName='Helvetica'
    )
    Story.append(Paragraph(project.get('period', ''), period_style))

    # Decorative Divider
    Story.append(HRFlowable(
        width="50%", thickness=1, color=_hex("border"),
        spaceAfter=40, hAlign='CENTER'
    ))

    # Meta info block with subtle typography
    meta_style = ParagraphStyle(
        'CoverMeta', parent=styles['Normal'],
        fontSize=11, alignment=TA_CENTER,
        textColor=_hex("gray"), spaceAfter=8,
        fontName='Helvetica'
    )
    Story.append(Paragraph(
        f"<b>Prepared on:</b> {datetime.now().strftime('%B %d, %Y')}",
        meta_style
    ))

    report_type = project.get('report_type', 'statistical')
    type_label = "AI-Driven Strategic Analysis" if report_type == "ai" else "Quantitative Statistical Analysis"
    Story.append(Paragraph(f"<b>Engagement Type:</b> {type_label}", meta_style))

    total = project.get('total_revenue', 0)
    Story.append(Paragraph(
        f"<b>Scope:</b> {currency}{total:,.0f} Analyzed", meta_style
    ))

    # Confidential badge - moved to footer natively
    Story.append(Spacer(1, 80))
    conf_style = ParagraphStyle(
        'Confidential', parent=styles['Normal'],
        fontSize=10, alignment=TA_CENTER,
        textColor=_hex("gray"), fontName='Helvetica-Bold'
    )
    Story.append(Paragraph("STRICTLY CONFIDENTIAL", conf_style))

    Story.append(PageBreak())


def _section_header(text, styles):
    """Create a styled section header with accent bar."""
    return Paragraph(
        f'<font color="{BRAND["accent"]}">■</font> &nbsp; {text}',
        ParagraphStyle(
            'SectionHead', parent=styles['Heading2'],
            fontSize=18, spaceBefore=24, spaceAfter=14,
            textColor=_hex("navy"), fontName='Helvetica-Bold',
            borderPadding=(0, 0, 4, 0)
        )
    )


def export_pdf_enhanced(project, output_path, user_plan="free"):
    """Generate consulting-grade PDF report."""
    currency = project.get('currency', '$')

    doc = _PDFWithHeaderFooter(
        output_path, pagesize=A4,
        rightMargin=50, leftMargin=50,
        topMargin=60, bottomMargin=55,
        project=project, user_plan=user_plan
    )
    styles = getSampleStyleSheet()

    # ── Custom styles ──
    normal = ParagraphStyle(
        'Body', parent=styles['Normal'],
        fontSize=10.5, leading=16, spaceAfter=8,
        textColor=_hex("slate")
    )
    metric_label = ParagraphStyle(
        'MetricLabel', parent=normal,
        fontName='Helvetica-Bold', textColor=_hex("navy")
    )
    caption = ParagraphStyle(
        'ChartCaption', parent=normal,
        fontSize=9, textColor=_hex("gray"),
        alignment=TA_CENTER, spaceBefore=4
    )
    locked = ParagraphStyle(
        'Locked', parent=normal, fontSize=10,
        textColor=_hex("gray"), alignment=TA_CENTER,
        fontName='Helvetica-Oblique'
    )

    Story = []

    # ═══ COVER PAGE ═══
    _pdf_cover_page(Story, styles, project, currency)

    # ═══ TABLE OF CONTENTS ═══
    Story.append(_section_header("Table of Contents", styles))
    toc_items = [
        "1. Executive Summary",
        "2. Key Performance Metrics",
        "3. Market Segmentation Analysis",
        "4. Visual Analysis",
        "5. Strategic Insights",
        "6. Recommendations",
    ]
    if project.get('ai_qa'):
        toc_items.append("7. Board Q&A")

    for item in toc_items:
        Story.append(Paragraph(item, ParagraphStyle(
            'TOCItem', parent=normal, fontSize=11,
            spaceBefore=6, spaceAfter=6, leftIndent=20,
            textColor=_hex("dark")
        )))
    Story.append(PageBreak())

    # ═══ 1. EXECUTIVE SUMMARY ═══
    # --- Consultant's Working Theory (NEW) ---
    working_theory = project.get("working_theory")
    if working_theory:
        Story.append(Paragraph("Consultant's Working Theory", ParagraphStyle(
            'TheoryTitle', parent=styles['Heading3'], fontSize=12, textColor=_hex("accent"),
            spaceBefore=14, spaceAfter=8, fontName='Helvetica-Bold'
        )))
        Story.append(Paragraph(working_theory, ParagraphStyle(
            'TheoryBody', parent=normal, leftIndent=10, borderPadding=8,
            backColor=_hex("lighter"), borderColor=_hex("border"), borderWidth=0.5
        )))
        Story.append(Spacer(1, 12))

    Story.append(_section_header("Executive Summary", styles))
    summary = project.get("ai_summary", "No summary available.")
    Story.append(Paragraph(summary, normal))
    Story.append(Spacer(1, 16))

    # --- Strategic Hypotheses (NEW) ---
    hypotheses = project.get("hypotheses", [])
    if hypotheses:
        Story.append(Paragraph("Strategic Hypotheses", ParagraphStyle(
            'HypoTitle', parent=styles['Heading3'], fontSize=12, textColor=_hex("navy"),
            spaceBefore=10, spaceAfter=8, fontName='Helvetica-Bold'
        )))
        for h in hypotheses:
            h_text = f"<b>{h.get('id', 'H')}:</b> {h.get('statement', '')}"
            Story.append(Paragraph(h_text, normal))
            Story.append(Paragraph(f"<i>Validation: {h.get('validation_plan', '')}</i>", 
                                   ParagraphStyle('HypoVal', parent=normal, fontSize=9, leftIndent=15, textColor=_hex("gray"))))
        Story.append(Spacer(1, 16))

    # ═══ 2. KEY PERFORMANCE METRICS ═══
    Story.append(_section_header("Key Performance Metrics", styles))

    kpi_data = [["Metric", "Value", "Growth", "Trend"]]

    # Phase B: Use multi-KPI data if available
    kpi_metrics = project.get('kpi_metrics', {})
    if kpi_metrics:
        # Sort by priority
        sorted_kpis = sorted(kpi_metrics.items(), key=lambda x: x[1].get('priority', 99))
        for col_name, kpi in sorted_kpis:
            label = kpi.get('label', col_name)
            fmt = kpi.get('format', 'number')
            total = kpi.get('total', 0)
            growth = kpi.get('growth', 0)
            trend = kpi.get('trend', 'flat')

            # Format value
            if fmt == 'currency':
                val_str = f"{currency}{total:,.0f}"
            elif fmt == 'percent':
                val_str = f"{kpi.get('avg', 0):.1f}%"
            else:
                val_str = f"{total:,.0f}"

            # Trend indicator
            growth_str = f"{growth:+.1f}%"
            trend_str = "▲" if trend == "up" else "▼" if trend == "down" else "—"

            kpi_data.append([label, val_str, growth_str, trend_str])
    else:
        # Fallback: revenue-only (backward compat)
        kpi_data.extend([
            ["Total Revenue", f"{currency}{project.get('total_revenue', 0):,.0f}",
             f"{project.get('growth_rate', 0):+.1f}%",
             "▲" if project.get('growth_rate', 0) > 0 else "▼" if project.get('growth_rate', 0) < 0 else "—"],
            ["Average Revenue", f"{currency}{project.get('avg_revenue', 0):,.0f}", "—", "—"],
            ["Median Revenue", f"{currency}{project.get('median_revenue', 0):,.0f}", "—", "—"],
        ])

    # Common rows
    kpi_data.extend([
        ["Top Market", project.get('top_region', 'N/A'), "", ""],
        ["Data Points", str(project.get('row_count', 0)), "", ""],
        ["Confidence", f"{project.get('confidence', 0)}%", "", ""],
    ])

    t = Table(kpi_data, colWidths=[2.2 * inch, 2.0 * inch, 1.0 * inch, 0.6 * inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), _hex("navy")),
        ('TEXTCOLOR', (0, 0), (-1, 0), _hex("white")),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('LINEABOVE', (0, 0), (-1, 0), 1.5, _hex("navy")),
        ('LINEBELOW', (0, 0), (-1, 0), 1.5, _hex("accent")),
        ('LINEBELOW', (0, 1), (-1, -1), 0.5, _hex("border")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [_hex("white"), _hex("lighter")]),
    ]))
    Story.append(t)
    Story.append(Spacer(1, 16))

    # ═══ 3. MARKET SEGMENTATION ═══
    comp = project.get('comprehensive_analysis')
    if comp and comp.get('segmentation'):
        Story.append(_section_header("Market Segmentation Analysis", styles))

        seg = comp['segmentation']
        for metric, dims in seg.items():
            for dim_name, dim_data in dims.items():
                metric_label = metric.replace('_', ' ').title()
                Story.append(Paragraph(
                    f"<b>{dim_name.replace('_', ' ').title()}</b> — {metric_label} Breakdown",
                    ParagraphStyle('DimTitle', parent=normal, fontSize=12,
                                   textColor=_hex("dark"), spaceBefore=14, spaceAfter=8)
                ))

                seg_rows = [["Rank", "Segment", "Revenue", "% Share"]]
                top = dim_data.get('top_performer', {})
                bot = dim_data.get('bottom_performer', {})
                count = dim_data.get('segment_count', 0)

                if top:
                    seg_rows.append([
                        "🏆 #1", top.get('name', 'N/A'),
                        f"{currency}{top.get('value', 0):,.0f}",
                        f"{top.get('pct', 0):.1f}%"
                    ])
                if bot:
                    seg_rows.append([
                        f"#{count}", bot.get('name', 'N/A'),
                        f"{currency}{bot.get('value', 0):,.0f}",
                        f"{bot.get('pct', 0):.1f}%"
                    ])

                if len(seg_rows) > 1:
                    st = Table(seg_rows, colWidths=[0.8*inch, 2.2*inch, 1.8*inch, 1*inch])
                    st.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), _hex("dark")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), _hex("white")),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9.5),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                        ('TOPPADDING', (0, 0), (-1, -1), 10),
                        ('LINEBELOW', (0, 0), (-1, 0), 1.5, _hex("accent")),
                        ('LINEBELOW', (0, 1), (-1, -1), 0.5, _hex("border")),
                        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
                        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                    ]))
                    Story.append(st)
                    Story.append(Spacer(1, 8))

    Story.append(PageBreak())

    # ═══ 4. VISUAL ANALYSIS ═══
    Story.append(_section_header("Visual Analysis", styles))

    narratives = project.get('chart_narratives', {})

    for chart_key, chart_label in [('revenue_chart', 'Revenue Trend'), ('region_chart', 'Regional Distribution')]:
        if project.get(chart_key):
            chart_path = BASE_DIR / project[chart_key].lstrip('/')
            if chart_path.exists():
                Story.append(Paragraph(f"<b>{chart_label}</b>", ParagraphStyle(
                    'ChartTitle', parent=normal, fontSize=12, textColor=_hex("dark"), spaceBefore=10
                )))
                im = Image(str(chart_path), 5.8 * inch, 2.9 * inch)
                Story.append(im)
                # Add narrative caption if available
                narr_key = 'revenue' if 'revenue' in chart_key else 'region'
                if narratives.get(narr_key):
                    Story.append(Paragraph(narratives[narr_key], caption))
                Story.append(Spacer(1, 16))

    Story.append(PageBreak())

    # ═══ 5. STRATEGIC INSIGHTS ═══
    Story.append(_section_header("Strategic Insights", styles))
    insights = project.get('ai_insights', [])

    visible = insights[:2] if user_plan == 'free' else insights
    for i, insight in enumerate(visible, 1):
        text = insight.get("text", "") if isinstance(insight, dict) else str(insight)
        Story.append(Paragraph(
            f"<b>{i}.</b> &nbsp; {text}", normal
        ))

    if user_plan == 'free' and len(insights) > 2:
        Story.append(Spacer(1, 12))
        Story.append(Paragraph(
            f"🔒 {len(insights) - 2} more insights available — Upgrade to Pro",
            locked
        ))

    Story.append(Spacer(1, 12))

    # ═══ 6. RECOMMENDATIONS ═══
    Story.append(_section_header("Strategic Recommendations", styles))
    recs = project.get('ai_recommendations', [])

    visible_recs = recs[:1] if user_plan == 'free' else recs
    for i, rec in enumerate(visible_recs, 1):
        Story.append(Paragraph(f"<b>→</b> &nbsp; {rec}", normal))

    if user_plan == 'free' and len(recs) > 1:
        Story.append(Spacer(1, 12))
        Story.append(Paragraph(
            f"🔒 {len(recs) - 1} more recommendations — Upgrade to Pro",
            locked
        ))

    # ═══ 7. BOARD Q&A ═══
    qa = project.get('ai_qa', [])
    if qa:
        Story.append(PageBreak())
        Story.append(_section_header("Board Q&A", styles))

        if user_plan == 'free':
            Story.append(Paragraph(
                f"🔒 {len(qa)} executive Q&A pairs — Upgrade to Pro",
                locked
            ))
        else:
            for item in qa:
                Story.append(Paragraph(
                    f"<b>Q:</b> {item.get('q', '')}", normal
                ))
                Story.append(Paragraph(
                    f"<b>A:</b> {item.get('a', '')}", 
                    ParagraphStyle('Answer', parent=normal, leftIndent=20, spaceAfter=14)
                ))

    # ── Build ──
    doc.build(Story)
    logger.info(f"✅ PDF exported: {output_path}")


# ╔════════════════════════════════════════════════════════════╗
# ║                  PPT EXPORT (python-pptx)                 ║
# ╚════════════════════════════════════════════════════════════╝

def _ppt_set_bg(slide, hex_color):
    """Set solid background color on a slide."""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = RGBColor.from_string(hex_color.lstrip('#'))


def _ppt_add_textbox(slide, left, top, width, height, text,
                      font_size=14, bold=False, color="ffffff", alignment=PP_ALIGN.LEFT):
    """Add a styled textbox to a slide."""
    txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = PptPt(font_size)
    p.font.bold = bold
    p.font.color.rgb = RGBColor.from_string(color.lstrip('#'))
    p.alignment = alignment
    return tf


def _ppt_add_footer(slide, slide_num):
    """Add slide number footer."""
    _ppt_add_textbox(
        slide, 0.5, 7.0, 9.0, 0.4,
        f"ExecSlate  |  Slide {slide_num}  |  CONFIDENTIAL",
        font_size=8, color="64748b", alignment=PP_ALIGN.CENTER
    )


def export_ppt_enhanced(project, output_path, user_plan="free"):
    """Generate consulting-grade dark-theme PowerPoint."""
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    currency = project.get('currency', '$')
    slide_num = 0

    # ═══ SLIDE 1: TITLE ═══
    slide_num += 1
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    _ppt_set_bg(slide, BRAND["navy"])

    # Accent bar
    shape = slide.shapes.add_shape(
        1, Inches(0), Inches(0), Inches(0.15), Inches(7.5)  # MSO_SHAPE.RECTANGLE
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = RGBColor.from_string(BRAND["accent"].lstrip('#'))
    shape.line.fill.background()

    _ppt_add_textbox(slide, 1.5, 1.0, 10, 0.5, "E X E C S L A T E",
                      font_size=16, color=BRAND["accent"])
    _ppt_add_textbox(slide, 1.5, 2.2, 10, 1.2,
                      project.get('report_title', 'Executive Performance Report'),
                      font_size=40, bold=True, color="ffffff")
    _ppt_add_textbox(slide, 1.5, 3.6, 10, 0.8, project.get('client', 'Client'),
                      font_size=28, color="94a3b8")
    _ppt_add_textbox(slide, 1.5, 4.6, 10, 0.5, project.get('period', ''),
                      font_size=16, color="64748b")
    _ppt_add_textbox(slide, 1.5, 5.8, 10, 0.5,
                      f"Generated: {datetime.now().strftime('%B %d, %Y')}",
                      font_size=12, color="475569")
    _ppt_add_textbox(slide, 1.5, 6.3, 10, 0.4, "CONFIDENTIAL",
                      font_size=10, bold=True, color="64748b")

    # ═══ SLIDE 2: EXECUTIVE SUMMARY ═══
    slide_num += 1
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _ppt_set_bg(slide, BRAND["dark"])

    _ppt_add_textbox(slide, 0.8, 0.4, 5, 0.6, "Executive Summary",
                      font_size=24, bold=True, color="ffffff")

    # Left: summary text
    summary = project.get("ai_summary", "No summary available.")
    tf = _ppt_add_textbox(slide, 0.8, 1.3, 6.5, 5.0, summary,
                           font_size=13, color="cbd5e1")
    tf.word_wrap = True

    # Right: KPI cards — Phase B: dynamic multi-KPI
    kpi_metrics = project.get('kpi_metrics', {})
    if kpi_metrics:
        sorted_kpis = sorted(kpi_metrics.items(), key=lambda x: x[1].get('priority', 99))
        kpis = []
        for col_name, kpi in sorted_kpis[:4]:  # Max 4 cards
            fmt = kpi.get('format', 'number')
            if fmt == 'currency':
                val_str = f"{currency}{kpi.get('total', 0):,.0f}"
            elif fmt == 'percent':
                val_str = f"{kpi.get('avg', 0):.1f}%"
            else:
                val_str = f"{kpi.get('total', 0):,.0f}"
            kpis.append((kpi.get('label', col_name), val_str))
    else:
        kpis = [
            ("Total Revenue", f"{currency}{project.get('total_revenue', 0):,.0f}"),
            ("Growth Rate", f"{project.get('growth_rate', 0):+.1f}%"),
            ("Top Market", project.get('top_region', 'N/A')),
            ("Data Points", str(project.get('row_count', 0))),
        ]

    y_start = 1.3
    for i, (label, value) in enumerate(kpis):
        card = slide.shapes.add_shape(
            1, Inches(8.0), Inches(y_start + i * 1.35), Inches(4.5), Inches(1.1)
        )
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor.from_string(BRAND["slate"].lstrip('#'))
        card.line.fill.background()

        _ppt_add_textbox(slide, 8.3, y_start + i * 1.35 + 0.1, 4, 0.3,
                          label, font_size=10, color="94a3b8")
        _ppt_add_textbox(slide, 8.3, y_start + i * 1.35 + 0.45, 4, 0.4,
                          value, font_size=20, bold=True, color="ffffff")

    # ═══ SLIDE 2.5: WORKING THEORY & HYPOTHESES (NEW) ═══
    working_theory = project.get("working_theory")
    hypotheses = project.get("hypotheses", [])
    
    if working_theory or hypotheses:
        slide_num += 1
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _ppt_set_bg(slide, BRAND["dark"])
        _ppt_add_textbox(slide, 0.8, 0.4, 10, 0.6, "Strategic Context & Hypotheses",
                          font_size=24, bold=True, color="ffffff")
        
        y_offset = 1.3
        if working_theory:
            _ppt_add_textbox(slide, 0.8, y_offset, 11, 0.4, "Consultant's Working Theory", font_size=16, bold=True, color=BRAND["accent"])
            _ppt_add_textbox(slide, 0.8, y_offset + 0.5, 11, 1.5, working_theory, font_size=12, color="cbd5e1")
            y_offset += 2.2
            
        if hypotheses:
            _ppt_add_textbox(slide, 0.8, y_offset, 11, 0.4, "Testing Hypotheses", font_size=16, bold=True, color="ffffff")
            h_text = ""
            for h in hypotheses[:3]: # Show top 3
                h_text += f"• {h.get('id')}: {h.get('statement')}\n"
            _ppt_add_textbox(slide, 0.8, y_offset + 0.5, 11, 2.0, h_text.strip(), font_size=12, color="94a3b8")
            
        _ppt_add_footer(slide, slide_num)

    # ═══ SLIDE 3: CHARTS ═══
    for chart_key, chart_label in [('revenue_chart', 'Revenue Trend Analysis'),
                                     ('region_chart', 'Regional Distribution')]:
        if project.get(chart_key):
            chart_path = BASE_DIR / project[chart_key].lstrip('/')
            if chart_path.exists():
                slide_num += 1
                slide = prs.slides.add_slide(prs.slide_layouts[6])
                _ppt_set_bg(slide, BRAND["dark"])
                _ppt_add_textbox(slide, 0.8, 0.4, 10, 0.6, chart_label,
                                  font_size=24, bold=True, color="ffffff")
                slide.shapes.add_picture(str(chart_path),
                                          Inches(1.5), Inches(1.5),
                                          width=Inches(10.3))
                _ppt_add_footer(slide, slide_num)

    # ═══ SLIDE 4: SEGMENTATION ═══
    comp = project.get('comprehensive_analysis')
    if comp and comp.get('segmentation'):
        slide_num += 1
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        _ppt_set_bg(slide, BRAND["dark"])
        _ppt_add_textbox(slide, 0.8, 0.4, 10, 0.6, "Market Segmentation",
                          font_size=24, bold=True, color="ffffff")

        seg_text = ""
        seg = comp['segmentation']
        for metric, dims in seg.items():
            seg_text += f"— {metric.replace('_', ' ').title()} —\n"
            for dim_name, dim_data in dims.items():
                top = dim_data.get('top_performer', {})
                bot = dim_data.get('bottom_performer', {})
                if top:
                    seg_text += f"▲ Top {dim_name}: {top.get('name')} — {ea.format_currency(top.get('value', 0), currency)} ({top.get('pct', 0):.1f}%)\n"
                if bot:
                    seg_text += f"▼ Bottom {dim_name}: {bot.get('name')} — {ea.format_currency(bot.get('value', 0), currency)} ({bot.get('pct', 0):.1f}%)\n"
                seg_text += "\n"

        _ppt_add_textbox(slide, 0.8, 1.3, 11.5, 5.0, seg_text.strip(),
                          font_size=14, color="e2e8f0")
        _ppt_add_footer(slide, slide_num)

    # ═══ SLIDE 5: INSIGHTS ═══
    slide_num += 1
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _ppt_set_bg(slide, BRAND["dark"])
    _ppt_add_textbox(slide, 0.8, 0.4, 10, 0.6, "Strategic Insights",
                      font_size=24, bold=True, color="ffffff")

    insights = project.get('ai_insights', [])
    visible = insights[:2] if user_plan == 'free' else insights[:6]
    text = ""
    for i, ins in enumerate(visible, 1):
        t = ins.get('text', '') if isinstance(ins, dict) else str(ins)
        text += f"{i}. {t}\n\n"

    if user_plan == 'free' and len(insights) > 2:
        text += f"🔒 {len(insights) - 2} more insights — Upgrade to Pro"

    _ppt_add_textbox(slide, 0.8, 1.3, 11.5, 5.5, text.strip(),
                      font_size=13, color="e2e8f0")
    _ppt_add_footer(slide, slide_num)

    # ═══ SLIDE 6: RECOMMENDATIONS ═══
    slide_num += 1
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    _ppt_set_bg(slide, BRAND["dark"])
    _ppt_add_textbox(slide, 0.8, 0.4, 10, 0.6, "Strategic Recommendations",
                      font_size=24, bold=True, color="ffffff")

    recs = project.get('ai_recommendations', [])
    visible_recs = recs[:1] if user_plan == 'free' else recs
    text = ""
    for i, rec in enumerate(visible_recs, 1):
        text += f"→ {rec}\n\n"

    if user_plan == 'free' and len(recs) > 1:
        text += f"\n🔒 {len(recs) - 1} more recommendations — Upgrade to Pro"

    _ppt_add_textbox(slide, 0.8, 1.3, 11.5, 5.5, text.strip(),
                      font_size=14, color="e2e8f0")
    _ppt_add_footer(slide, slide_num)

    prs.save(output_path)
    logger.info(f"✅ PPT exported: {output_path}")


# ╔════════════════════════════════════════════════════════════╗
# ║                  DOCX EXPORT (python-docx)                ║
# ╚════════════════════════════════════════════════════════════╝

def export_docx_enhanced(project, output_path, user_plan="free"):
    """Generate consulting-grade Word document."""
    from docx import Document
    from docx.shared import Inches as DocxInches, Pt as DocxPt, RGBColor as DocxRGB
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    currency = project.get('currency', '$')

    def sanitize(text):
        if not text:
            return ""
        return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(text))

    doc = Document()

    # ── Style tweaks ──
    style = doc.styles['Normal']
    style.font.name = 'Calibri'
    style.font.size = DocxPt(11)

    for level in range(1, 4):
        hs = doc.styles[f'Heading {level}']
        hs.font.color.rgb = DocxRGB(0x0f, 0x17, 0x2a)
        hs.font.name = 'Calibri'

    # ── Watermark for free/demo ──
    if user_plan in ('free', 'demo'):
        try:
            from lxml import etree
            vml_ns = "urn:schemas-microsoft-com:vml"
            office_ns = "urn:schemas-microsoft-com:office:office"

            section = doc.sections[0]
            header = section.header
            header.is_linked_to_previous = False
            p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
            r = p.add_run()
            pict = OxmlElement('w:pict')

            wm_label = 'ExecSlate Demo' if user_plan == 'demo' else 'ExecSlate Trial'
            positions = [
                ("-150pt", "-300pt"), ("100pt", "-300pt"), ("350pt", "-300pt"),
                ("-100pt", "-100pt"), ("150pt", "-100pt"), ("400pt", "-100pt"),
                ("-150pt", "100pt"), ("100pt", "100pt"), ("350pt", "100pt"),
                ("-100pt", "300pt"), ("150pt", "300pt"), ("400pt", "300pt"),
            ]

            shapes_xml = f'''
            <v:shapetype xmlns:v="{vml_ns}" xmlns:o="{office_ns}"
                id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800"
                path="m@7,l@8,m@5,21600l@6,21600e">
                <v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/><v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/><v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/><v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>
                <v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" o:connectangles="270,180,90,0"/>
                <v:textpath on="t" fitshape="t"/>
                <v:handles><v:h position="#0,bottomRight" xrange="6629,14971"/></v:handles>
                <o:lock v:ext="edit" text="t" shapetype="t"/>
            </v:shapetype>
            '''
            for idx, (left, top) in enumerate(positions):
                shapes_xml += f'''
                <v:shape xmlns:v="{vml_ns}" xmlns:o="{office_ns}"
                    id="WM{idx}" o:spid="_x0000_s{2049+idx}" type="#_x0000_t136"
                    style="position:absolute;margin-left:{left};margin-top:{top};width:180pt;height:40pt;rotation:315;z-index:-251658752;mso-position-horizontal-relative:margin;mso-position-vertical-relative:margin"
                    o:allowincell="f" fillcolor="#CCCCCC" stroked="f">
                    <v:fill opacity=".3"/>
                    <v:textpath style="font-family:&quot;Arial&quot;;font-size:1pt" string="{wm_label}"/>
                </v:shape>
                '''
            root = etree.fromstring(f'<root xmlns:v="{vml_ns}" xmlns:o="{office_ns}">{shapes_xml}</root>')
            for elem in root:
                pict.append(elem)
            r._r.append(pict)
        except Exception as e:
            logger.warning(f"DOCX watermark failed: {e}")

    # ── Footer with page numbers ──
    try:
        section = doc.sections[0]
        footer = section.footer
        footer.is_linked_to_previous = False
        fp = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = fp.add_run("ExecSlate  |  CONFIDENTIAL  |  Page ")
        run.font.size = DocxPt(8)
        run.font.color.rgb = DocxRGB(0x64, 0x74, 0x8b)
        # Page number field
        fld = OxmlElement('w:fldSimple')
        fld.set(qn('w:instr'), 'PAGE')
        fld_run = OxmlElement('w:r')
        fld_text = OxmlElement('w:t')
        fld_text.text = "0"
        fld_run.append(fld_text)
        fld.append(fld_run)
        fp._p.append(fld)
    except Exception as e:
        logger.warning(f"DOCX footer failed: {e}")

    # ═══ COVER PAGE ═══
    doc.add_paragraph()
    doc.add_paragraph()
    doc.add_paragraph()

    title = doc.add_heading(project.get('report_title', 'Executive Performance Report'), 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()

    for line in [
        f'Client: {sanitize(project.get("client", ""))}',
        f'Period: {sanitize(project.get("period", ""))}',
        f'Generated: {datetime.now().strftime("%B %d, %Y")}',
        f'Analysis: {"AI-Enhanced" if project.get("report_type") == "ai" else "Statistical"}',
    ]:
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph()
    conf = doc.add_paragraph("━━━  CONFIDENTIAL  ━━━")
    conf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for run in conf.runs:
        run.font.size = DocxPt(9)
        run.font.color.rgb = DocxRGB(0x64, 0x74, 0x8b)

    doc.add_page_break()

    # ═══ EXECUTIVE SUMMARY ═══
    # --- Working Theory (NEW) ---
    working_theory = project.get("working_theory")
    if working_theory:
        doc.add_heading("Consultant's Working Theory", 2)
        p = doc.add_paragraph(sanitize(working_theory))
        p.style.font.italic = True
        doc.add_paragraph()

    doc.add_heading('Executive Summary', 1)
    doc.add_paragraph(sanitize(project.get("ai_summary", "No summary available.")))
    
    # --- Hypotheses (NEW) ---
    hypotheses = project.get("hypotheses", [])
    if hypotheses:
        doc.add_heading('Strategic Hypotheses', 2)
        for h in hypotheses:
            doc.add_paragraph(f"{h.get('id')}: {sanitize(h.get('statement'))}", style='List Bullet')
    
    doc.add_page_break()

    # ═══ KEY METRICS ═══
    doc.add_heading('Key Performance Metrics', 1)

    # Phase B: dynamic multi-KPI table
    kpi_metrics = project.get('kpi_metrics', {})
    if kpi_metrics:
        metrics = [('Metric', 'Value', 'Growth')]
        sorted_kpis = sorted(kpi_metrics.items(), key=lambda x: x[1].get('priority', 99))
        for col_name, kpi in sorted_kpis:
            fmt = kpi.get('format', 'number')
            if fmt == 'currency':
                val_str = f"{currency}{kpi.get('total', 0):,.2f}"
            elif fmt == 'percent':
                val_str = f"{kpi.get('avg', 0):.1f}%"
            else:
                val_str = f"{kpi.get('total', 0):,.0f}"
            growth_str = f"{kpi.get('growth', 0):+.1f}%"
            metrics.append((kpi.get('label', col_name), val_str, growth_str))
        # Append common metadata
        metrics.extend([
            ('Top Market', sanitize(project.get('top_region', 'N/A')), ''),
            ('Data Points', str(project.get('row_count', 0)), ''),
            ('Confidence', f"{project.get('confidence', 0)}%", ''),
        ])
        table = doc.add_table(rows=len(metrics), cols=3)
    else:
        # Fallback: revenue-only
        metrics = [
            ('Metric', 'Value', ''),
            ('Total Revenue', f"{currency}{project.get('total_revenue', 0):,.2f}", ''),
            ('Average Revenue', f"{currency}{project.get('avg_revenue', 0):,.2f}", ''),
            ('Growth Rate', f"{project.get('growth_rate', 0):+.1f}%", ''),
            ('Trend Direction', sanitize(project.get('trend', 'N/A')), ''),
            ('Top Market', sanitize(project.get('top_region', 'N/A')), ''),
            ('Data Points', str(project.get('row_count', 0)), ''),
            ('Confidence', f"{project.get('confidence', 0)}%", ''),
        ]
        table = doc.add_table(rows=len(metrics), cols=2)

    table.style = 'Table Grid'
    for i, row_data in enumerate(metrics):
        for j in range(len(table.columns)):
            if j < len(row_data):
                table.rows[i].cells[j].text = row_data[j]
        if i == 0:  # Header row bold
            for cell in table.rows[i].cells:
                for run in cell.paragraphs[0].runs:
                    run.bold = True

    doc.add_paragraph()

    # ═══ CHARTS ═══
    for chart_key, chart_label in [('revenue_chart', 'Revenue Trend'), ('region_chart', 'Regional Distribution')]:
        if project.get(chart_key):
            doc.add_heading(chart_label, 2)
            if chart_key == 'region_chart' and user_plan == 'free':
                doc.add_paragraph('[Regional chart available in Pro version]')
            else:
                try:
                    p = BASE_DIR / project[chart_key].lstrip('/')
                    if p.exists() and p.stat().st_size > 0:
                        doc.add_picture(str(p), width=DocxInches(6))
                    else:
                        doc.add_paragraph('[Chart unavailable]')
                except Exception as e:
                    logger.error(f"DOCX chart failed: {e}")
                    doc.add_paragraph('[Chart unavailable]')

    doc.add_page_break()

    # ═══ INSIGHTS ═══
    doc.add_heading('Strategic Insights', 1)
    insights = project.get('ai_insights', [])

    visible = insights[:2] if user_plan == 'free' else insights
    for i, insight in enumerate(visible, 1):
        text = insight.get("text", "") if isinstance(insight, dict) else str(insight)
        doc.add_paragraph(f"{i}. {sanitize(text)}")

    if user_plan == 'free' and len(insights) > 2:
        _docx_locked_section(doc, f"{len(insights) - 2} more strategic insights")

    # ═══ RECOMMENDATIONS ═══
    doc.add_paragraph()
    doc.add_heading('Strategic Recommendations', 1)
    recs = project.get('ai_recommendations', [])

    visible_recs = recs[:1] if user_plan == 'free' else recs
    for i, rec in enumerate(visible_recs, 1):
        doc.add_paragraph(f"{i}. {sanitize(rec)}")

    if user_plan == 'free' and len(recs) > 1:
        _docx_locked_section(doc, f"{len(recs) - 1} more recommendations")

    # ═══ Q&A ═══
    qa = project.get('ai_qa', [])
    if qa:
        doc.add_page_break()
        doc.add_heading('Board Q&A', 1)
        if user_plan == 'free':
            _docx_locked_section(doc, f"{len(qa)} executive Q&A pairs")
        else:
            for item in qa:
                qp = doc.add_paragraph()
                qr = qp.add_run(f"Q: {sanitize(item.get('q', ''))}")
                qr.bold = True
                doc.add_paragraph(f"A: {sanitize(item.get('a', ''))}")
                doc.add_paragraph()

    # ── Save ──
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)
    logger.info(f"✅ DOCX exported: {output_path}")


def _docx_locked_section(doc, items_desc):
    """Add a locked content placeholder in DOCX."""
    from docx.shared import Pt as DocxPt, RGBColor as DocxRGB
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    lines = [
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "🔒 PREMIUM CONTENT LOCKED",
        "",
        f"This section contains {items_desc}",
        "",
        "Upgrade to ExecSlate Pro to unlock",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ]
    for line in lines:
        p = doc.add_paragraph(line)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in p.runs:
            run.font.size = DocxPt(9)
            run.font.color.rgb = DocxRGB(0x94, 0xa3, 0xb8)
            if "PREMIUM" in line or "━" in line:
                run.bold = True
