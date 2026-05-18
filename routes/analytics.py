# ==================== ANALYTICS ROUTES ====================
# Analytics tab is fully independent from the Report/Project upload pipeline.
# Users upload data here for exploration; Report tab is for final deliverable generation.

import io
import base64
import logging
import numpy as np
import seaborn as sns
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(tags=["analytics"])
logger = logging.getLogger("ExecSlate")

MAX_ANALYTICS_FILE_SIZE = 5_000_000  # 5 MB


# ── Chart helpers (self-contained, return base64 PNG) ──────────────────────────

def _b64_chart(fig) -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def _trend_chart(values: list, currency: str, col_name: str) -> str:
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='white')
    x = list(range(1, len(values) + 1))
    palette = ['#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd']
    bar_colors = [palette[i % len(palette)] for i in range(len(values))]
    ax.bar(x, values, color=bar_colors, width=0.7, edgecolor='#1e293b', linewidth=1.5, alpha=0.9)
    if len(x) > 1:
        z = np.polyfit(x, values, 1)
        ax.plot(x, np.poly1d(z)(x), '--', color='#059669', linewidth=2, alpha=0.8, label='Trend')
        ax.legend(fontsize=10, framealpha=0.9)
    ax.set_title(f"{col_name.replace('_', ' ').title()} — Trend Analysis",
                 fontsize=13, fontweight='bold', color='#0f172a', pad=15)
    ax.set_xlabel("Period", fontsize=11, color='#334155')
    ax.set_ylabel(f"{col_name.replace('_', ' ').title()}", fontsize=11, color='#334155')
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{currency}{v:,.0f}"))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cbd5e1')
    ax.spines['bottom'].set_color('#cbd5e1')
    ax.grid(True, axis='y', alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return _b64_chart(fig)


def _region_chart(labels: list, values: list, currency: str) -> str:
    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.55)), facecolor='white')
    palette = sns.color_palette("Blues_d", len(labels))
    bars = ax.barh(labels, values, color=palette, edgecolor='#1e293b', linewidth=1, alpha=0.9)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                f"{currency}{val:,.0f}", va='center', fontsize=9, color='#1e293b')
    ax.set_title("Segment Distribution", fontsize=13, fontweight='bold', color='#0f172a', pad=15)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{currency}{v:,.0f}"))
    ax.grid(True, axis='x', alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return _b64_chart(fig)


# ── Pydantic model for draft saving ───────────────────────────────────────────

class DraftPayload(BaseModel):
    name: Optional[str] = "Draft"
    kpi_snapshot: Optional[List[str]] = []
    selected_insights: Optional[List[str]] = []
    notes: Optional[str] = ""


# ── Route setup ────────────────────────────────────────────────────────────────

def setup(app_module):
    db = app_module.db
    templates = app_module.templates
    require_user = app_module.require_user
    ea = app_module.ea
    ai_providers = app_module.ai_providers

    # ── Analytics workspace page ──────────────────────────────────────────────

    @router.get("/analytics/{pid}")
    def analytics_workspace(pid: int, request: Request, user=Depends(require_user)):
        if "id" in user:
            project = db.get_project(pid, user["id"])
        else:
            from app import projects
            project = next(
                (x for x in projects if x.get("id") == pid and x.get("user_email") == user["email"]),
                None,
            )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        session = None
        drafts = []
        if "id" in user:
            try:
                session = db.get_latest_analytics_session(pid)
                drafts = db.get_analytics_drafts(pid)
            except Exception:
                pass

        return templates.TemplateResponse(
            request=request,
            name="analytics.html",
            context={
                "request": request,
                "user": user,
                "project": project,
                "session": session,
                "drafts": drafts,
            },
        )

    # ── Independent analytics file upload ─────────────────────────────────────

    @router.post("/analytics/{pid}/upload")
    async def analytics_upload(
        pid: int,
        request: Request,
        file: UploadFile = File(...),
        currency: str = Form("$"),
        user=Depends(require_user),
    ):
        if "id" not in user:
            raise HTTPException(status_code=403, detail="Demo users cannot upload in Analytics. Please register.")

        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # ── Read & validate file ──
        contents = await file.read()
        if len(contents) > MAX_ANALYTICS_FILE_SIZE:
            raise HTTPException(status_code=400, detail="File too large (max 5MB)")

        fname = file.filename or ""
        try:
            if fname.endswith(('.xlsx', '.xls')):
                import pandas as pd
                df = pd.read_excel(io.BytesIO(contents))
            else:
                import pandas as pd
                df = pd.read_csv(io.BytesIO(contents))
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

        if df.empty or len(df.columns) == 0:
            raise HTTPException(status_code=400, detail="File appears to be empty.")

        # ── Detect columns ──
        numeric_cols = df.select_dtypes(include='number').columns.tolist()
        text_cols = df.select_dtypes(include='object').columns.tolist()

        if not numeric_cols:
            raise HTTPException(status_code=400, detail="No numeric columns found. Please upload a file with numeric data.")

        # ── Run comprehensive analysis ──
        try:
            analysis = ea.analyze_comprehensive(df, currency)
        except Exception as e:
            logger.warning(f"Enhanced analysis failed: {e}")
            analysis = {}

        # ── Build KPI metrics ──
        kpi_metrics = {}
        for col in numeric_cols[:12]:
            vals = df[col].dropna()
            if len(vals) == 0:
                continue
            col_lower = col.lower()
            is_currency = any(k in col_lower for k in ['revenue', 'sales', 'income', 'profit', 'cost', 'price', 'amount', 'fee', 'spend'])
            is_pct = any(k in col_lower for k in ['margin', 'rate', 'ratio', 'pct', 'percent', 'growth'])
            is_down_good = any(k in col_lower for k in ['cost', 'expense', 'churn', 'loss', 'return', 'refund'])
            kpi_metrics[col] = {
                "label": col.replace('_', ' ').title(),
                "value": float(vals.sum()),
                "avg": float(vals.mean()),
                "format": "percent" if is_pct else ("currency" if is_currency else "number"),
                "direction": "down_good" if is_down_good else "up_good",
            }

        # ── Revenue/trend series (primary numeric column) ──
        primary_col = numeric_cols[0]
        revenue_series = df[primary_col].dropna().tolist()[:30]

        # ── Regional / segmentation data ──
        region_labels, region_values = [], []
        if text_cols:
            region_col = text_cols[0]
            try:
                grouped = (
                    df.groupby(region_col)[primary_col]
                    .sum()
                    .sort_values(ascending=False)
                    .head(8)
                )
                region_labels = [str(l) for l in grouped.index.tolist()]
                region_values = [float(v) for v in grouped.values.tolist()]
            except Exception:
                pass

        # ── Growth rate & trend ──
        growth_rate = 0.0
        trend = "Stable"
        if len(revenue_series) >= 2:
            first, last = revenue_series[0], revenue_series[-1]
            if first and first != 0:
                growth_rate = round(((last - first) / abs(first)) * 100, 2)
            trend = "Increasing" if growth_rate > 2 else ("Decreasing" if growth_rate < -2 else "Stable")

        # ── Confidence score (simple data quality proxy) ──
        total_cells = df.shape[0] * df.shape[1]
        missing = df.isnull().sum().sum()
        confidence = max(10, int(100 - (missing / max(total_cells, 1)) * 100))

        # ── Generate charts ──
        trend_b64 = None
        region_b64 = None
        try:
            if len(revenue_series) >= 2:
                trend_b64 = _trend_chart(revenue_series, currency, primary_col)
        except Exception as e:
            logger.warning(f"Trend chart failed: {e}")

        try:
            if region_labels:
                region_b64 = _region_chart(region_labels, region_values, currency)
        except Exception as e:
            logger.warning(f"Region chart failed: {e}")

        # ── AI insights (if available) ──
        ai_insights = []
        try:
            if ai_providers.is_ai_available():
                top_kpis = list(kpi_metrics.items())[:5]
                kpi_text = "\n".join(
                    f"- {v['label']}: {currency}{v['value']:,.0f}" for k, v in top_kpis
                )
                prompt = f"""You are a business analyst. Analyse this dataset and provide 6 concise, consulting-grade insights.

Dataset: {len(df)} rows, {len(numeric_cols)} numeric columns, {len(text_cols)} text columns.
Primary metric: {primary_col} | Trend: {trend} | Growth: {growth_rate:.1f}%
Top KPIs:
{kpi_text}

Return exactly 6 bullet insights, one per line, starting with •. No markdown headers."""

                raw = ai_providers.get_ai_response(prompt, max_tokens=600)
                if raw:
                    lines = [l.strip().lstrip('•-').strip() for l in raw.split('\n') if l.strip() and len(l.strip()) > 15]
                    ai_insights = lines[:6]
        except Exception as e:
            logger.warning(f"AI insights failed: {e}")

        # Fallback statistical insights
        if not ai_insights:
            ai_insights = [
                f"Primary metric '{primary_col}' shows a {trend.lower()} trend with {abs(growth_rate):.1f}% {'growth' if growth_rate >= 0 else 'decline'} over the dataset period.",
                f"Dataset contains {len(df):,} records across {len(numeric_cols)} numeric and {len(text_cols)} categorical dimensions.",
                f"Data completeness score: {confidence}% — {'high quality data suitable for reliable analysis.' if confidence >= 80 else 'some missing values detected, interpret results with caution.'}",
                f"{'Top segment' if region_labels else 'Primary metric'}: {region_labels[0] if region_labels else primary_col} accounts for the largest share of total {primary_col}." if region_labels else f"No categorical segmentation detected — analysis is based on {len(df)} data points.",
                f"Average {primary_col.replace('_', ' ')}: {currency}{float(df[primary_col].mean()):,.0f} across all periods.",
                f"Identified {len(numeric_cols)} KPI dimensions for analysis: {', '.join(c.replace('_', ' ') for c in numeric_cols[:4])}{'...' if len(numeric_cols) > 4 else ''}.",
            ]

        # ── Column summary for display ──
        column_summary = {}
        for col in df.columns[:20]:
            dtype = str(df[col].dtype)
            column_summary[col] = "numeric" if "int" in dtype or "float" in dtype else "text"

        # ── Save session ──
        try:
            db.create_analytics_session(
                project_id=pid,
                currency=currency,
                row_count=len(df),
                confidence=confidence,
                trend=trend,
                growth_rate=growth_rate,
                primary_col=primary_col,
                revenue_chart_b64=trend_b64,
                region_chart_b64=region_b64,
                kpi_metrics=kpi_metrics,
                ai_insights=ai_insights,
                column_summary=column_summary,
            )
        except Exception as e:
            logger.error(f"Failed to save analytics session: {e}")
            raise HTTPException(status_code=500, detail="Analysis complete but could not save session.")

        return RedirectResponse(f"/analytics/{pid}", status_code=303)

    # ── Save analytics draft ──────────────────────────────────────────────────

    @router.post("/api/analytics/{pid}/draft")
    async def save_analytics_draft(pid: int, payload: DraftPayload, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if "id" not in user:
            return JSONResponse({"ok": False, "error": "Demo users cannot save drafts"}, status_code=403)

        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            draft_id = db.create_analytics_draft(
                project_id=pid,
                name=payload.name or "Draft",
                kpi_snapshot=payload.kpi_snapshot or [],
                selected_insights=payload.selected_insights or [],
                notes=payload.notes or "",
            )
            return {"ok": True, "draft_id": draft_id}
        except Exception as e:
            logger.error(f"Failed to save draft: {e}")
            raise HTTPException(status_code=500, detail="Could not save draft")

    # ── List saved drafts ────────────────────────────────────────────────────

    @router.get("/api/analytics/{pid}/drafts")
    def list_analytics_drafts(pid: int, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if "id" not in user:
            return {"drafts": []}

        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return {"drafts": db.get_analytics_drafts(pid)}
