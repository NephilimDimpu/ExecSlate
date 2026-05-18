# ==================== EXECSLATE - PART 1: IMPORTS, CONFIG & HELPERS ====================
# File: C:\ExecSlate\app.py
# Instructions: This is PART 1 - Copy this to the TOP of your new app.py file

from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware

import pandas as pd
import numpy as np
import os, json, tempfile, time, glob, shutil
import matplotlib
matplotlib.use('Agg')  # Non-GUI backend for server
import matplotlib.pyplot as plt
import seaborn as sns

from openai import OpenAI  # kept for type hints

# AI provider fallback chain
import ai_providers
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.chart.data import ChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

import bcrypt
import logging
from datetime import datetime
from pathlib import Path

from docx import Document
from pptx.dml.color import RGBColor
from docx.shared import Inches as DocxInches, Pt as DocxPt
from docx.enum.text import WD_ALIGN_PARAGRAPH

# Import database module
import database as db

# Import enhanced analysis module
import enhanced_analysis as ea

# Import export functions
from exports.export_functions import export_pdf_enhanced, export_ppt_enhanced


# ==================== LOGGING SETUP ====================
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ==================== CONFIGURATION ====================
ENV = os.getenv("ENV", "development")
DEBUG = ENV != "production"
DEFAULT_CURRENCY = "$"
MAX_FILE_SIZE = 5_000_000  # 5MB limit

# Cross-platform path handling
BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR / "uploads"
EXPORT_DIR = BASE_DIR / "exports"
CHART_DIR = BASE_DIR / "static" / "charts"
TEMPLATE_DIR = BASE_DIR / "templates"

# Create required directories
for directory in [UPLOAD_DIR, EXPORT_DIR, CHART_DIR]:
    directory.mkdir(parents=True, exist_ok=True)

# Session security
SESSION_SECRET = os.getenv("SESSION_SECRET", "dev-secret-change-in-production")
if ENV == "production" and SESSION_SECRET == "dev-secret-change-in-production":
    raise ValueError("⚠️ SESSION_SECRET must be set in production!")

# ==================== RAZORPAY CONFIGURATION ====================
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")

try:
    import razorpay
    if RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET:
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        logger.info("✅ Razorpay client initialized")
    else:
        razorpay_client = None
        logger.warning("⚠️ Razorpay keys not set — payment processing disabled")
except ImportError:
    razorpay_client = None
    logger.warning("⚠️ razorpay package not installed — payment processing disabled")

# ==================== PLAN LIMITS ====================
PLAN_LIMITS = {
    "demo": {
        "max_uploads": 1,               # Only 1 upload to try it out
        "max_ai_generations": 1,        # Allow 1 AI to showcase the feature
        "max_ai_regens": 0,
        "ppt_export": False,            # No PPT for demo users
        "docx_export": False            # No Word for demo (PDF only)
    },
    "free": {
        "max_uploads": 3,
        "max_ai_generations": 1,
        "max_ai_regens": 0,
        "ppt_export": False
    },
    "pro": {
        "max_uploads": 20,              # 20 reports per month
        "max_ai_generations": 10,       # 10 AI-enhanced analyses
        "max_ai_regens": 5,             # 5 regeneration cycles
        "ppt_export": True
    },
    "business": {
        "max_uploads": None,            # Unlimited
        "max_ai_generations": None,     # Unlimited
        "max_ai_regens": None,          # Unlimited
        "ppt_export": True
    }
}

# ==================== AI PROVIDER STATUS ====================
# Multi-provider fallback chain is initialized in ai_providers.py
# Supports: OpenAI → Gemini → Groq → Statistical Fallback
# Set env vars: OPENAI_API_KEY, GEMINI_API_KEY, GROQ_API_KEY

# Backward-compatible: 'client' check replaced by ai_providers.is_ai_available()
client = True if ai_providers.is_ai_available() else None

# ==================== PASSWORD HASHING ====================

