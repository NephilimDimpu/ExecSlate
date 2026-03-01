"""
Enhanced Revenue Reporting Module
Addresses all 15 critical gaps identified in gap analysis
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# ==================== KPI CLASSIFICATION ====================

KNOWN_KPIS = {
    'revenue': {
        'patterns': ['revenue', 'sales', 'income', 'turnover', 'gross_sales', 'net_sales', 'total_sales'],
        'format': 'currency',
        'direction': 'up_good',
        'label': 'Revenue',
        'priority': 1,
    },
    'profit': {
        'patterns': ['profit', 'earnings', 'ebitda', 'ebit', 'net_income', 'operating_income', 'gross_profit', 'net_profit'],
        'format': 'currency',
        'direction': 'up_good',
        'label': 'Profit',
        'priority': 2,
    },
    'margin': {
        'patterns': ['margin', 'gpm', 'npm', 'gross_margin', 'net_margin', 'profit_margin', 'operating_margin'],
        'format': 'percent',
        'direction': 'up_good',
        'label': 'Margin',
        'priority': 3,
    },
    'cost': {
        'patterns': ['cost', 'expense', 'cogs', 'opex', 'spend', 'expenditure', 'overhead', 'total_cost', 'operating_expense'],
        'format': 'currency',
        'direction': 'down_good',
        'label': 'Cost',
        'priority': 4,
    },
    'units': {
        'patterns': ['units', 'quantity', 'volume', 'count', 'orders', 'transactions', 'items_sold', 'qty', 'num_orders'],
        'format': 'number',
        'direction': 'up_good',
        'label': 'Units',
        'priority': 5,
    },
    'rate': {
        'patterns': ['rate', 'churn', 'attrition', 'conversion', 'retention', 'utilization', 'efficiency', 'yield', 'churn_rate', 'conversion_rate', 'retention_rate'],
        'format': 'percent',
        'direction': 'down_good',
        'label': 'Rate',
        'priority': 6,
    },
}


def classify_metrics(metric_columns: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Classify detected numeric columns into known KPI types.
    Returns a dict mapping column name -> KPI metadata.
    """
    classified = {}
    
    for col in metric_columns:
        col_lower = col.lower().strip().replace(' ', '_')
        matched = False
        
        for kpi_type, kpi_info in KNOWN_KPIS.items():
            for pattern in kpi_info['patterns']:
                if pattern in col_lower or col_lower in pattern:
                    classified[col] = {
                        'type': kpi_type,
                        'format': kpi_info['format'],
                        'direction': kpi_info['direction'],
                        'label': kpi_info.get('label', col.replace('_', ' ').title()),
                        'priority': kpi_info['priority'],
                    }
                    matched = True
                    break
            if matched:
                break
        
        if not matched:
            # Unknown metric — still include it
            classified[col] = {
                'type': 'other',
                'format': 'number',
                'direction': 'neutral',
                'label': col.replace('_', ' ').title(),
                'priority': 99,
            }
    
    logger.info(f"📊 KPI classification: {', '.join(f'{col} → {info["type"]}' for col, info in classified.items())}")
    return classified


def get_report_title(kpi_metrics: Dict[str, Dict] = None) -> str:
    """
    Determine adaptive report title based on detected KPIs.
    """
    if not kpi_metrics or len(kpi_metrics) == 0:
        return "Executive Performance Report"
    
    types = {info.get('type', 'other') for info in kpi_metrics.values()}
    
    # Multi-KPI -> Business Performance
    if len(types) >= 3 or ('revenue' in types and 'profit' in types):
        return "Business Performance Report"
    
    # Revenue + something -> Financial Performance
    if 'revenue' in types and len(types) >= 2:
        return "Financial Performance Report"
    
    # Revenue only
    if types == {'revenue'} or (len(types) == 1 and 'revenue' in types):
        return "Revenue Analysis Report"
    
    # Cost/expense focused
    if 'cost' in types and 'revenue' not in types:
        return "Cost Analysis Report"
    
    # Operations focused
    if 'units' in types and 'revenue' not in types:
        return "Operations Performance Report"
    
    return "Executive Performance Report"


