"""
ExecSlate — Shared Analytics Engine

Pure analysis logic with no auth/session/routing concerns, so both the
authenticated Analytics workspace and the anonymous /try funnel run the
exact same pipeline.

Public API:
    read_and_stack_files(files) -> (DataFrame | None, error_message | None)
    analyze_dataframe(df, currency) -> (result_dict | None, error_message | None)
"""

import io
import base64
import logging

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

import ai_providers
import enhanced_analysis as ea

logger = logging.getLogger("ExecSlate")

MAX_UPLOAD_SIZE = 5_000_000  # 5 MB total across all files


# ── Chart helpers (return base64 PNG) ─────────────────────────────────────────

def _b64_chart(fig) -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode('utf-8')


def trend_chart(values: list, currency: str, col_name: str, x_labels: list = None) -> str:
    """Time-series chart: bars + linear trend line over an ordered axis."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='white')
    x = list(range(1, len(values) + 1))
    palette = ['#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd']
    bar_colors = [palette[i % len(palette)] for i in range(len(values))]
    ax.bar(x, values, color=bar_colors, width=0.7, edgecolor='#1e293b', linewidth=1.5, alpha=0.9)
    if len(x) > 1:
        z = np.polyfit(x, values, 1)
        ax.plot(x, np.poly1d(z)(x), '--', color='#059669', linewidth=2, alpha=0.8, label='Trend')
        ax.legend(fontsize=10, framealpha=0.9)
    ax.set_title(f"{col_name.replace('_', ' ').title()} — Trend Over Time",
                 fontsize=13, fontweight='bold', color='#0f172a', pad=15)
    if x_labels:
        ax.set_xticks(x)
        ax.set_xticklabels([str(l)[:12] for l in x_labels], rotation=35, ha='right', fontsize=9)
        ax.set_xlabel("", fontsize=11, color='#334155')
    else:
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


def region_chart(labels: list, values: list, currency: str, title: str = "Segment Breakdown") -> str:
    """Ranking chart: horizontal bars of a metric grouped by a category."""
    fig, ax = plt.subplots(figsize=(10, max(4, len(labels) * 0.55)), facecolor='white')
    palette = sns.color_palette("Blues_d", len(labels))
    bars = ax.barh(labels, values, color=palette, edgecolor='#1e293b', linewidth=1, alpha=0.9)
    for bar, val in zip(bars, values):
        ax.text(bar.get_width() * 1.01, bar.get_y() + bar.get_height() / 2,
                f"{currency}{val:,.0f}", va='center', fontsize=9, color='#1e293b')
    ax.set_title(title, fontsize=13, fontweight='bold', color='#0f172a', pad=15)
    ax.invert_yaxis()
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{currency}{v:,.0f}"))
    ax.grid(True, axis='x', alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return _b64_chart(fig)


def distribution_chart(values: list, currency: str, col_name: str) -> str:
    """Histogram for data that is neither a time series nor segment-shaped."""
    fig, ax = plt.subplots(figsize=(10, 5), facecolor='white')
    n_bins = min(30, max(8, int(len(values) ** 0.5)))
    ax.hist(values, bins=n_bins, color='#2563eb', edgecolor='#1e293b', linewidth=1, alpha=0.85)
    mean_v = float(np.mean(values)) if values else 0
    ax.axvline(mean_v, color='#059669', linestyle='--', linewidth=2,
               label=f"Mean {currency}{mean_v:,.0f}")
    ax.legend(fontsize=10, framealpha=0.9)
    ax.set_title(f"{col_name.replace('_', ' ').title()} — Distribution",
                 fontsize=13, fontweight='bold', color='#0f172a', pad=15)
    ax.set_xlabel(f"{col_name.replace('_', ' ').title()}", fontsize=11, color='#334155')
    ax.set_ylabel("Count", fontsize=11, color='#334155')
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{currency}{v:,.0f}"))
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.grid(True, axis='y', alpha=0.18, linewidth=0.7)
    ax.set_axisbelow(True)
    plt.tight_layout()
    return _b64_chart(fig)


def detect_time_column(df, text_cols, numeric_cols):
    """Return the name of a usable time/period column, or None."""
    import pandas as pd
    time_kw = ('date', 'month', 'year', 'quarter', 'qtr', 'week',
               'period', 'time', 'fy', 'day')
    candidates = [c for c in df.columns if any(k in str(c).lower() for k in time_kw)]
    for c in candidates:
        ser = df[c].dropna()
        if ser.empty:
            continue
        if str(ser.dtype).startswith('datetime'):
            return c
        try:
            parsed = pd.to_datetime(ser.head(20), errors='coerce')
            if parsed.notna().mean() >= 0.7:
                return c
        except Exception:
            pass
        if c in numeric_cols:
            vals = ser.astype(float)
            if vals.between(1900, 2100).mean() >= 0.7 and ser.nunique() >= 2:
                return c
        if c in text_cols and 2 <= ser.nunique() <= 24:
            return c
    return None


# ── File ingestion ────────────────────────────────────────────────────────────

def read_and_stack_files(files):
    """
    Read uploaded files IN ORDER and stack them into a single DataFrame.

    Args:
        files: list of (filename, bytes) tuples, in the user's chosen order.

    Returns:
        (DataFrame, None) on success, or (None, error_message) on failure.
    """
    import pandas as pd

    if not files:
        return None, "No files uploaded. Please choose at least one file."

    dfs = []
    total_size = 0
    reference_cols = None

    for idx, (fname, contents) in enumerate(files):
        total_size += len(contents)
        if total_size > MAX_UPLOAD_SIZE:
            return None, "Combined file size too large (5MB total maximum). Remove a file or upload smaller files."

        fname = fname or f"file {idx + 1}"
        try:
            if str(fname).lower().endswith(('.xlsx', '.xls')):
                fdf = pd.read_excel(io.BytesIO(contents))
            else:
                fdf = pd.read_csv(io.BytesIO(contents))
        except Exception as e:
            return None, f"Could not read '{fname}': {e}"

        if fdf.empty or len(fdf.columns) == 0:
            return None, f"'{fname}' appears to be empty."

        cols = list(fdf.columns)
        if reference_cols is None:
            reference_cols = cols
        elif set(cols) != set(reference_cols):
            return None, (
                f"Column mismatch in '{fname}'. To combine files in sequence, every file must have "
                f"the same column headers as the first file. Expected columns: "
                f"{', '.join(map(str, reference_cols))}."
            )
        fdf = fdf[reference_cols]
        dfs.append(fdf)

    df = pd.concat(dfs, ignore_index=True)
    if df.empty or len(df.columns) == 0:
        return None, "The combined dataset is empty after reading the files."

    return df, None


# ── Core analysis ─────────────────────────────────────────────────────────────

def analyze_dataframe(df, currency="$", use_ai=True):
    """
    Run the full ExecSlate analysis pipeline on a DataFrame.

    Returns:
        (result_dict, None) on success, or (None, error_message) on failure.

    result_dict keys match what AnalyticsSession stores, plus 'chart_strategy'.
    """
    import pandas as pd

    numeric_cols = df.select_dtypes(include='number').columns.tolist()
    text_cols = df.select_dtypes(include='object').columns.tolist()

    if not numeric_cols:
        return None, "No numeric columns found. Please upload a file that contains at least one numeric column."

    try:
        ea.analyze_comprehensive(df, currency)
    except Exception as e:
        logger.warning(f"Enhanced analysis failed: {e}")

    # ── KPI metrics ──
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

    primary_col = numeric_cols[0]
    time_col = detect_time_column(df, text_cols, numeric_cols)

    cat_col = None
    for c in text_cols:
        try:
            nun = df[c].nunique(dropna=True)
        except Exception:
            continue
        if 2 <= nun <= 50 and c != time_col:
            cat_col = c
            break

    region_labels, region_values = [], []
    trend_b64 = None
    region_b64 = None
    growth_rate = 0.0
    trend = "Stable"
    chart_strategy = "distribution"

    if cat_col:
        try:
            grouped = df.groupby(cat_col)[primary_col].sum().sort_values(ascending=False).head(8)
            region_labels = [str(l) for l in grouped.index.tolist()]
            region_values = [float(v) for v in grouped.values.tolist()]
        except Exception:
            pass

    seg_title = (f"{primary_col.replace('_', ' ').title()} by "
                 f"{cat_col.replace('_', ' ').title()}") if cat_col else "Segment Breakdown"

    if time_col:
        chart_strategy = "time-series"
        try:
            tdf = df[[time_col, primary_col]].dropna()
            try:
                order = pd.to_datetime(tdf[time_col], errors='coerce')
                tdf = (tdf.assign(_o=order).sort_values('_o')
                       if order.notna().mean() >= 0.7 else tdf.sort_values(time_col))
            except Exception:
                tdf = tdf.sort_values(time_col)
            agg = tdf.groupby(tdf[time_col], sort=False)[primary_col].sum()
            series = [float(v) for v in agg.values.tolist()][:60]
            labels = [str(l) for l in agg.index.tolist()][:60]
            if len(series) >= 2:
                first, last = series[0], series[-1]
                if first and first != 0:
                    growth_rate = round(((last - first) / abs(first)) * 100, 2)
                trend = ("Increasing" if growth_rate > 2
                         else ("Decreasing" if growth_rate < -2 else "Stable"))
                trend_b64 = trend_chart(series, currency, primary_col, x_labels=labels)
        except Exception as e:
            logger.warning(f"Trend chart failed: {e}")
        if region_labels:
            try:
                region_b64 = region_chart(region_labels, region_values, currency, title=seg_title)
            except Exception as e:
                logger.warning(f"Segment chart failed: {e}")

    elif cat_col and region_labels:
        chart_strategy = "categorical"
        trend = "Categorical"
        try:
            trend_b64 = region_chart(region_labels, region_values, currency, title=seg_title)
        except Exception as e:
            logger.warning(f"Ranking chart failed: {e}")
        try:
            dist_vals = df[primary_col].dropna().astype(float).tolist()
            if len(dist_vals) >= 5:
                region_b64 = distribution_chart(dist_vals, currency, primary_col)
        except Exception as e:
            logger.warning(f"Distribution chart failed: {e}")

    else:
        chart_strategy = "distribution"
        trend = "Distribution"
        try:
            dist_vals = df[primary_col].dropna().astype(float).tolist()
            if len(dist_vals) >= 2:
                trend_b64 = distribution_chart(dist_vals, currency, primary_col)
        except Exception as e:
            logger.warning(f"Distribution chart failed: {e}")

    # ── Confidence ──
    total_cells = df.shape[0] * df.shape[1]
    missing = df.isnull().sum().sum()
    confidence = max(10, int(100 - (missing / max(total_cells, 1)) * 100))

    # ── AI insights ──
    ai_insights = []
    if use_ai:
        try:
            if ai_providers.is_ai_available():
                top_kpis = list(kpi_metrics.items())[:5]
                kpi_text = "\n".join(f"- {v['label']}: {currency}{v['value']:,.0f}" for k, v in top_kpis)
                shape_note = {
                    "time-series": f"This is time-series data ordered by '{time_col}'. "
                                   f"The primary metric is {trend.lower()} ({growth_rate:.1f}% first-to-last).",
                    "categorical": f"This is categorical data grouped by '{cat_col}'. "
                                   f"There is NO time dimension — do not describe trends over time; "
                                   f"compare segments instead.",
                    "distribution": "This data has no time or categorical structure. "
                                    "Describe the distribution and spread — do NOT invent a time trend.",
                }.get(chart_strategy, "")
                prompt = f"""You are a business analyst. Analyse this dataset and provide 6 concise, consulting-grade insights.