def hash_password(password: str) -> str:
    """Hash a password using raw bcrypt"""
    # bcrypt requires bytes
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_bytes.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hash"""
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

# ==================== FASTAPI APP SETUP ====================
app = FastAPI(title="ExecSlate", version="1.0.0")

import routes.payments as payments
app.include_router(payments.router)

# Add session middleware
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=86400)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))

# ==================== RATE LIMITING ====================
try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    limiter = Limiter(key_func=get_remote_address)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    logger.info("✅ Rate limiting enabled")
except ImportError:
    # Graceful fallback if slowapi not installed
    from types import SimpleNamespace
    limiter = SimpleNamespace(limit=lambda *a, **k: lambda f: f)
    logger.warning("⚠️ slowapi not installed — rate limiting disabled")

# ==================== EXPORT CLEANUP ====================
def cleanup_old_exports(max_age_days: int = 7):
    """Delete export files older than max_age_days to prevent disk bloat."""
    cutoff = time.time() - (max_age_days * 86400)
    removed = 0
    for ext in ("*.pdf", "*.pptx", "*.docx"):
        for f in glob.glob(str(EXPORT_DIR / ext)):
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
                    removed += 1
            except Exception:
                pass
    if removed:
        logger.info(f"🧹 Cleaned up {removed} export file(s) older than {max_age_days} days")

# ==================== GLOBAL ERROR HANDLER ====================
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP errors with custom error page"""
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        
    # Pass through redirects (3xx) - used by auth guards
    if 300 <= exc.status_code < 400:
        from starlette.responses import Response
        response = Response(status_code=exc.status_code)
        if exc.headers:
            for key, value in exc.headers.items():
                response.headers[key] = value
        return response
    
    return templates.TemplateResponse(request=request, name="error.html", context=
        {
            "request": request,
            "status_code": exc.status_code,
            "detail": exc.detail
        },
        status_code=exc.status_code
    )

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """Custom 404 handler"""
    return templates.TemplateResponse(request=request, name="error.html", context=
        {"request": request, "status_code": 404, "detail": None},
        status_code=404
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all error handler for production"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    
    # Check if it's an HTTPException
    status_code = getattr(exc, 'status_code', 500)
    
    # Do not leak internal server details in production for unhandled 500 errors
    if ENV == "production" and status_code == 500:
        detail = "An internal server error occurred. Our team has been notified. Please try again later."
    else:
        detail = getattr(exc, 'detail', str(exc))
    
    # Return JSON for API routes
    if request.url.path.startswith("/api/"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detail": detail}, status_code=status_code)
        
    return templates.TemplateResponse(request=request, name="error.html", context=
        {
            "request": request,
            "status_code": status_code,
            "detail": detail
        },
        status_code=status_code
    )

# ==================== IN-MEMORY DATA STORE ====================
# In production, replace with a database (PostgreSQL, MongoDB, etc.)

users = {
    "admin@execslate.com": {
        "email": "admin@execslate.com",
        "password": hash_password(os.getenv("ADMIN_PASSWORD", "admin123")),
        "plan": "pro",
        "uploads_used": 0,
        "ai_generations_used": 0,
        "ai_regens_used": 0,
        "is_admin": True
    },
    "demo@execslate.ai": {
        "email": "demo@execslate.ai",
        "password": hash_password("demo123"),
        "plan": "demo",  # Restricted demo plan
        "uploads_used": 0,
        "ai_generations_used": 0,
        "ai_regens_used": 0,
        "is_admin": False
    }
}

projects = [
    {
        "id": 1,
        "user_email": "demo@execslate.ai",
        "client": "Daulaguphu Industries Ltd",
        "period": "Q2 2025",
        "uploads": 0,
        "ai_used": False,
        "ai_regens": 0,
        "currency": DEFAULT_CURRENCY,
        "generated": False
    },
    {
        "id": 2,
        "user_email": "demo@execslate.ai",
        "client": "Orion Retail Group",
        "period": "FY 2024",
        "uploads": 0,
        "ai_used": False,
        "ai_regens": 0,
        "currency": DEFAULT_CURRENCY,
        "generated": False
    },
]

next_project_id = 3

# In-memory analytics storage for non-DB (admin/demo) accounts — mirrors the
# dual-storage pattern used for `projects`. Keyed by project id.
analytics_sessions_mem = {}   # {project_id: session_dict}
analytics_drafts_mem = {}     # {project_id: [draft_dict, ...]}

# ==================== HELPER FUNCTIONS ====================

def log(event: str, details: str = ""):
    """Structured logging helper"""
    logger.info(f"{event} | {details}")

def get_user_plan(request: Request) -> str:
    """Get current user's plan from session"""
    user = request.session.get("user")
    return user.get("plan", "free") if user else "free"

def cleanup_temp_file(file_path: str):
    """Safely cleanup temporary files"""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
            logger.debug(f"Cleaned up: {file_path}")
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

def require_user(request: Request):
    """Authentication guard - redirects to login if not authenticated"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    return user

def require_admin(request: Request):
    """Admin authentication guard"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=303, headers={"Location": "/login"})
    
    user_data = users.get(user["email"])
    if not user_data or not user_data.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

def is_demo_user(user):
    """Check if user is on demo plan"""
    if not user:
        return False
    return user.get("plan") == "demo" or user.get("email") == "demo@execslate.ai"

# ==================== DATA VALIDATION ====================

def validate_dataframe(df, revenue_col, region_col=None):
    """
    Validate uploaded DataFrame for common edge cases.
    
    Args:
        df: pandas DataFrame
        revenue_col: Name of the revenue column
        region_col: Optional name of the region column
    
    Returns:
        tuple: (is_valid: bool, error_message: str or None, cleaned_df: DataFrame or None)
    """
    # Check 1: Empty DataFrame
    if df is None or df.empty:
        return False, "The uploaded file is empty. Please upload a file with data rows.", None
    
    # Check 2: Too few rows
    if len(df) < 2:
        return False, "The file needs at least 2 data rows to generate a meaningful report.", None
    
    # Check 3: Primary metric column exists
    if revenue_col not in df.columns:
        available = ", ".join(df.columns[:10])
        return False, f"Column '{revenue_col}' not found in your file. Available columns: {available}. Please check column names.", None
    
    # Check 4: Primary metric column has data (not all empty)
    revenue_data = df[revenue_col]
    if revenue_data.isna().all():
        return False, f"The '{revenue_col}' column is completely empty. Please provide numeric data in this column.", None
    
    # Check 5: Try converting to numeric
    revenue_numeric = pd.to_numeric(revenue_data, errors='coerce')
    non_numeric_count = revenue_numeric.isna().sum() - revenue_data.isna().sum()
    
    if non_numeric_count > 0:
        # Some values couldn't be converted
        total = len(revenue_data)
        pct = (non_numeric_count / total) * 100
        if pct > 50:
            return False, f"More than half ({non_numeric_count}/{total}) of values in '{revenue_col}' are text instead of numbers. Tip: Remove currency symbols, commas, or non-numeric text from this column.", None
        else:
            # Auto-clean: drop non-numeric rows
            logger.warning(f"Dropping {non_numeric_count} non-numeric rows from '{revenue_col}' column")
    
    # Check 6: Replace column with cleaned numeric data
    df = df.copy()
    df[revenue_col] = revenue_numeric
    
    # Drop rows where revenue is NaN (after conversion)
    before_count = len(df)
    df = df.dropna(subset=[revenue_col])
    dropped = before_count - len(df)
    
    if dropped > 0:
        logger.info(f"Dropped {dropped} rows with empty/invalid revenue values")
    
    # Check 7: After cleaning, still have enough rows?
    if len(df) < 2:
        return False, "After removing invalid/empty values, less than 2 rows remain. Please check your data quality.", None
    
    # Check 8: All zeros
    if (df[revenue_col] == 0).all():
        return False, f"All values in '{revenue_col}' are zero. Please upload data with actual figures to generate a meaningful report.", None
    
    # Check 9: Negative values warning (not an error, just clean)
    neg_count = (df[revenue_col] < 0).sum()
    if neg_count > 0:
        logger.info(f"Note: {neg_count} negative revenue values found (treating as valid loss data)")
    
    # Check 10: Region column validation (if specified)
    if region_col and region_col in df.columns:
        # Fill empty regions with "Unknown"
        df[region_col] = df[region_col].fillna("Unknown").astype(str)
        # Trim whitespace
        df[region_col] = df[region_col].str.strip()
        df.loc[df[region_col] == "", region_col] = "Unknown"
    
    # Check 11: Extreme outliers warning
    mean_val = df[revenue_col].mean()
    std_val = df[revenue_col].std()
    if std_val > 0:
        outlier_count = ((df[revenue_col] - mean_val).abs() > 5 * std_val).sum()
        if outlier_count > 0:
            logger.info(f"Note: {outlier_count} potential outlier(s) detected (>5 std deviations)")
    
    return True, None, df

# ==================== DATA PROCESSING FUNCTIONS ====================

def process_dataframe(project, df):
    """
    Process uploaded dataframe using comprehensive multi-dimensional analysis
    
    Args:
        project: Project dictionary to update
        df: Pandas DataFrame with revenue data
    """
    rev_col = project["column_map"]["revenue"]
    reg_col = project["column_map"].get("region")
    currency = project.get("currency", "$")
    
    # ✅ NEW: Run comprehensive analysis
    try:
        comprehensive_analysis = ea.analyze_comprehensive(df, currency)
        project["comprehensive_analysis"] = comprehensive_analysis
        
        # Store validation results
        if comprehensive_analysis.get('validation'):
            project["data_validation"] = comprehensive_analysis['validation']
        
        # Store column detection
        if comprehensive_analysis.get('column_detection'):
            project["detected_columns"] = comprehensive_analysis['column_detection']
        
        logger.info(f"✅ Comprehensive analysis complete")
        logger.info(f"   Dimensions: {comprehensive_analysis.get('column_detection', {}).get('dimensions', [])}")
        logger.info(f"   Metrics: {comprehensive_analysis.get('column_detection', {}).get('metrics', [])}")
        
        # ✅ NEW: Generate strategic hypotheses
        framework = project.get("analysis_framework", "general")
        project["hypotheses"] = ea.generate_hypotheses(comprehensive_analysis, framework)
        logger.info(f"✅ Generated {len(project['hypotheses'])} hypotheses for framework: {framework}")
        
    except Exception as e:
        logger.error(f"Enhanced analysis failed, falling back to basic: {e}")
        comprehensive_analysis = None
        project["comprehensive_analysis"] = None
    
    # Basic metrics (backward compatibility)
    project["row_count"] = len(df)
    revenue_data = df[rev_col].astype(float)
    project["revenue_series"] = list(revenue_data)
    project["total_revenue"] = float(revenue_data.sum())
    project["avg_revenue"] = float(revenue_data.mean())
    project["median_revenue"] = float(revenue_data.median())
    project["std_revenue"] = float(revenue_data.std())
    
    # Growth analysis
    if len(df) >= 2:
        first_val = revenue_data.iloc[0]
        last_val = revenue_data.iloc[-1]
        project["growth_rate"] = ((last_val - first_val) / first_val * 100) if first_val != 0 else 0
        project["trend"] = "Increasing" if last_val > first_val else "Decreasing"
    
    # ✅ PHASE B: Build multi-KPI metrics from all detected numeric columns
    kpi_metrics = {}
    kpi_classification = comprehensive_analysis.get('kpi_classification', {}) if comprehensive_analysis else {}
    overall_metrics = comprehensive_analysis.get('overall_metrics', {}) if comprehensive_analysis else {}
    
    for col_name in [rev_col] + [c for c in df.select_dtypes(include='number').columns if c != rev_col]:
        try:
            col_data = df[col_name].astype(float).dropna()
            if len(col_data) == 0:
                continue
            
            kpi_info = kpi_classification.get(col_name, {})
            kpi_label = kpi_info.get('label', col_name.replace('_', ' ').title())
            kpi_format = kpi_info.get('format', 'number')
            kpi_direction = kpi_info.get('direction', 'neutral')
            
            total = float(col_data.sum())
            avg = float(col_data.mean())
            median = float(col_data.median())
            
            # Growth
            growth = 0.0
            trend = "flat"
            if len(col_data) >= 2:
                first = col_data.iloc[0]
                last = col_data.iloc[-1]
                growth = ((last - first) / first * 100) if first != 0 else 0.0
                trend = "up" if last > first else "down" if last < first else "flat"
            
            kpi_metrics[col_name] = {
                'label': kpi_label,
                'total': total,
                'avg': avg,
                'median': median,
                'growth': round(float(growth), 1),
                'trend': trend,
                'format': kpi_format,
                'direction': kpi_direction,
                'type': kpi_info.get('type', 'other'),
                'priority': kpi_info.get('priority', 99),
            }
        except Exception as e:
            logger.warning(f"Skipping KPI column {col_name}: {e}")
    
    project["kpi_metrics"] = kpi_metrics
    project["primary_kpi"] = rev_col
    project["report_title"] = ea.get_report_title(kpi_metrics)
    logger.info(f"✅ Multi-KPI metrics built: {list(kpi_metrics.keys())} | Title: {project['report_title']}")
    
   # ✅ ENHANCED: Use segmentation from comprehensive analysis if available
    if comprehensive_analysis and comprehensive_analysis.get('segmentation'):
        segmentation = comprehensive_analysis['segmentation']
        
        # Try to find revenue or first metric
        primary_metric = None
        for metric_name in segmentation.keys():
            if 'revenue' in metric_name.lower() or metric_name == list(segmentation.keys())[0]:
                primary_metric = metric_name
                break
        
        if primary_metric and segmentation[primary_metric]:
            # Try to find region dimension
            for dim_name, seg_data in segmentation[primary_metric].items():
                if 'region' in dim_name.lower() or dim_name == list(segmentation[primary_metric].keys())[0]:
                    if seg_data and seg_data.get('top_performer'):
                        project["top_region"] = seg_data['top_performer']['name']
                        project["top_region_pct"] = seg_data['top_performer']['pct']
                        
                        # Extract labels and values for chart
                        table = seg_data.get('table', [])
                        if table:
                            project["region_labels"] = [row[dim_name] for row in table]
                            project["region_values"] = [row['total'] for row in table]
                            project["region_percentages"] = [row['pct_of_total'] for row in table]
                        break
    else:
        # Fallback to old regional analysis
        if reg_col and reg_col in df.columns:
            region_totals = df.groupby(reg_col)[rev_col].sum().sort_values(ascending=False)
            project["top_region"] = str(region_totals.index[0])
            project["region_labels"] = [str(x) for x in region_totals.index]
            project["region_values"] = [float(x) for x in region_totals.values]
            
            # Calculate regional percentages
            total = region_totals.sum()
            project["region_percentages"] = [float(x/total*100) for x in region_totals.values]

def reset_project(project):
    """
    Reset project data while keeping metadata
    
    Args:
        project: Project dictionary to reset
    """
    keep = {"id", "client", "period", "uploads", "ai_used", "ai_regens", "currency", "user_email"}
    for key in list(project.keys()):
        if key not in keep:
            project.pop(key, None)
    project["generated"] = False

def calculate_confidence(project):
    """
    Calculate confidence score based on data quality
    
    Args:
        project: Project dictionary with metrics
    
    Returns:
        int: Confidence score (0-100)
    """
    score = 0
    if project.get("row_count", 0) >= 10:
        score += 30
    if project.get("row_count", 0) >= 50:
        score += 10
    if project.get("trend"):
        score += 20
    if project.get("top_region"):
        score += 20
    if project.get("ai_used"):
        score += 20
    return min(score, 100)
    
def extract_segmentation_insights(project):
    """
    Extract top segmentation insights from comprehensive analysis
    
    Returns dict with formatted strings ready for insights
    """
    comp = project.get('comprehensive_analysis')
    if not comp or not comp.get('segmentation'):
        return None
    
    currency = project.get('currency', '$')
    insights = {}
    
    # Get segmentation data
    segmentation = comp.get('segmentation', {})
    
    # Find primary metric (revenue or first metric)
    primary_metric = None
    for metric_name in segmentation.keys():
        if 'revenue' in metric_name.lower():
            primary_metric = metric_name
            break
    if not primary_metric and segmentation:
        primary_metric = list(segmentation.keys())[0]
    
    if primary_metric and segmentation.get(primary_metric):
        metric_segs = segmentation[primary_metric]
        
        # Extract top performers from each dimension
        for dim_name, seg_data in metric_segs.items():
            if seg_data and seg_data.get('top_performer'):
                top = seg_data['top_performer']
                bottom = seg_data.get('bottom_performer', {})
                
                insights[dim_name] = {
                    'top_name': top.get('name'),
                    'top_value': top.get('value', 0),
                    'top_pct': top.get('pct', 0),
                    'bottom_name': bottom.get('name') if bottom else None,
                    'bottom_value': bottom.get('value', 0) if bottom else 0,
                    'bottom_pct': bottom.get('pct', 0) if bottom else 0,
                    'formatted_top': f"{top.get('name')} with {ea.format_currency(top.get('value', 0), currency)} ({top.get('pct', 0):.0f}%)",
                }
    
    # Get period comparison if available
    period_comp = comp.get('period_comparison')
    if period_comp:
        insights['period_comparison'] = {
            'current': period_comp.get('current', 0),
            'previous': period_comp.get('previous', 0),
            'change': period_comp.get('absolute_change', 0),
            'change_pct': period_comp.get('percent_change', 0),
            'direction': period_comp.get('direction', 'flat'),
            'formatted': f"{ea.format_currency(abs(period_comp.get('absolute_change', 0)), currency)} ({abs(period_comp.get('percent_change', 0)):.1f}%) {period_comp.get('direction', 'change')}"
        }
    
    return insights if insights else None

def generate_statistical_insights(project):
    """Consulting-grade statistical insights — enhanced with comprehensive analysis data"""
    import statistics
    
    currency = project.get("currency", "$")
    growth = project.get("growth_rate", 0)
    avg = project.get("avg_revenue", 0)
    total = project.get("total_revenue", 0)
    median = project.get("median_revenue", 0)
    trend = project.get("trend", "Unknown")
    top_region = project.get("top_region", None)
    row_count = project.get("row_count", 0)
    revenue_series = project.get("revenue_series", [])
    region_labels = project.get("region_labels", [])
    region_values = project.get("region_values", [])
    
    # ✅ NEW: Extract segmentation insights from comprehensive analysis
    seg_insights = extract_segmentation_insights(project)
    
    # ── Advanced Statistical Calculations ──
    volatility = 0
    if len(revenue_series) > 1 and avg > 0:
        volatility = (statistics.stdev(revenue_series) / avg * 100)
    
    # Min/Max analysis
    min_rev = min(revenue_series) if revenue_series else 0
    max_rev = max(revenue_series) if revenue_series else 0
    revenue_range = max_rev - min_rev
    
    # Recent performance (last 3 periods vs first 3)
    recent_momentum = ""
    if len(revenue_series) >= 6:
        first_half_avg = statistics.mean(revenue_series[:3])
        second_half_avg = statistics.mean(revenue_series[-3:])
        if first_half_avg > 0:
            momentum_pct = ((second_half_avg - first_half_avg) / first_half_avg) * 100
            if momentum_pct > 10:
                recent_momentum = "accelerating"
            elif momentum_pct > 0:
                recent_momentum = "maintaining positive trajectory"
            elif momentum_pct > -10:
                recent_momentum = "showing signs of deceleration"
            else:
                recent_momentum = "experiencing notable deceleration"
    
    # Median vs Mean skew analysis
    skew_direction = ""
    if avg > 0:
        skew_ratio = (avg - median) / avg * 100
        if skew_ratio > 10:
            skew_direction = "right-skewed (outlier high-value periods lifting the average)"
        elif skew_ratio < -10:
            skew_direction = "left-skewed (occasional low-value periods depressing the average)"
        else:
            skew_direction = "symmetrically distributed (consistent performance across periods)"
    
    # Regional concentration analysis
    top_region_pct = 0
    region_count = len(region_labels)
    if region_values and sum(region_values) > 0:
        top_region_pct = (region_values[0] / sum(region_values)) * 100
    
    # ✅ ENHANCED: Use segmentation data if available
    if seg_insights and 'region' in seg_insights:
        region_seg = seg_insights['region']
        top_region = region_seg['top_name']
        top_region_pct = region_seg['top_pct']
        region_count = len(region_labels) if region_labels else 4  # fallback
        
    # Trend descriptions (missing variable fix)
    if growth > 10:
        trend_desc = "indicates strong market momentum"
        trend_outlook = "Current momentum provides a strategic window to scale proven growth engines"
    elif growth > 0:
        trend_desc = "shows stable, positive evolution"
        trend_outlook = "Stable fundamentals warrant continued investment in validated channels"
    elif growth < -5:
        trend_desc = "reflects material contraction"
        trend_outlook = "Declining metrics demand immediate stabilization measures before further expansion"
    else:
        trend_desc = "remains relatively flat"
        trend_outlook = "Equilibrium state requires strategic intervention to break out into new growth"
    
    # ── SCQA Narrative Engine (Phase 1.2) ──
    
    # 1. Situation (The Context)
    situation = (
        f"ExecSlate Analysis: {currency}{total:,.0f} {project.get('report_title', 'Business Performance')}. "
        f"This report examines {row_count} data measurement intervals across {region_count or 1} active segment(s). "
        f"Current analysis framework: {project.get('analysis_framework', 'General Strategy').replace('_', ' ').title()}."
    )
    
    # 2. Complication (The Challenge/Change)
    comp_parts = []
    comp_parts.append(f"Revenue performance {trend_desc}, showing a {abs(growth):.1f}% {trend.lower()} trajectory.")
    if volatility > 20:
        comp_parts.append(f"Significant volatility ({volatility:.1f}%) in period-over-period performance creates forecasting risk.")
    if top_region_pct > 45:
        comp_parts.append(f"High concentration in {top_region} ({top_region_pct:.0f}% of total) creates structural sensitivity to that specific segment.")
    complication = " ".join(comp_parts)
    
    # 3. Question (The Strategic Pivot)
    if growth > 10:
        question = f"How can the organization best capitalize on this {abs(growth):.1f}% momentum without overextending resources or diluting margin?"
    elif growth < 0:
        question = f"What immediate stabilization measures are required to arrest the {abs(growth):.1f}% decline and return to baseline performance?"
    else:
        question = "In a period of relative stability, what are the primary levers for breaking out of this equilibrium into accelerated growth?"
        
    # 4. Answer (The Recommendation)
    answer = f"{trend_outlook}. Analysis suggests prioritizing {top_region if top_region else 'top-performing segments'} for continued investment while addressing {f'{volatility:.1f}% volatility' if volatility > 20 else 'operational consistency'}."
    
    summary = f"<strong>SITUATION:</strong> {situation}<br/><br/><strong>COMPLICATION:</strong> {complication}<br/><br/><strong>QUESTION:</strong> {question}<br/><br/><strong>ANSWER:</strong> {answer}"
    
    # ── Build Enhanced Insights (6 total) ──
    insights = [
        {
            "text": f"Growth Momentum: Revenue {trend_desc}, with {abs(growth):.1f}% {'expansion' if growth > 0 else 'decline'} indicating {'accelerating market traction and strong product-market fit' if growth > 15 else 'steady demand generation with room for optimization' if growth > 0 else 'competitive headwinds requiring strategic response'}",
            "sentiment": "positive" if growth > 5 else "negative" if growth < -5 else "neutral"
        },
        {
            "text": f"Unit Economics: Average revenue of {currency}{avg:,.0f} per period with a median of {currency}{median:,.0f}. Revenue distribution is {skew_direction}. The {currency}{revenue_range:,.0f} range between peak ({currency}{max_rev:,.0f}) and trough ({currency}{min_rev:,.0f}) periods {'indicates significant performance variability' if revenue_range > avg else 'reflects controlled performance consistency'}",
            "sentiment": "positive" if revenue_range < avg * 0.5 else "negative" if revenue_range > avg * 1.5 else "neutral"
        },
    ]
    
    # ✅ ENHANCED: Geographic insight with specific segmentation data
    if seg_insights and 'region' in seg_insights:
        region_seg = seg_insights['region']
        insights.append({
            "text": f"Geographic Risk: {region_seg['formatted_top']} total revenue across {region_count} market{'s' if region_count > 1 else ''}. {'Heavy concentration in a single market creates material exposure to regional disruptions — diversification should be a Q2 priority' if region_seg['top_pct'] > 50 else 'Moderate geographic concentration balances focus with portfolio resilience' if region_seg['top_pct'] > 30 else 'Well-diversified geographic revenue base mitigates regional risk exposure'}",
            "sentiment": "negative" if region_seg['top_pct'] > 50 else "positive" if region_seg['top_pct'] < 30 else "neutral"
        })
    elif top_region and top_region_pct > 0:
        insights.append({
            "text": f"Geographic Risk: {top_region} accounts for {top_region_pct:.0f}% of total revenue across {region_count} market{'s' if region_count > 1 else ''}. {'Heavy concentration in a single market creates material exposure to regional disruptions — diversification should be a Q2 priority' if top_region_pct > 50 else 'Moderate geographic concentration balances focus with portfolio resilience' if top_region_pct > 30 else 'Well-diversified geographic revenue base mitigates regional risk exposure'}",
            "sentiment": "negative" if top_region_pct > 50 else "positive" if top_region_pct < 30 else "neutral"
        })
    else:
        insights.append({
            "text": "Geographic Distribution: Revenue is spread across segments without dominant concentration, providing natural diversification against regional market disruptions",
            "sentiment": "positive"
        })
    
    insights.extend([
        {
            "text": f"Performance Stability: Coefficient of variation at {volatility:.1f}% indicates {'elevated variance that may impact cash-flow forecasting accuracy and investor confidence' if volatility > 25 else 'moderate fluctuation within acceptable operational parameters for this business profile' if volatility > 10 else 'exceptional stability supporting predictable financial planning and reliable stakeholder commitments'}",
            "sentiment": "negative" if volatility > 25 else "positive" if volatility < 10 else "neutral"
        },
        {
            "text": f"Data Confidence: Analysis based on {row_count} measurement intervals provides {'statistically robust' if row_count > 20 else 'adequate' if row_count > 10 else 'preliminary'} confidence levels. {'Results should be validated with extended time series for strategic decision-making' if row_count < 10 else 'Sample size supports reliable trend identification and forward projection'}",
            "sentiment": "positive" if row_count > 15 else "neutral" if row_count > 5 else "negative"
        },
    ])
    
    # Momentum insight (if enough data)
    if recent_momentum:
        insights.append({
            "text": f"Recent Trajectory: Comparing recent periods against earlier performance shows the business is {recent_momentum}. {'This positive momentum compounds over time and should be reinforced with continued investment' if 'accelerat' in recent_momentum else 'Management should investigate root causes and implement corrective measures before deceleration becomes structural' if 'decelerat' in recent_momentum else 'Maintaining trajectory requires disciplined execution of current strategy'}",
            "sentiment": "positive" if "accelerat" in recent_momentum else "negative" if "decelerat" in recent_momentum else "neutral"
        })
    else:
        insights.append({
            "text": f"Market Position: Total revenue of {currency}{total:,.0f} {'positions the organization competitively within its segment' if total > avg * row_count * 0.8 else 'suggests opportunity for market share expansion through targeted growth initiatives'}. {'Strong average performance indicates pricing power and demand resilience' if avg > median else 'Consistent median performance provides a stable revenue baseline for strategic planning'}",
            "sentiment": "neutral"
        })
    
    # ── Build Enhanced Recommendations (6 total) ──
    recommendations = [
        f"{'Capitalize on Growth Momentum: Accelerate investment in proven revenue drivers, Scale top-performing channels by 20-30% and allocate dedicated resources to replicate success patterns across underperforming segments' if growth > 10 else 'Stabilize Revenue Base: Implement operational efficiency programs targeting 10-15% cost reduction while preserving revenue capacity. Prioritize quick-win optimizations in the first 60 days' if growth < 0 else 'Strategic Expansion: Pursue selective growth opportunities through market development and product optimization. Target 5-10% incremental growth through controlled expansion initiatives'}",
        
        f"{'Geographic Diversification: Reduce dependency on ' + top_region + ' (currently ' + f'{top_region_pct:.0f}' + '% of revenue) by developing 2-3 secondary markets. Set a 12-month target to bring top-market concentration below 40%' if top_region and top_region_pct > 40 else 'Market Penetration: Deepen engagement in existing markets through customer expansion strategies. Target 15-20% revenue uplift from current accounts through upselling and cross-selling programs'}",
        
        f"Forecasting & Planning: Deploy {'conservative scenario-based' if volatility > 20 else 'balanced probabilistic' if volatility > 10 else 'confident linear'} forecasting models calibrated to the observed {volatility:.1f}% revenue variance. Establish {'monthly' if volatility > 20 else 'quarterly'} forecast review cadence with variance analysis",
        
        f"Board Governance: Establish {'monthly' if growth < -5 or volatility > 25 else 'quarterly'} performance reviews with executive visibility dashboards tracking revenue KPIs, growth trajectory, and{'geographic concentration metrics' if top_region else ' market share indicators'}. Set early-warning thresholds for proactive intervention",
        
        f"Data-Driven Decision Making: {'Expand data collection to 20+ periods to strengthen statistical confidence and enable predictive modeling' if row_count < 15 else 'Leverage the robust dataset to build predictive models and scenario analyses for strategic planning'}. Invest in analytics infrastructure to support real-time performance monitoring",
        
        f"Risk Mitigation: Develop contingency plans addressing {'revenue concentration risk, performance volatility, and growth sustainability' if growth > 15 else 'market contraction risk, competitive displacement, and operational efficiency gaps' if growth < 0 else 'market maturity, competitive intensity, and incremental growth challenges'}. Quarterly stress-testing should validate strategic assumptions"
    ]
    
    # ── Build Enhanced Q&A (5 total) ──
    qa = [
        {
            "q": "What factors are driving current revenue performance?",
            "a": f"The {trend.lower()} trend reflects {'strong market demand, effective go-to-market execution, and positive customer acquisition dynamics' if growth > 10 else 'stable competitive positioning with established market presence' if abs(growth) < 5 else 'market challenges requiring strategic adjustment and operational review'}. Period-over-period analysis reveals {abs(growth):.1f}% {'expansion' if growth > 0 else 'contraction'}, {'substantially exceeding' if abs(growth) >= 15 else 'aligned with' if 5 < abs(growth) < 15 else 'below'} typical industry patterns. Average period revenue of {currency}{avg:,.0f} {'demonstrates strong pricing power' if avg > median * 1.1 else 'reflects consistent demand patterns'}."
        },
        {
            "q": "How sustainable is this performance trajectory?",
            "a": f"Sustainability assessment: Revenue volatility of {volatility:.1f}% indicates {'high variability that poses material risk to forward planning — management should implement hedging or diversification strategies' if volatility > 25 else 'moderate fluctuations within manageable bounds for this business profile' if volatility > 10 else 'exceptional consistency that strongly supports reliable multi-quarter planning'}. {'The performance range of ' + currency + f'{revenue_range:,.0f} between peak and trough periods ' + ('warrants further investigation into cyclical or seasonal drivers' if revenue_range > avg else 'confirms operational consistency') + '.'}  {trend_outlook}."
        },
        {
            "q": "What strategic priorities should the board focus on?",
            "a": f"Priority 1: {'Scale growth engines — current momentum provides a window for market share capture before competitive response' if growth > 10 else 'Revenue stabilization through operational excellence and customer retention programs' if growth < 0 else 'Strategic positioning through selective investment in high-potential growth vectors'}. Priority 2: {'Reduce geographic concentration risk through systematic market diversification' if top_region and top_region_pct > 40 else 'Deepen market penetration in existing territories to maximize revenue per account'}. Priority 3: Enhance forecasting precision with {'expanded data collection and scenario modeling' if row_count < 15 else 'advanced predictive analytics leveraging the robust historical dataset'}."
        },
        {
            "q": "What risks demand immediate stakeholder attention?",
            "a": f"Three key risk vectors require monitoring: (1) {'Revenue geographic concentration — ' + top_region + ' represents ' + f'{top_region_pct:.0f}' + '% of total revenue, creating single-market exposure' if top_region and top_region_pct > 30 else 'Market fragmentation — revenue spread across segments may dilute competitive focus'}. (2) {'Elevated performance volatility at ' + f'{volatility:.1f}' + '% — this level of variance can impact investor confidence and operational planning accuracy' if volatility > 20 else 'Performance variance at ' + f'{volatility:.1f}' + '% — within acceptable bounds but warrants ongoing monitoring'}. (3) {'Growth sustainability — maintaining ' + f'{abs(growth):.1f}' + '% growth requires continuous investment and market expansion' if growth > 10 else 'Competitive pressure — current trajectory suggests vulnerability to market disruption' if growth < 0 else 'Growth acceleration — breaking out of current stable trajectory requires strategic initiative beyond business-as-usual operations'}."
        },
        {
            "q": "What is the recommended investment thesis based on this data?",
            "a": f"Based on {row_count} data points showing {currency}{total:,.0f} total revenue with {abs(growth):.1f}% {'growth' if growth > 0 else 'contraction'}: {'GROWTH THESIS — Strong performance metrics justify increased capital allocation. Focus investment on expanding proven revenue channels and entering adjacent markets. The current growth rate supports a 2-3x revenue expansion target over 18-24 months with appropriate resourcing.' if growth > 10 else 'OPTIMIZATION THESIS — Stable fundamentals warrant operational investment rather than aggressive expansion. Focus on margin improvement, customer retention, and selective growth initiatives with clear ROI visibility. Target 10-15% efficiency gain within 12 months.' if abs(growth) < 5 else 'TURNAROUND THESIS — Declining metrics require immediate intervention. Prioritize cost structure review, customer churn analysis, and competitive repositioning. The first 90 days should focus on stabilization before any growth investment.' if growth < -5 else 'BALANCED THESIS — Moderate growth supports measured expansion investment. Allocate resources to both organic growth acceleration and operational optimization. Target 15-25% growth improvement within 12 months through combined initiatives.'}"
        }
    ]
    
    return {
        "summary": summary,
        "insights": insights,
        "recommendations": recommendations,
        "qa": qa,
        "type": "statistical"
    }

def generate_ai_enhanced_insights(project):
    """AI-enhanced insights — cascading fallback: OpenAI → Gemini → Groq"""
    if not ai_providers.is_ai_available():
        raise RuntimeError("AI_UNAVAILABLE: No AI providers configured. Set OPENAI_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY.")
    
    try:
        currency = project.get("currency", "$")
        
        # Extended context from comprehensive analysis
        comp = project.get("comprehensive_analysis", {})
        validation = project.get("data_validation", {})
        
        # Build context string for the AI
        context_str = ""
        
        # Add segmentation details if available
        if comp and comp.get('segmentation'):
            context_str += "\nDETAILED SEGMENTATION:\n"
            seg = comp['segmentation']
            for metric, dims in seg.items():
                for dim, data in dims.items():
                    if data.get('top_performer'):
                        top = data['top_performer']
                        context_str += f"- Top {dim}: {top['name']} ({ea.format_currency(top['value'], currency)}, {top['pct']:.1f}%)\n"
                    if data.get('bottom_performer'):
                        bot = data['bottom_performer']
                        context_str += f"- Bottom {dim}: {bot['name']} ({ea.format_currency(bot['value'], currency)}, {bot['pct']:.1f}%)\n"
        
        # Add period comparison if available
        if comp and comp.get('period_comparison'):
            pc = comp['period_comparison']
            period_type = comp.get('column_detection', {}).get('period_type', 'period')
            context_str += f"\nPERIOD COMPARISON ({period_type} over {period_type}):\n"
            context_str += f"- Current: {ea.format_currency(pc.get('current', 0), currency)}\n"
            context_str += f"- Previous: {ea.format_currency(pc.get('previous', 0), currency)}\n"
            context_str += f"- Change: {pc.get('percent_change', 0):+.1f}% ({pc.get('direction', 'flat')})\n"
        
        # Add forecast if available
        if comp and comp.get('forecast'):
            fc = comp['forecast']
            context_str += f"\nFORECAST:\n"
            context_str += f"- Next Period Prediction: {ea.format_currency(fc.get('next_period_value', 0), currency)}\n"
            context_str += f"- Trend Direction: {fc.get('trend_direction', 'unknown')}\n"

        # Add multi-KPI context
        kpi_metrics = project.get('kpi_metrics', {})
        if kpi_metrics:
            context_str += "\nDETECTED KPIs:\n"
            for name, info in kpi_metrics.items():
                context_str += f"- {info.get('label', name)}: Total {ea.format_currency(info.get('total', 0), currency)}, Growth {info.get('growth', 0):+.1f}%, Trend: {info.get('trend', 'N/A')}\n"

        # Framework-specific instructions
        framework_focus = ""
        framework = project.get("analysis_framework", "general")
        if framework == "profitability":
            framework_focus = "Focus on margin waterfalls, unit economics, and cost-to-revenue ratios."
        elif framework == "market_entry":
            framework_focus = "Focus on market size (TAM/SAM/SOM), competitive positioning, and entry barriers."
        elif framework == "cost_reduction":
            framework_focus = "Focus on operational inefficiencies, overhead bloat, and process simplification."

        prompt = f"""You are a senior management consultant from a top-tier firm (McKinsey/BCG/Bain). 
Preparing board-level analysis using the SCQA (Situation-Complication-Question-Answer) framework.

STRATEGIC CONTEXT:
- Analysis Framework: {framework}
- {framework_focus}

BUSINESS METRICS:
- Primary KPI Total: {currency}{project.get('total_revenue', 0):,.2f}
- Average per Period: {currency}{project.get('avg_revenue', 0):,.2f}
- Growth Rate: {project.get('growth_rate', 0):+.1f}%
- Trend: {project.get('trend', 'Unknown')}
- Sample Size: {project.get('row_count', 0)} periods

{context_str}

Provide executive-grade insights in VALID JSON format.
The 'summary' field MUST use the following pattern using HTML formatting:
<strong>SITUATION:</strong> [The background/context]<br/><br/>
<strong>COMPLICATION:</strong> [The core challenge or change identified in data]<br/><br/>
<strong>QUESTION:</strong> [The strategic question the board must answer]<br/><br/>
<strong>ANSWER:</strong> [Your data-driven recommendation]

JSON Structure:
{{
  "summary": "SCQA formatted text blocks as described above.",
  "insights": [
    {{"text": "consulting-grade insight 1 — cite specific numbers", "sentiment": "positive"}},
    {{"text": "insight 2 — negative or risk-based", "sentiment": "negative"}},
    ... total 6 insights
  ],
  "recommendations": [
    "strategic recommendation 1 with action steps",
    ... total 5 recommendations
  ],
  "qa": [
    {{"q": "strategic question", "a": "detailed answer referencing data"}},
    {{"q": "risk analysis", "a": "..."}},
    {{"q": "sustainability", "a": "..."}},
    {{"q": "action plan", "a": "..."}}
  ]
}}

Deliver the narrative in an elite, decisive tone. Reference actual decimal percentages and rounded currency values."""

        # ── Multi-provider fallback chain ──
        content = ai_providers.get_ai_response(prompt, temperature=0.3)
        
        if content is None:
            raise RuntimeError("AI_FAILED: All AI providers exhausted. Falling back to statistical insights.")
        
        # Robust JSON extraction — handle markdown fences, extra text, etc.
        import re
        raw = content.strip()
        
        # Strip markdown code fences (```json ... ``` or ``` ... ```)
        fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', raw, re.DOTALL)
        if fence_match:
            raw = fence_match.group(1).strip()
        
        # Sanitize control characters inside JSON strings (Llama/Groq puts literal 
        # newlines inside string values around <br/> tags, breaking json.loads)
        # Replace literal newlines/tabs that aren't structural JSON whitespace
        def _sanitize_json_string(s):
            """Remove literal control chars from inside JSON string values."""
            # First try as-is
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                pass
            # Replace literal newlines/tabs within strings with spaces
            sanitized = re.sub(r'(?<=": ")(.*?)(?="[,\s*}])', 
                             lambda m: m.group(0).replace('\n', ' ').replace('\r', ' ').replace('\t', ' '),
                             s, flags=re.DOTALL)
            # If that doesn't work, brute-force: replace all control chars except structural ones
            try:
                return json.loads(sanitized)
            except json.JSONDecodeError:
                pass
            # Nuclear option: remove ALL control characters except those in JSON structure
            cleaned = re.sub(r'[\x00-\x1f\x7f]', ' ', s)
            return json.loads(cleaned)
        
        # Try direct parse first
        try:
            ai_result = _sanitize_json_string(raw)
        except json.JSONDecodeError:
            # Fallback: find the first { ... } block in the response
            brace_match = re.search(r'\{.*\}', raw, re.DOTALL)
            if brace_match:
                try:
                    ai_result = _sanitize_json_string(brace_match.group(0))
                except json.JSONDecodeError as e2:
                    logger.error(f"AI JSON extraction failed. Raw content (first 500 chars): {raw[:500]}")
                    raise RuntimeError(f"AI_FAILED: AI returned invalid JSON — {str(e2)}")
            else:
                logger.error(f"No JSON found in AI response. Raw content (first 500 chars): {raw[:500]}")
                raise RuntimeError("AI_FAILED: AI response did not contain valid JSON")
        
        ai_result["type"] = "ai"
        logger.info(f"AI insights generated for project {project['id']}")
        return ai_result
        
    except json.JSONDecodeError as e:
        logger.error(f"AI response was not valid JSON: {e}")
        raise RuntimeError(f"AI_FAILED: AI returned invalid JSON — {str(e)}")
    except Exception as e:
        logger.error(f"AI generation failed: {e}")
        raise RuntimeError(f"AI_FAILED: {str(e)}")    


def chart_narratives(project):
    """
    Deterministic chart explanations for UI & PDF
    """
    narratives = {}

    narratives["revenue"] = (
        "This chart highlights revenue evolution over time and helps evaluate growth momentum, "
        "stability, and predictability of cash flows."
    )

    if project.get("top_region"):
        narratives["region"] = (
            f"Revenue concentration in {project['top_region']} indicates a strong core market "
            "but increases exposure to regional demand fluctuations."
        )
    else:
        narratives["region"] = (
            "Revenue is diversified across regions, reducing dependency risk on a single market."
        )

    narratives["volatility"] = (
        "Observed revenue variability provides insight into earnings stability and operational risk."
    )

    return narratives



# ==================== CHART STYLING SETUP ====================
sns.set_style("whitegrid")
plt.rcParams['font.size'] = 11
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14

# ==================== CHART GENERATION FUNCTIONS ====================

def generate_revenue_chart(project):
    """
    Generate ELITE consulting-grade revenue trend chart
    
    Args:
        project: Project dictionary with revenue_series data
    
    Returns:
        str: Path to generated chart image
    """
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"revenue_{project['id']}.png"

    # Create figure with premium sizing
    fig, ax = plt.subplots(figsize=(14, 7), facecolor='white')
    
    revenue_data = project["revenue_series"]
    x_axis = list(range(1, len(revenue_data) + 1))
    
    # ELITE DESIGN: Gradient bar chart with sophisticated styling
    colors = ['#1e3a8a', '#2563eb', '#3b82f6', '#60a5fa', '#93c5fd']  # Blue gradient
    bar_colors = [colors[i % len(colors)] for i in range(len(revenue_data))]
    
    # Create bars with gradient effect
    bars = ax.bar(x_axis, revenue_data, color=bar_colors, width=0.7, 
                   edgecolor='#1e293b', linewidth=2, alpha=0.9)
    
    # Add subtle shadow effect (premium feel)
    for i, (bar, value) in enumerate(zip(bars, revenue_data)):
        height = bar.get_height()
        # Add value labels on top of bars
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{project["currency"]}{value:,.0f}',
                ha='center', va='bottom', fontsize=11, fontweight='600',
                color='#0f172a')
        
        # Add gradient effect to bars
        gradient = np.linspace(0.6, 1.0, 100).reshape(100, 1)
        ax.imshow(gradient, extent=[bar.get_x(), bar.get_x() + bar.get_width(),
                  0, height], aspect='auto', alpha=0.3, cmap='Blues', zorder=0)
    
    # Add trend line (elegant overlay)
    z = np.polyfit(x_axis, revenue_data, 1)
    poly = np.poly1d(z)
    ax.plot(x_axis, poly(x_axis), "--", alpha=0.7, color='#059669', 
            linewidth=3, label='Growth Trend', zorder=5)
    
    # PREMIUM STYLING
    ax.set_title(f"Revenue Performance Analysis - {project.get('trend', 'Trending')}", 
                 fontsize=18, fontweight='bold', pad=25, color='#0f172a',
                 fontfamily='sans-serif')
    ax.set_xlabel("Period", fontsize=14, fontweight='600', color='#334155')
    ax.set_ylabel(f"Revenue ({project['currency']})", fontsize=14, fontweight='600', color='#334155')
    
    # Sophisticated grid
    ax.grid(True, axis='y', alpha=0.2, linestyle='-', linewidth=0.8, color='#cbd5e1')
    ax.set_axisbelow(True)
    
    # Clean spines (McKinsey-style)
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)
    ax.spines['left'].set_color('#cbd5e1')
    ax.spines['bottom'].set_color('#cbd5e1')
    
    # Format y-axis with currency
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, p: f"{project['currency']}{x:,.0f}")
    )
    
    # Legend with premium styling
    ax.legend(loc='upper left', framealpha=0.95, edgecolor='#cbd5e1', 
              fancybox=True, shadow=True, fontsize=11)
    
    plt.tight_layout(pad=2.0)
    plt.savefig(str(path), dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()

    return f"/static/charts/revenue_{project['id']}.png"

def generate_region_chart(project):
    """
    Generate regional revenue distribution bar chart
    
    Args:
        project: Project dictionary with regional data
    
    Returns:
        str: Path to generated chart image, or None if no regional data
    """
    if not project.get("region_labels"):
        return None

    CHART_DIR.mkdir(parents=True, exist_ok=True)
    path = CHART_DIR / f"region_{project['id']}.png"

    fig, ax = plt.subplots(figsize=(12, 6))
    
    labels = project["region_labels"]
    values = project["region_values"]
    colors_palette = sns.color_palette("viridis", len(labels))
    
    # Create bar chart
    bars = ax.bar(labels, values, color=colors_palette, alpha=0.8, 
                   edgecolor='white', linewidth=2)
    
    # Add value labels on top of bars
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{project["currency"]}{height:,.0f}',
                ha='center', va='bottom', fontsize=10, fontweight='bold')
    
    # Styling
    ax.set_title("Revenue Distribution by Region", fontsize=16, fontweight='bold', pad=20)
    ax.set_xlabel("Region", fontsize=13)
    ax.set_ylabel(f"Revenue ({project['currency']})", fontsize=13)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda x, p: f"{project['currency']}{x:,.0f}")
    )
    
    plt.xticks(rotation=45, ha='right')
    ax.grid(True, alpha=0.3, axis='y', linestyle='--')
    
    plt.tight_layout()
    plt.savefig(str(path), dpi=150, bbox_inches='tight', facecolor='white')
    plt.close()

    return f"/static/charts/region_{project['id']}.png"