# ==================== GAP 1: DATA HANDLING ====================

def detect_column_types(df: pd.DataFrame) -> Dict[str, List[str]]:
    """
    Auto-detect column types: dimensions, metrics, and dates
    
    Addresses Gap 1.1: Multi-column detection
    """
    dimensions = []
    metrics = []
    dates = []
    
    for col in df.columns:
        # Check if it's a date column
        if is_date_column(df[col]):
            dates.append(col)
        # Check if it's numeric (metric)
        elif pd.api.types.is_numeric_dtype(df[col]):
            metrics.append(col)
        # Otherwise it's a dimension (category)
        else:
            dimensions.append(col)
    
    logger.info(f"📊 Detected columns - Dimensions: {dimensions}, Metrics: {metrics}, Dates: {dates}")
    
    return {
        'dimensions': dimensions,
        'metrics': metrics,
        'dates': dates
    }

def is_date_column(series: pd.Series) -> bool:
    """Check if a column contains dates"""
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    
    # Try parsing as date
    if series.dtype == 'object':
        try:
            pd.to_datetime(series, errors='coerce')
            # If more than 50% parse successfully, it's a date column
            parsed = pd.to_datetime(series, errors='coerce')
            if parsed.notna().sum() / len(series) > 0.5:
                return True
        except:
            pass
    
    return False