Dataset: {len(df)} rows, {len(numeric_cols)} numeric columns, {len(text_cols)} text columns.
Primary metric: {primary_col}
Data shape: {shape_note}
Top KPIs:
{kpi_text}

Base every insight only on the data shape described above. Return exactly 6 bullet insights, one per line, starting with •. No markdown headers."""
                raw = ai_providers.get_ai_response(prompt, max_tokens=600)
                if raw:
                    lines = [l.strip().lstrip('•-').strip() for l in raw.split('\n')
                             if l.strip() and len(l.strip()) > 15]
                    ai_insights = lines[:6]
        except Exception as e:
            logger.warning(f"AI insights failed: {e}")

    # ── Shape-aware statistical fallback ──
    if not ai_insights:
        if chart_strategy == "time-series":
            headline = (f"Primary metric '{primary_col}' is {trend.lower()} with "
                        f"{abs(growth_rate):.1f}% {'growth' if growth_rate >= 0 else 'decline'} "
                        f"from the first to the last period.")
        elif chart_strategy == "categorical":
            headline = (f"'{primary_col}' varies across {cat_col.replace('_', ' ')} segments — "
                        f"'{region_labels[0]}' leads with the largest share." if region_labels
                        else f"'{primary_col}' is broken down by {cat_col}.")
        else:
            headline = (f"'{primary_col}' ranges from {currency}{float(df[primary_col].min()):,.0f} "
                        f"to {currency}{float(df[primary_col].max()):,.0f}, "
                        f"averaging {currency}{float(df[primary_col].mean()):,.0f}.")
        ai_insights = [
            headline,
            f"Dataset contains {len(df):,} records across {len(numeric_cols)} numeric and {len(text_cols)} categorical dimensions.",
            f"Data completeness score: {confidence}% — {'high quality data suitable for reliable analysis.' if confidence >= 80 else 'some missing values detected, interpret results with caution.'}",
            (f"Top segment: {region_labels[0]} accounts for the largest share of total {primary_col}."
             if region_labels else f"No categorical segmentation detected — analysis is based on {len(df)} data points."),
            f"Average {primary_col.replace('_', ' ')}: {currency}{float(df[primary_col].mean()):,.0f} (median {currency}{float(df[primary_col].median()):,.0f}).",
            f"Identified {len(numeric_cols)} KPI dimensions for analysis: {', '.join(c.replace('_', ' ') for c in numeric_cols[:4])}{'...' if len(numeric_cols) > 4 else ''}.",
        ]

    # ── Column summary ──
    column_summary = {}
    for col in df.columns[:20]:
        dtype = str(df[col].dtype)
        column_summary[col] = "numeric" if "int" in dtype or "float" in dtype else "text"

    return {
        "currency": currency,
        "row_count": len(df),
        "confidence": confidence,
        "trend": trend,
        "growth_rate": growth_rate,
        "primary_col": primary_col,
        "revenue_chart_b64": trend_b64,
        "region_chart_b64": region_b64,
        "kpi_metrics": kpi_metrics,
        "ai_insights": ai_insights,
        "column_summary": column_summary,
        "chart_strategy": chart_strategy,
    }, None