# ==================== EXPORT FUNCTIONS (imported from exports module) ====================

from exports.export_functions import export_pdf_enhanced, export_ppt_enhanced, export_docx_enhanced

logger.info("✅ Export functions loaded from exports.export_functions")

# ==================== MODULAR ROUTES ====================
import sys
from routes import auth as auth_routes
from routes import exports as export_routes
from routes import admin as admin_routes
from routes import payments as payment_routes
from routes import agent as agent_routes
from routes import analytics as analytics_routes

# Wire shared state into route modules
_this = sys.modules[__name__]
auth_routes.setup(_this)
export_routes.setup(_this)
admin_routes.setup(_this)
payment_routes.setup(_this)
agent_routes.setup(_this)
analytics_routes.setup(_this)  # needs: db, templates, require_user, ea, ai_providers

# Include routers
app.include_router(auth_routes.router)
app.include_router(export_routes.router)
app.include_router(admin_routes.router)
app.include_router(payment_routes.router)
app.include_router(agent_routes.router)
app.include_router(analytics_routes.router)

logger.info("✅ Modular routes loaded: auth, exports, admin, payments, agent, analytics")

# ==================== MAIN ROUTES ====================

@app.get("/")
async def index(request: Request):
    """
    Homepage - Shows landing page or dashboard based on auth status
    """
    user_session = request.session.get("user")
    
    if not user_session:
        return templates.TemplateResponse(request=request, name="landing.html", context= {"request": request})
    
    # User is logged in - prepare dashboard data
    email = user_session["email"]
    
    # Check if it's a database user (has 'id') or demo user
    if "id" in user_session:
        # Fetch fresh data from DB
        db_user = db.get_user_by_id(user_session["id"])
        
        # Get projects from DB
        user_projects = db.get_user_projects(user_session["id"])
        
        # Prepare context with DB data
        context = {
            "request": request,
            "user": user_session,
            "projects": user_projects,  # Real DB projects
            "stats": {
                "uploads_used": db_user["uploads"],
                "ai_generations_used": db_user["ai_used"],
                "ai_regens_used": db_user["ai_regens"]
            },
            "PLAN_LIMITS": PLAN_LIMITS,
            "is_demo": False
        }
        return templates.TemplateResponse(request=request, name="dashboard.html", context= context)
        
    else:
        # Legacy/Demo user (in-memory)
        demo_user = users.get(email)
        if not demo_user:
            # Session exists but user gone (server restart)
            request.session.clear()
            return RedirectResponse("/", status_code=303)
            
        # Filter in-memory projects for this user
        # Note: older code might use list or dict for projects, adapting to list search
        user_projects_list = [p for p in projects if p.get("user_email") == email]
        
        context = {
            "request": request,
            "user": user_session,
            "projects": user_projects_list,
            "stats": {
                "uploads_used": demo_user["uploads_used"],
                "ai_generations_used": demo_user["ai_generations_used"],
                "ai_regens_used": demo_user["ai_regens_used"]
            },
            "PLAN_LIMITS": PLAN_LIMITS,
            "is_demo": True
        }
        return templates.TemplateResponse(request=request, name="dashboard.html", context= context)