def validate_data(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Validate uploaded data and return issues
    
    Addresses Gap 1.2: Data validation
    """
    issues = []
    warnings = []
    
    # Check for empty dataframe
    if df.empty:
        issues.append({
            'type': 'critical',
            'message': 'File contains no data',
            'suggestion': 'Upload a file with at least one row of data'
        })
        return {'valid': False, 'issues': issues, 'warnings': warnings}
    
    # Check for missing values
    missing_counts = df.isnull().sum()
    if missing_counts.any():
        for col, count in missing_counts[missing_counts > 0].items():
            pct = (count / len(df)) * 100
            warnings.append({
                'type': 'warning',
                'message': f'Column "{col}" has {count} missing values ({pct:.1f}%)',
                'suggestion': 'Missing values will be ignored in calculations'
            })
    
    # Check for duplicate rows
    dup_count = df.duplicated().sum()
    if dup_count > 0:
        warnings.append({
            'type': 'warning',
            'message': f'{dup_count} duplicate rows found',
            'suggestion': 'Duplicates will be included in analysis unless removed'
        })
    
    # Check for negative values in metrics
    columns = detect_column_types(df)
    for metric in columns['metrics']:
        if (df[metric] < 0).any():
            neg_count = (df[metric] < 0).sum()
            warnings.append({
                'type': 'warning',
                'message': f'Column "{metric}" has {neg_count} negative values',
                'suggestion': 'Verify if negative values are intentional (e.g., refunds)'
            })
    
    # Check for sufficient data
    if len(df) < 3:
        warnings.append({
            'type': 'warning',
            'message': f'Only {len(df)} data points found',
            'suggestion': 'At least 6-12 periods recommended for reliable trends'
        })
    
    return {
        'valid': len(issues) == 0,
        'issues': issues,
        'warnings': warnings,
        'row_count': len(df),
        'column_count': len(df.columns)
    }

def detect_time_period(df: pd.DataFrame, date_column: str) -> Optional[str]:
    """
    Auto-detect time period (daily, weekly, monthly, quarterly, yearly)
    
    Addresses Gap 1.3: Period detection
    """
    try:
        dates = pd.to_datetime(df[date_column])
        dates_sorted = dates.sort_values()
        
        # Calculate most common difference between dates
        diffs = dates_sorted.diff().dropna()
        if len(diffs) == 0:
            return None
            
        mode_diff = diffs.mode()[0] if len(diffs.mode()) > 0 else diffs.median()
        days = mode_diff.days
        
        if days <= 1:
            return 'daily'
        elif days <= 7:
            return 'weekly'
        elif days <= 35:  # ~monthly (28-31 days)
            return 'monthly'
        elif days <= 100:  # ~quarterly (90-92 days)
            return 'quarterly'
        else:
            return 'yearly'
    except Exception as e:
        logger.warning(f"Could not detect time period: {e}")
        return None

# ==================== GAP 2: ANALYSIS DEPTH ====================

def generate_segmentation_analysis(df: pd.DataFrame, metric: str, dimension: str) -> Dict[str, Any]:
    """
    Generate segmentation table for metric by dimension
    
    Addresses Gap 2.1: Segmentation tables
    """
    try:
        # Group by dimension and calculate aggregates
        segment_data = df.groupby(dimension)[metric].agg([
            ('total', 'sum'),
            ('avg', 'mean'),
            ('count', 'count'),
            ('min', 'min'),
            ('max', 'max')
        ]).reset_index()
        
        # Calculate percentage of total
        total_sum = segment_data['total'].sum()
        segment_data['pct_of_total'] = (segment_data['total'] / total_sum * 100).round(1)
        
        # Sort by total descending
        segment_data = segment_data.sort_values('total', ascending=False)
        
        # Identify top and bottom performers
        top_performer = segment_data.iloc[0] if len(segment_data) > 0 else None
        bottom_performer = segment_data.iloc[-1] if len(segment_data) > 0 else None
        
        return {
            'table': segment_data.to_dict('records'),
            'top_performer': {
                'name': top_performer[dimension] if top_performer is not None else None,
                'value': float(top_performer['total']) if top_performer is not None else 0,
                'pct': float(top_performer['pct_of_total']) if top_performer is not None else 0
            },
            'bottom_performer': {
                'name': bottom_performer[dimension] if bottom_performer is not None else None,
                'value': float(bottom_performer['total']) if bottom_performer is not None else 0,
                'pct': float(bottom_performer['pct_of_total']) if bottom_performer is not None else 0
            },
            'segment_count': len(segment_data)
        }
    except Exception as e:
        logger.error(f"Error generating segmentation for {metric} by {dimension}: {e}")
        return None

def calculate_period_comparison(df: pd.DataFrame, metric: str, date_column: str) -> Dict[str, Any]:
    """
    Calculate period-over-period comparisons (QoQ, YoY, MoM)
    
    Addresses Gap 2.2: Period comparison
    """
    try:
        # Sort by date
        df_sorted = df.sort_values(date_column)
        
        # Get current and previous period values
        current_period = df_sorted.iloc[-1][metric] if len(df_sorted) > 0 else 0
        previous_period = df_sorted.iloc[-2][metric] if len(df_sorted) > 1 else 0
        
        # Calculate change
        absolute_change = current_period - previous_period
        percent_change = (absolute_change / previous_period * 100) if previous_period != 0 else 0
        
        # Detect period type
        period_type = detect_time_period(df, date_column) or 'period'
        
        # Calculate year-over-year if enough data
        yoy_change = None
        yoy_percent = None
        if len(df_sorted) >= 12 and period_type == 'monthly':
            current_month = df_sorted.iloc[-1][metric]
            year_ago_month = df_sorted.iloc[-12][metric] if len(df_sorted) >= 12 else 0
            yoy_change = current_month - year_ago_month
            yoy_percent = (yoy_change / year_ago_month * 100) if year_ago_month != 0 else 0
        
        return {
            'current': float(current_period),
            'previous': float(previous_period),
            'absolute_change': float(absolute_change),
            'percent_change': float(percent_change),
            'direction': 'up' if absolute_change > 0 else 'down' if absolute_change < 0 else 'flat',
            'period_type': period_type,
            'yoy_change': float(yoy_change) if yoy_change is not None else None,
            'yoy_percent': float(yoy_percent) if yoy_percent is not None else None
        }
    except Exception as e:
        logger.error(f"Error calculating period comparison: {e}")
        return None

def forecast_metric(df: pd.DataFrame, metric: str, date_column: str, periods: int = 3) -> Dict[str, Any]:
    """
    Simple linear forecast for future periods
    
    Addresses Gap 2.3: Forecasting
    """
    try:
        # Sort by date
        df_sorted = df.sort_values(date_column).reset_index(drop=True)
        historical_values = df_sorted[metric].values
        
        # Simple linear regression
        X = np.arange(len(historical_values)).reshape(-1, 1)
        y = historical_values
        
        # Calculate slope and intercept manually (avoid sklearn dependency)
        mean_x = X.mean()
        mean_y = y.mean()
        slope = ((X.flatten() - mean_x) * (y - mean_y)).sum() / ((X.flatten() - mean_x) ** 2).sum()
        intercept = mean_y - slope * mean_x
        
        # Forecast future values
        future_X = np.arange(len(historical_values), len(historical_values) + periods)
        forecast = slope * future_X + intercept
        
        # Calculate confidence (based on R-squared)
        y_pred = slope * X.flatten() + intercept
        r_squared = 1 - (((y - y_pred) ** 2).sum() / ((y - mean_y) ** 2).sum())
        
        return {
            'forecast_values': forecast.tolist(),
            'confidence': float(r_squared),
            'trend': 'growing' if slope > 0 else 'declining' if slope < 0 else 'flat',
            'avg_growth_rate': float(slope / mean_y * 100) if mean_y != 0 else 0
        }
    except Exception as e:
        logger.error(f"Error forecasting {metric}: {e}")
        return None

# ==================== GAP 3: OUTPUT QUALITY ====================

def format_currency(value: float, currency: str = "$", short: bool = True) -> str:
    """
    Consistent currency formatting
    
    Addresses Gap 3.3: Number formatting
    """
    if short:
        if abs(value) >= 1_000_000000:  # Billion
            return f"{currency}{value/1_000_000_000:.1f}B"
        elif abs(value) >= 1_000_000:  # Million
            return f"{currency}{value/1_000_000:.1f}M"
        elif abs(value) >= 1_000:  # Thousand
            return f"{currency}{value/1_000:.1f}k"
        else:
            return f"{currency}{value:,.0f}"
    else:
        return f"{currency}{value:,.0f}"

def format_percent(value: float, decimals: int = 1) -> str:
    """Format percentage consistently"""
    return f"{value:+.{decimals}f}%" if value != 0 else f"{value:.{decimals}f}%"

# ==================== MAIN ANALYSIS FUNCTION ====================

def analyze_comprehensive(df: pd.DataFrame, currency: str = "$") -> Dict[str, Any]:
    """
    Comprehensive multi-dimensional analysis
    
    Combines all enhancements into single analysis function
    """
    results = {
        'validation': None,
        'column_detection': None,
        'overall_metrics': {},
        'segmentation': {},
        'period_comparison': None,
        'forecast': None,
        'insights': [],
        'recommendations': []
    }
    
    # 1. Validate data
    validation = validate_data(df)
    results['validation'] = validation
    
    if not validation['valid']:
        return results
    
    # 2. Detect column types
    columns = detect_column_types(df)
    results['column_detection'] = columns
    
    if not columns['metrics']:
        logger.warning("No numeric metrics detected in data")
        return results
    
    # 2.5 Classify metrics into known KPI types
    kpi_classification = classify_metrics(columns['metrics'])
    results['kpi_classification'] = kpi_classification
    
    # 3. Overall metrics for each numeric column
    for metric in columns['metrics']:
        results['overall_metrics'][metric] = {
            'total': float(df[metric].sum()),
            'avg': float(df[metric].mean()),
            'median': float(df[metric].median()),
            'min': float(df[metric].min()),
            'max': float(df[metric].max()),
            'std': float(df[metric].std()),
            'count': int(df[metric].count())
        }
    
    # 4. Segmentation analysis (metric by dimension)
    for metric in columns['metrics']:
        results['segmentation'][metric] = {}
        for dimension in columns['dimensions']:
            seg_analysis = generate_segmentation_analysis(df, metric, dimension)
            if seg_analysis:
                results['segmentation'][metric][dimension] = seg_analysis
    
    # 5. Period comparison (if date column exists)
    if columns['dates']:
        date_col = columns['dates'][0]  # Use first date column
        primary_metric = columns['metrics'][0]  # Use first metric
        
        period_comp = calculate_period_comparison(df, primary_metric, date_col)
        if period_comp:
            results['period_comparison'] = period_comp
        
        # 6. Forecast
        forecast = forecast_metric(df, primary_metric, date_col, periods=3)
        if forecast:
            results['forecast'] = forecast
    
    # 7. Generate AI-ready insights summary
    results['insights'] = generate_insight_summary(results, currency)
    
    return results

def generate_insight_summary(analysis: Dict[str, Any], currency: str = "$") -> List[str]:
    """
    Generate human-readable insights from analysis
    
    Addresses Gap 2.4: Enhanced AI insights with specific numbers
    """
    insights = []
    
    # Overall metrics insight
    if analysis['overall_metrics']:
        primary_metric = list(analysis['overall_metrics'].keys())[0]
        metrics = analysis['overall_metrics'][primary_metric]
        
        total_str = format_currency(metrics['total'], currency)
        avg_str = format_currency(metrics['avg'], currency)
        
        insights.append(
            f"Total {primary_metric}: {total_str} across {metrics['count']} periods "
            f"(avg: {avg_str}/period)"
        )
    
    # Period comparison insight
    if analysis['period_comparison']:
        pc = analysis['period_comparison']
        change_str = format_currency(abs(pc['absolute_change']), currency)
        pct_str = format_percent(pc['percent_change'])
        
        insights.append(
            f"Period-over-period: {change_str} ({pct_str}) "
            f"{'increase' if pc['direction'] == 'up' else 'decrease' if pc['direction'] == 'down' else 'no change'}"
        )
    
    # Segmentation insights
    if analysis['segmentation']:
        for metric, dimensions in analysis['segmentation'].items():
            for dimension, seg_data in dimensions.items():
                if seg_data and seg_data['top_performer']['name']:
                    top = seg_data['top_performer']
                    top_str = format_currency(top['value'], currency)
                    
                    insights.append(
                        f"Top {dimension}: {top['name']} with {top_str} "
                        f"({top['pct']:.0f}% of total {metric})"
                    )
    
    # Forecast insight
    if analysis['forecast']:
        fc = analysis['forecast']
        if fc['forecast_values']:
            next_value = format_currency(fc['forecast_values'][0], currency)
            insights.append(
                f"Forecast next period: {next_value} "
                f"(trend: {fc['trend']}, confidence: {fc['confidence']*100:.0f}%)"
            )
    
    return insights

# ==================== UTILITIES ====================

def create_segmentation_table_markdown(seg_data: Dict[str, Any], metric: str, dimension: str, currency: str = "$") -> str:
    """Create markdown table for segmentation"""
    if not seg_data or not seg_data['table']:
        return ""
    
    table = seg_data['table']
    
    # Header
    md = f"\n### {metric.title()} by {dimension.title()}\n\n"
    md += f"| {dimension.title()} | Total | % of Total | Average |\n"
    md += "|" + "-" * 20 + "|" + "-" * 15 + "|" + "-" * 12 + "|" + "-" * 15 + "|\n"
    
    # Rows
    for row in table:
        name = row[dimension]
        total = format_currency(row['total'], currency)
        pct = f"{row['pct_of_total']:.1f}%"
        avg = format_currency(row['avg'], currency)
        md += f"| {name} | {total} | {pct} | {avg} |\n"
    
    return md