# ==================== AUTH ROUTES → routes/auth.py ====================
# Login, register, logout, demo login, and pricing routes
# have been moved to routes/auth.py for maintainability.

# ==================== PROJECT/REPORT ROUTES ====================

@app.get("/report/{pid}")
def report(pid: int, request: Request, user=Depends(require_user)):
    """
    Display individual project report
    
    Args:
        pid: Project ID
    """
    user_email = user["email"]
    
    if "id" in user:
        # DB User
        project = db.get_project(pid, user["id"])
        db_user = db.get_user_by_id(user["id"])
        stats = {
            "uploads_used": db_user["uploads"] if db_user else 0,
            "ai_generations_used": db_user["ai_used"] if db_user else 0,
            "ai_regens_used": db_user["ai_regens"] if db_user else 0,
        }
    else:
        # Demo User
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
        user_data = users.get(user_email, {})
        stats = {
            "uploads_used": user_data.get("uploads_used", 0),
            "ai_generations_used": user_data.get("ai_generations_used", 0),
            "ai_regens_used": user_data.get("ai_regens_used", 0),
        }
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    return templates.TemplateResponse(request=request, name="report.html", context= {
        "request": request,
        "report": project,
        "user": user,
        "stats": stats,
        "users": users,
        "PLAN_LIMITS": PLAN_LIMITS
    })
    
@app.post("/project/create")
async def create_project(request: Request, user=Depends(require_user)):
    """
    Create a new project for the user
    """
    global next_project_id, projects
    
    user_email = user["email"]
    
    if "id" in user:
        # DB User
        # Generate a distinct name
        existing_count = len(db.get_user_projects(user["id"]))
        client_name = f"New Report #{existing_count + 1}"
        
        project_id = db.create_project(user["id"], client_name)
        log(f"New project created (DB): {project_id} by {user_email}")
        return RedirectResponse(f"/report/{project_id}", status_code=303)
        
    else:
        # Demo User (Legacy)
        new_project = {
            "id": next_project_id,
            "user_email": user_email,
            "client": f"New Report #{next_project_id}",
            "period": datetime.now().strftime("%B %Y"),
            "uploads": 0,
            "ai_used": False,
            "ai_regens": 0,
            "currency": DEFAULT_CURRENCY,
            "generated": False
        }
        
        projects.append(new_project)
        next_project_id += 1
        
        log(f"New project created (DEMO): {new_project['id']} by {user_email}")
        
        # Redirect to the new project
        return RedirectResponse(f"/report/{new_project['id']}", status_code=303)

@app.post("/upload/{pid}")
async def upload(
    pid: int,
    request: Request,
    file: UploadFile = File(...),
    currency: str = Form(DEFAULT_CURRENCY),
    analysis_type: str = Form("standard"),
    analysis_framework: str = Form("general"),
    user=Depends(require_user)
):
    """
    Handle CSV/Excel file upload and processing
    
    Args:
        pid: Project ID
        file: Uploaded CSV or Excel file (.csv, .xlsx, .xls)
        currency: Currency symbol for the report
        analysis_type: 'standard' or 'ai_enhanced'
    """
    user_email = user["email"]
    is_db_user = "id" in user
    
    # ── Dual-path project lookup ──
    if is_db_user:
        project = db.get_project(pid, user["id"])
    else:
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    log(f"Upload received for project {pid} by user {user_email}")

    # Read file content
    content = await file.read()
    if len(content) == 0:
        project["error"] = "The uploaded file is empty. Please select a file with data."
        if is_db_user:
            db.update_project(pid, user["id"], error=project["error"])
        return RedirectResponse(f"/report/{pid}", 303)
    if len(content) > MAX_FILE_SIZE:
        project["error"] = f"File too large (max {MAX_FILE_SIZE // 1_000_000}MB)"
        if is_db_user:
            db.update_project(pid, user["id"], error=project["error"])
        return RedirectResponse(f"/report/{pid}", 303)

    # Check upload limits based on user's plan
    plan = get_user_plan(request)
    upload_limit = PLAN_LIMITS[plan]["max_uploads"]
    
    # Get current upload count
    if is_db_user:
        db_user = db.get_user_by_id(user["id"])
        current_uploads = db_user["uploads"] if db_user else 0
    else:
        user_data = users.get(user_email, {})
        current_uploads = user_data.get("uploads_used", 0)
    
    if upload_limit is not None and current_uploads >= upload_limit:
        project["error"] = f"{plan.capitalize()} plan upload limit reached ({upload_limit} uploads). Upgrade your plan for more."
        if is_db_user:
            db.update_project(pid, user["id"], error=project["error"])
        return RedirectResponse(f"/report/{pid}", 303)

    # Reset project data
    reset_project(project)
    project["currency"] = currency
    project["analysis_framework"] = analysis_framework

    # Save uploaded file persistently to uploads/ for Copilot access
    temp_file = None
    filename = file.filename.lower() if file.filename else ""
    is_excel = filename.endswith(('.xlsx', '.xls'))
    suffix = '.xlsx' if is_excel else '.csv'
    
    try:
        temp_file = tempfile.NamedTemporaryFile(mode='wb', delete=False, suffix=suffix)
        temp_file.write(content)
        temp_file.close()
        
        # Read file with pandas (CSV or Excel)
        if is_excel:
            df = pd.read_excel(temp_file.name)
            log(f"Excel file loaded: {filename}")
        else:
            df = pd.read_csv(temp_file.name)
            log(f"CSV file loaded: {filename}")
    except Exception as e:
        log(f"File read failed: {e}")
        project["error"] = "Invalid file. Please check format and try again. Supported: CSV, Excel (.xlsx, .xls)"
        if temp_file:
            cleanup_temp_file(temp_file.name)
        return RedirectResponse(f"/report/{pid}", 303)

    # Copy to persistent location so Copilot can access it after redeploys
    persistent_filename = f"upload_{pid}{suffix}"
    persistent_path = UPLOAD_DIR / persistent_filename
    try:
        shutil.copy2(temp_file.name, str(persistent_path))
        project["last_uploaded_file"] = str(persistent_path)
        log(f"File persisted to {persistent_path}")
    except Exception as e:
        logger.warning(f"Could not persist upload: {e}")
        project["last_uploaded_file"] = temp_file.name
    project["available_columns"] = list(df.columns)
    
    # Smart column detection — find all metrics and dimensions
    detected = ea.detect_column_types(df)
    all_metrics = detected.get('metrics', [])
    all_dimensions = detected.get('dimensions', [])
    
    # Best-guess revenue column
    rev_col = None
    for col in all_metrics:
        if any(p in col.lower() for p in ['revenue', 'sales', 'income', 'turnover']):
            rev_col = col
            break
    if not rev_col:
        rev_col = all_metrics[0] if all_metrics else df.columns[0]
    
    # Best-guess region column
    reg_col = None
    for col in all_dimensions:
        if any(p in col.lower() for p in ['region', 'country', 'state', 'city', 'market', 'territory', 'area']):
            reg_col = col
            break
    if not reg_col and all_dimensions:
        reg_col = all_dimensions[0]
    
    project["column_map"] = {
        "revenue": rev_col,
        "region": reg_col,
        "metrics": all_metrics,
        "dimensions": all_dimensions,
    }

    # Validate the dataframe for edge cases
    rev_col = project["column_map"]["revenue"]
    reg_col = project["column_map"].get("region")
    
    is_valid, error_msg, cleaned_df = validate_dataframe(df, rev_col, reg_col)
    
    if not is_valid:
        log(f"DataFrame validation failed: {error_msg}")
        project["error"] = error_msg
        cleanup_temp_file(temp_file.name)
        return RedirectResponse(f"/report/{pid}", 303)
    
    # Use the cleaned dataframe
    df = cleaned_df

    # Process the dataframe
    try:
        process_dataframe(project, df)
    except Exception as e:
        log(f"DataFrame processing failed: {e}")
        project["error"] = "Error processing data. Please check your file and try again."
        cleanup_temp_file(temp_file.name)
        return RedirectResponse(f"/report/{pid}", 303)

    # Generate charts
    try:
        project["revenue_chart"] = generate_revenue_chart(project)
        if project.get("region_labels"):
            project["region_chart"] = generate_region_chart(project)
    except Exception as e:
        logger.error(f"Chart generation failed: {e}", exc_info=True)

    project["chart_narratives"] = chart_narratives(project)

# ================= INSIGHT GENERATION (USER-CONTROLLED) =================
    plan = get_user_plan(request)
    
    if analysis_type == "ai_enhanced" and plan == "pro":
        # Pro user chose AI-Enhanced analysis
        ai_limit = PLAN_LIMITS[plan]["max_ai_generations"]
        
        # Fetch fresh usage stats
        current_ai_usage = 0
        if is_db_user:
            fresh_db_user = db.get_user_by_id(user["id"])
            if fresh_db_user:
                current_ai_usage = int(fresh_db_user.get("ai_used", 0))
        else:
            demo_user_rec = users.get(user_email)
            if demo_user_rec:
                current_ai_usage = demo_user_rec.get("ai_generations_used", 0)

        if ai_limit is None or current_ai_usage < ai_limit:
            try:
                insights = generate_ai_enhanced_insights(project)
                log(f"AI-Enhanced analysis generated for project {pid}")
            except RuntimeError as e:
                # AI failed — tell the user honestly, give them standard instead
                error_msg = str(e)
                if "AI_UNAVAILABLE" in error_msg:
                    project["error"] = "⚠️ AI service is currently unavailable. Your report was generated with our consulting-grade Standard Analysis. You can retry AI-Enhanced analysis later."
                else:
                    project["error"] = "⚠️ AI analysis encountered an error. Your report was generated with consulting-grade Standard Analysis instead. Please try AI-Enhanced again — your AI usage was not counted."
                insights = generate_statistical_insights(project)
                log(f"AI failed for project {pid}, using standard with user notification: {e}")
        else:
            insights = generate_statistical_insights(project)
            project["error"] = "AI generation limit reached. Generated standard analysis instead."
            log(f"AI limit reached, falling back to standard for project {pid}")
    else:
        # Standard analysis (default for all users)
        insights = generate_statistical_insights(project)
        log(f"Standard consulting analysis generated for project {pid}")

    project["ai_summary"] = insights["summary"]
    project["ai_insights"] = insights["insights"]
    project["ai_recommendations"] = insights["recommendations"]
    project["ai_qa"] = insights["qa"]
    project["report_type"] = insights.get("type", "statistical")

    if insights.get("type") == "ai":
        project["ai_used"] = True
        if is_db_user:
            db.update_user_stats(user["id"], ai_used=True)
        else:
            user_data = users.get(user_email, {})
            user_data["ai_generations_used"] = user_data.get("ai_generations_used", 0) + 1
            users[user_email] = user_data

    # ================= FINALIZE REPORT =================
    project["confidence_score"] = calculate_confidence(project)
    project["generated"] = True
    project["generated_at"] = datetime.now().strftime("%B %d, %Y at %I:%M %p")

    # Persist changes
    if is_db_user:
        # Prepare DB fields (including new ones)
        db_fields = {
            'currency': project.get('currency'),
            'total_revenue': project.get('total_revenue', 0),
            'avg_revenue': project.get('avg_revenue', 0),
            'median_revenue': project.get('median_revenue', 0),
            'growth_rate': project.get('growth_rate', 0),
            'trend': project.get('trend'),
            'top_region': project.get('top_region'),
            'row_count': project.get('row_count', 0),
            'confidence': project.get('confidence_score', 0),
            'revenue_series': project.get('revenue_series'),
            'region_labels': project.get('region_labels'),
            'region_values': project.get('region_values'),
            'ai_summary': project.get('ai_summary'),
            'ai_insights': project.get('ai_insights'),
            'ai_recommendations': project.get('ai_recommendations'),
            'ai_qa': project.get('ai_qa'),
            'revenue_chart': project.get('revenue_chart'),
            'region_chart': project.get('region_chart'),
            'chart_narratives': project.get('chart_narratives'),
            'available_columns': project.get('available_columns'),
            'column_map': project.get('column_map'),
            'report_type': project.get('report_type', 'statistical'),
            'kpi_metrics': project.get('kpi_metrics'),
            'primary_kpi': project.get('primary_kpi'),
            'report_title': project.get('report_title'),
            'analysis_framework': project.get('analysis_framework'),
            'hypotheses': project.get('hypotheses'),
            'working_theory': project.get('working_theory'),
            'generated': True,
            'error': project.get('error'),
        }
        # Update project in DB
        db.update_project(pid, user["id"], **db_fields)
        # Update user upload count
        db.update_user_stats(user["id"], uploads=current_uploads + 1)
    else:
        # In-memory user logic
        project["uploads"] = current_uploads + 1
        if user_email in users:
            users[user_email]["uploads_used"] = current_uploads + 1

    cleanup_temp_file(temp_file.name)
    return RedirectResponse(f"/report/{pid}", 303)

@app.post("/project/save_theory/{pid}")
async def save_theory(
    pid: int,
    request: Request,
    working_theory: str = Form(...),
    user=Depends(require_user)
):
    """
    Save consultant's qualitative working theory
    """
    is_db_user = "id" in user
    user_email = user["email"]
    
    if is_db_user:
        db.update_project(pid, user["id"], working_theory=working_theory)
    else:
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
        if project:
            project["working_theory"] = working_theory
            
    return RedirectResponse(f"/report/{pid}", 303)


@app.post("/demo/{pid}")
async def load_demo(pid: int, request: Request, user=Depends(require_user)):
    """
    Load demo data into a project
    
    Args:
        pid: Project ID
    """
    user_email = user["email"]
    is_db_user = "id" in user
    
    # Dual-path project lookup
    if is_db_user:
        project = db.get_project(pid, user["id"])
    else:
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
    
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Create demo CSV data
    demo_data = """revenue,region
1200,US
1350,EU
1420,APAC
1280,US
1490,EU
1560,APAC
1310,US
1580,EU
1640,APAC
1450,US
1520,EU
1670,APAC"""
    
    # Save demo CSV persistently so Copilot can access it later
    persistent_demo_path = UPLOAD_DIR / f"demo_{pid}.csv"
    with open(str(persistent_demo_path), 'w', newline='') as f:
        f.write(demo_data)
    
    try:
        df = pd.read_csv(str(persistent_demo_path))
        
        reset_project(project)
        project["currency"] = "$"
        project["available_columns"] = list(df.columns)
        project["column_map"] = {"revenue": "revenue", "region": "region"}
        project["last_uploaded_file"] = str(persistent_demo_path)
        
        process_dataframe(project, df)
        
        project["revenue_chart"] = generate_revenue_chart(project)
        project["region_chart"] = generate_region_chart(project)
        project["chart_narratives"] = chart_narratives(project)

        # Generate insights
        plan = get_user_plan(request)
        ai_limit = PLAN_LIMITS[plan]["max_ai_generations"]
        
        # Fetch current AI usage
        current_ai_usage = 0
        if is_db_user:
            db_user = db.get_user_by_id(user["id"])
            if db_user:
                current_ai_usage = int(db_user.get("ai_used", 0))
        else:
            demo_user_rec = users.get(user_email)
            if demo_user_rec:
                current_ai_usage = demo_user_rec.get("ai_generations_used", 0)
        
        if ai_limit is None or current_ai_usage < ai_limit:
            try:
                insights = generate_ai_enhanced_insights(project)
            except Exception:
                insights = generate_statistical_insights(project)
        else:
            insights = generate_statistical_insights(project)

        project["ai_summary"] = insights["summary"]
        project["ai_insights"] = insights["insights"]
        project["ai_recommendations"] = insights["recommendations"]
        project["ai_qa"] = insights["qa"]
        project["report_type"] = insights.get("type", "statistical")

        if insights.get("type") == "ai":
            project["ai_used"] = True
            if is_db_user:
                db.update_user_stats(user["id"], ai_used=current_ai_usage + 1)
            else:
                if user_email in users:
                    users[user_email]["ai_generations_used"] += 1
        else:
            project["ai_used"] = False

        project["confidence_score"] = calculate_confidence(project)
        project["generated"] = True
        project["generated_at"] = datetime.now().strftime("%B %d, %Y at %I:%M %p")
        
        log(f"Demo data loaded for project {pid}")
        
        # Persist ALL fields (including Phase 1/2) to DB
        if is_db_user:
            db_safe_fields = {
                'client': project.get('client'),
                'currency': project.get('currency'),
                'total_revenue': project.get('total_revenue', 0),
                'avg_revenue': project.get('avg_revenue', 0),
                'median_revenue': project.get('median_revenue', 0),
                'growth_rate': project.get('growth_rate', 0),
                'trend': project.get('trend'),
                'top_region': project.get('top_region'),
                'row_count': project.get('row_count', 0),
                'confidence': project.get('confidence_score', 0),
                'revenue_series': project.get('revenue_series'),
                'region_labels': project.get('region_labels'),
                'region_values': project.get('region_values'),
                'ai_summary': project.get('ai_summary'),
                'ai_insights': project.get('ai_insights'),
                'ai_recommendations': project.get('ai_recommendations'),
                'ai_qa': project.get('ai_qa'),
                'revenue_chart': project.get('revenue_chart'),
                'region_chart': project.get('region_chart'),
                'chart_narratives': project.get('chart_narratives'),
                'available_columns': project.get('available_columns'),
                'column_map': project.get('column_map'),
                'report_type': project.get('report_type', 'statistical'),
                'kpi_metrics': project.get('kpi_metrics'),
                'primary_kpi': project.get('primary_kpi'),
                'report_title': project.get('report_title'),
                'analysis_framework': project.get('analysis_framework'),
                'hypotheses': project.get('hypotheses'),
                'working_theory': project.get('working_theory'),
                'last_uploaded_file': str(persistent_demo_path),
                'generated': True,
                'error': project.get('error'),
            }
            db_safe_fields = {k: v for k, v in db_safe_fields.items() if v is not None}
            db.update_project(pid, user["id"], **db_safe_fields)
        
    except Exception as e:
        logger.error(f"Demo data loading failed: {e}", exc_info=True)
        project["error"] = "Failed to load demo data. Please try again."
    
    return RedirectResponse(f"/report/{pid}", 303)

# ==================== PROJECT MANAGEMENT ROUTES ====================

@app.post("/project/rename/{pid}")
async def rename_project(
    pid: int,
    request: Request,
    new_name: str = Form(...),
    user=Depends(require_user)
):
    """Rename a project"""
    user_email = user["email"]
    
    # Sanitize input
    new_name = new_name.strip()[:100]
    if not new_name:
         return RedirectResponse(f"/report/{pid}", 303)

    if "id" in user:
        # DB User
        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        db.update_project(pid, user["id"], client=new_name)
        log(f"Project {pid} renamed to: {new_name} (DB)")
        
    else:
        # Demo User
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
        if not project:
             raise HTTPException(status_code=404, detail="Project not found")
        
        project["client"] = new_name
        log(f"Project {pid} renamed to: {new_name} (DEMO)")
    
    return RedirectResponse(f"/report/{pid}", 303)

@app.post("/project/delete/{pid}")
async def delete_project(pid: int, request: Request, user=Depends(require_user)):
    """Delete a project"""
    global projects
    user_email = user["email"]
    
    if "id" in user:
        # DB User
        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
            
        # Cleanup associated files
        if project.get("last_uploaded_file"):
            cleanup_temp_file(project["last_uploaded_file"])
            
        for chart_key in ["revenue_chart", "region_chart"]:
            if project.get(chart_key):
                chart_path = str(BASE_DIR / project[chart_key].lstrip("/"))
                cleanup_temp_file(chart_path)
        
        db.delete_project(pid, user["id"])
        log(f"Project {pid} deleted by {user_email} (DB)")
        
    else:
        # Demo User
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
        
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        
        # Cleanup associated files
        if project.get("last_uploaded_file"):
            cleanup_temp_file(project["last_uploaded_file"])
        
        for chart_key in ["revenue_chart", "region_chart"]:
            if project.get(chart_key):
                chart_path = str(BASE_DIR / project[chart_key].lstrip("/"))
                cleanup_temp_file(chart_path)
        
        projects = [x for x in projects if x["id"] != pid]
        log(f"Project {pid} deleted by {user_email} (DEMO)")
    
    return RedirectResponse("/", 303)

# ==================== AI REGENERATION ROUTE ====================

@app.post("/ai/regenerate/{pid}")
async def regenerate_ai(pid: int, request: Request, analysis_type: str = Form("standard"), user=Depends(require_user)):
    """Regenerate insights for a project — standard or AI-enhanced"""
    user_email = user["email"]
    
    if "id" in user:
        # DB User
        project = db.get_project(pid, user["id"])
        user_data = db.get_user_by_id(user["id"]) # Refresh user data for limits
    else:
        # Demo User
        project = next((x for x in projects if x.get("id") == pid and x.get("user_email") == user_email), None)
        user_data = users.get(user_email, {})

    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    plan = get_user_plan(request)

    if analysis_type == "ai_enhanced" and plan == "pro":
        # AI-Enhanced regeneration (Pro only)
        # Note: Database users use 'ai_regens' column, demo users use 'ai_regens_used' (legacy naming difference?)
        # Let's check `database.py`: tables have `ai_regens`.
        # Demo users in memory: `ai_regens_used`?
        # Let's check `dashboard` template: `stats.ai_regens_used`.
        # `database.py` schema: `ai_regens`.
        # `app.py` index route maps `ai_regens` to `ai_regens_used` in stats dict.
        
        # So here we should use the underlying field name.
        if "id" in user:
            current_regens = user_data["ai_regens"]
        else:
            current_regens = user_data.get("ai_regens_used", 0)

        regen_limit = PLAN_LIMITS[plan]["max_ai_regens"]
        if regen_limit is not None and current_regens >= regen_limit:
            project["error"] = f"{plan.capitalize()} plan AI regeneration limit reached."
            return RedirectResponse(f"/report/{pid}", 303)

        try:
            log(f"AI-Enhanced regeneration for project {pid}")
            insights = generate_ai_enhanced_insights(project)
            
            if "id" in user:
                # Update DB User stats
                db.update_user_stats(user["id"], ai_regens=current_regens + 1)
            else:
                # Update Demo User stats
                user_data["ai_regens_used"] = current_regens + 1
                
        except RuntimeError as e:
            error_msg = str(e)
            if "AI_UNAVAILABLE" in error_msg:
                project["error"] = "⚠️ AI service is currently unavailable. Your report was regenerated with consulting-grade Standard Analysis. You can retry AI-Enhanced later."
            else:
                project["error"] = "⚠️ AI regeneration encountered an error. Your report was regenerated with Standard Analysis instead. Please try again — your AI usage was not counted."
            insights = generate_statistical_insights(project)
            log(f"AI regen failed for project {pid}, using standard with notification: {e}")
    else:
        # Standard regeneration (available to all)
        log(f"Standard regeneration for project {pid}")
        insights = generate_statistical_insights(project)

    project["ai_summary"] = insights["summary"]
    project["ai_insights"] = insights["insights"]
    project["ai_recommendations"] = insights["recommendations"]
    project["ai_qa"] = insights["qa"]
    project["report_type"] = insights.get("type", "statistical")
    # Persist changes to DB if applicable
    if "id" in user:
        db_safe_fields = {
            'ai_summary': project.get('ai_summary'),
            'ai_insights': project.get('ai_insights'),
            'ai_recommendations': project.get('ai_recommendations'),
            'ai_qa': project.get('ai_qa'),
            'report_type': project.get('report_type', 'statistical'),
            'error': project.get('error'),
        }
        db_safe_fields = {k: v for k, v in db_safe_fields.items() if v is not None}
        db.update_project(pid, user["id"], **db_safe_fields)

    return RedirectResponse(f"/report/{pid}", status_code=303)



# ==================== EXPORT ROUTES → routes/exports.py ====================
# PDF, PPT, DOCX export and upgrade routes moved to routes/exports.py

# ==================== ADMIN ROUTES → routes/admin.py ====================
# Dashboard, plan management, usage reset moved to routes/admin.py



# ==================== STARTUP EVENT ====================

@app.on_event("startup")
async def startup_event():
    """Log startup information and run cleanup"""
    # Clean old exports
    cleanup_old_exports(max_age_days=7)
    
    logger.info("=" * 60)
    logger.info("🚀 ExecSlate Starting Up")
    logger.info(f"Environment: {ENV}")
    logger.info(f"Debug Mode: {DEBUG}")
    logger.info(f"OpenAI: {'✅ Enabled' if client else '⚠️ Disabled (using mock data)'}")
    logger.info(f"Base Directory: {BASE_DIR}")
    logger.info("=" * 60)

# ==================== HEALTH CHECK ====================
@app.get("/health")
async def health_check():
    """Health check for Render deployment"""
    return {"status": "healthy", "environment": ENV}

# ==================== ROBOTS.TXT ====================
@app.get("/robots.txt")
async def robots_txt():
    """Serve robots.txt for search engine guidance"""
    return FileResponse(str(BASE_DIR / "static" / "robots.txt"), media_type="text/plain")

# ==================== MAIN ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)