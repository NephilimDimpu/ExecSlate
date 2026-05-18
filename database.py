"""
ExecSlate Database Module
SQLAlchemy ORM version (PostgreSQL & SQLite compatible)
"""

import os
import json
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from sqlalchemy.exc import IntegrityError

from storage_service import storage

logger = logging.getLogger(__name__)

# Use DATABASE_URL from env (PostgreSQL), fallback to local sqlite
DB_URL = os.getenv("DATABASE_URL", f"sqlite:///{Path(__file__).parent / 'execslate.db'}")

# SQLite specific args
connect_args = {"check_same_thread": False} if "sqlite" in DB_URL else {}
engine = create_engine(DB_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ==================== ORM MODELS ====================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String)
    password_hash = Column(String, nullable=False)
    plan = Column(String, default='free')
    created_at = Column(DateTime, server_default=func.now())
    uploads = Column(Integer, default=0)
    ai_used = Column(Boolean, default=False)
    ai_regens = Column(Integer, default=0)
    reset_token = Column(String)
    reset_token_expires = Column(DateTime)
    
class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    client = Column(String, nullable=False)
    period = Column(String)
    currency = Column(String, default='$')
    total_revenue = Column(Float, default=0.0)
    avg_revenue = Column(Float, default=0.0)
    median_revenue = Column(Float, default=0.0)
    growth_rate = Column(Float, default=0.0)
    trend = Column(String)
    top_region = Column(String)
    row_count = Column(Integer, default=0)
    confidence = Column(Integer, default=0)
    
    # Text types for JSON storage
    revenue_series = Column(Text)
    region_labels = Column(Text)
    region_values = Column(Text)
    ai_summary = Column(Text)
    ai_insights = Column(Text)
    ai_recommendations = Column(Text)
    ai_qa = Column(Text)
    revenue_chart = Column(String)
    region_chart = Column(String)
    chart_narratives = Column(Text)
    available_columns = Column(Text)
    column_map = Column(Text)
    kpi_metrics = Column(Text)
    primary_kpi = Column(String)
    report_title = Column(String)
    last_uploaded_file = Column(String)
    report_type = Column(String, default='statistical')
    analysis_framework = Column(String)  # e.g., 'profitability', 'market_entry'
    hypotheses = Column(Text)           # JSON storage for strategic hypotheses
    working_theory = Column(Text)       # Consultant's qualitative insights
    generated = Column(Boolean, default=False)
    error = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class AnalyticsDraft(Base):
    __tablename__ = "analytics_drafts"
    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, default="Draft 1")
    kpi_snapshot = Column(Text)       # JSON list of selected KPI keys
    selected_insights = Column(Text)  # JSON list of pinned insight strings
    notes = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    email = Column(String, nullable=False)
    order_id = Column(String, nullable=False)
    payment_id = Column(String, unique=True, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default='INR')
    plan = Column(String, nullable=False)
    status = Column(String, default='captured')
    created_at = Column(DateTime, server_default=func.now())

# ==================== HELPERS ====================

def init_db():
    Base.metadata.create_all(bind=engine)
    db_type = "PostgreSQL" if "postgres" in DB_URL else "SQLite"
    logger.info(f"✅ Database initialized ({db_type})")

def _user_to_dict(user):
    if not user:
        return None
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "password_hash": user.password_hash,
        "plan": user.plan,
        "created_at": user.created_at,
        "uploads": user.uploads,
        "ai_used": 1 if user.ai_used else 0,
        "ai_regens": user.ai_regens,
        "reset_token": user.reset_token,
        "reset_token_expires": user.reset_token_expires
    }

def _project_to_dict(proj, include_user_email=False):
    if not proj:
        return None
        
    p_obj = proj[0] if isinstance(proj, tuple) else proj
    p_dict = {
        "id": p_obj.id,
        "user_id": p_obj.user_id,
        "client": p_obj.client,
        "period": p_obj.period,
        "currency": p_obj.currency,
        "total_revenue": p_obj.total_revenue,
        "avg_revenue": p_obj.avg_revenue,
        "median_revenue": p_obj.median_revenue,
        "growth_rate": p_obj.growth_rate,
        "trend": p_obj.trend,
        "top_region": p_obj.top_region,
        "row_count": p_obj.row_count,
        "confidence": p_obj.confidence,
        "revenue_chart": storage.load(p_obj.revenue_chart) if p_obj.revenue_chart and p_obj.revenue_chart.startswith("storage://") else p_obj.revenue_chart,
        "region_chart": storage.load(p_obj.region_chart) if p_obj.region_chart and p_obj.region_chart.startswith("storage://") else p_obj.region_chart,
        "primary_kpi": p_obj.primary_kpi,
        "report_title": p_obj.report_title,
        "last_uploaded_file": p_obj.last_uploaded_file,
        "report_type": p_obj.report_type,
        "analysis_framework": p_obj.analysis_framework,
        "working_theory": p_obj.working_theory,
        "generated": 1 if p_obj.generated else 0,
        "error": p_obj.error,
        "created_at": p_obj.created_at,
    }
    
    if include_user_email and isinstance(proj, tuple) and len(proj) > 1:
        p_dict["user_email"] = proj[1]

    json_fields = ['revenue_series', 'region_labels', 'region_values', 
                   'ai_insights', 'ai_recommendations', 'ai_qa', 
                   'chart_narratives', 'available_columns', 'column_map', 'kpi_metrics', 'hypotheses']
                   
    for field in json_fields:
        val = getattr(p_obj, field)
        if val:
            try:
                if val.startswith("storage://"):
                    raw_data = storage.load(val)
                    p_dict[field] = json.loads(raw_data) if raw_data else None
                else:
                    p_dict[field] = json.loads(val)
            except:
                p_dict[field] = None
        else:
            p_dict[field] = None
            
    p_dict["ai_summary"] = p_obj.ai_summary
            
    return p_dict

# ==================== USER OPERATIONS ====================

def create_user(email, password_hash, plan='free', username=None):
    with SessionLocal() as db:
        user = User(email=email.lower(), username=username, password_hash=password_hash, plan=plan)
        try:
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"✅ Created user: {email} (ID: {user.id})")
            return user.id
        except Exception as e:
            db.rollback()
            logger.warning(f"⚠️ User already exists or error: {e}")
            return None

def get_user_by_email(email):
    with SessionLocal() as db:
        user = db.query(User).filter(func.lower(User.email) == email.lower()).first()
        return _user_to_dict(user)

def get_user_by_id(user_id):
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        return _user_to_dict(user)

def update_user_stats(user_id, **kwargs):
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update(kwargs)
        db.commit()

def get_all_users():
    with SessionLocal() as db:
        users = db.query(User).order_by(User.created_at.desc()).all()
        return [_user_to_dict(u) for u in users]

def set_reset_token(email, token, expiry):
    with SessionLocal() as db:
        db.query(User).filter(User.email == email).update({"reset_token": token, "reset_token_expires": expiry})
        db.commit()

def get_user_by_reset_token(token):
    with SessionLocal() as db:
        user = db.query(User).filter(User.reset_token == token, User.reset_token_expires > datetime.now()).first()
        return _user_to_dict(user)

def update_user_password(user_id, new_password_hash):
    with SessionLocal() as db:
        db.query(User).filter(User.id == user_id).update({"password_hash": new_password_hash, "reset_token": None, "reset_token_expires": None})
        db.commit()

# ==================== PROJECT OPERATIONS ====================

def get_all_projects():
    with SessionLocal() as db:
        projects = db.query(Project, User.email).join(User, Project.user_id == User.id).order_by(Project.created_at.desc()).all()
        return [_project_to_dict(p, include_user_email=True) for p in projects]

def create_project(user_id, client, period=""):
    with SessionLocal() as db:
        proj = Project(user_id=user_id, client=client, period=period)
        db.add(proj)
        db.commit()
        db.refresh(proj)
        logger.info(f"✅ Created project: {client} (ID: {proj.id}) for user {user_id}")
        return proj.id

def get_project(project_id, user_id):
    with SessionLocal() as db:
        proj = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).first()
        return _project_to_dict(proj)

def get_user_projects(user_id):
    with SessionLocal() as db:
        projects = db.query(Project).filter(Project.user_id == user_id).order_by(Project.created_at.desc()).all()
        return [_project_to_dict(p) for p in projects]

def update_project(project_id, user_id, **kwargs):
    with SessionLocal() as db:
        json_fields = ['revenue_series', 'region_labels', 'region_values', 
                       'ai_insights', 'ai_recommendations', 'ai_qa', 
                       'chart_narratives', 'available_columns', 'column_map', 'kpi_metrics', 'hypotheses']
        blob_fields = ['revenue_chart', 'region_chart']
        
        upd = {}
        for k, v in kwargs.items():
            if k in json_fields and v is not None:
                json_str = json.dumps(v)
                key = f"project_{project_id}_{k}"
                uri = storage.save(key, json_str)
                upd[k] = uri if uri else json_str
            elif k in blob_fields and v is not None:
                key = f"project_{project_id}_{k}"
                uri = storage.save(key, str(v))
                upd[k] = uri if uri else v
            else:
                upd[k] = v
                
        affected = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).update(upd)
        db.commit()
        return affected > 0

def delete_project(project_id, user_id):
    with SessionLocal() as db:
        affected = db.query(Project).filter(Project.id == project_id, Project.user_id == user_id).delete()
        db.commit()
        if affected > 0:
            logger.info(f"✅ Deleted project {project_id}")
            return True
        return False

# ==================== PAYMENT OPERATIONS ====================

def create_payment(user_id, email, order_id, payment_id, amount, currency, plan, status='captured'):
    with SessionLocal() as db:
        payment = Payment(
            user_id=user_id,
            email=email.lower(),
            order_id=order_id,
            payment_id=payment_id,
            amount=amount,
            currency=currency,
            plan=plan,
            status=status
        )
        try:
            db.add(payment)
            db.commit()
            db.refresh(payment)
            logger.info(f"✅ Logged payment: {payment_id} for user {email}")
            return payment.id
        except Exception as e:
            db.rollback()
            logger.error(f"❌ Failed to log payment {payment_id}: {e}")
            return None

def get_user_payments(user_id):
    with SessionLocal() as db:
        payments = db.query(Payment).filter(Payment.user_id == user_id).order_by(Payment.created_at.desc()).all()
        return [
            {
                "id": p.id,
                "user_id": p.user_id,
                "email": p.email,
                "order_id": p.order_id,
                "payment_id": p.payment_id,
                "amount": p.amount,
                "currency": p.currency,
                "plan": p.plan,
                "status": p.status,
                "created_at": p.created_at
            }
            for p in payments
        ]

# ==================== ANALYTICS DRAFT OPERATIONS ====================

def create_analytics_draft(project_id, name, kpi_snapshot, selected_insights, notes):
    with SessionLocal() as db_session:
        draft = AnalyticsDraft(
            project_id=project_id,
            name=name or "Draft",
            kpi_snapshot=json.dumps(kpi_snapshot) if kpi_snapshot else None,
            selected_insights=json.dumps(selected_insights) if selected_insights else None,
            notes=notes,
        )
        db_session.add(draft)
        db_session.commit()
        db_session.refresh(draft)
        return draft.id

def get_analytics_drafts(project_id):
    with SessionLocal() as db_session:
        drafts = db_session.query(AnalyticsDraft).filter(
            AnalyticsDraft.project_id == project_id
        ).order_by(AnalyticsDraft.created_at.desc()).all()
        return [
            {
                "id": d.id,
                "project_id": d.project_id,
                "name": d.name,
                "kpi_snapshot": json.loads(d.kpi_snapshot) if d.kpi_snapshot else [],
                "selected_insights": json.loads(d.selected_insights) if d.selected_insights else [],
                "notes": d.notes,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in drafts
        ]

def get_latest_analytics_draft(project_id):
    with SessionLocal() as db_session:
        draft = db_session.query(AnalyticsDraft).filter(
            AnalyticsDraft.project_id == project_id
        ).order_by(AnalyticsDraft.created_at.desc()).first()
        if not draft:
            return None
        return {
            "id": draft.id,
            "project_id": draft.project_id,
            "name": draft.name,
            "kpi_snapshot": json.loads(draft.kpi_snapshot) if draft.kpi_snapshot else [],
            "selected_insights": json.loads(draft.selected_insights) if draft.selected_insights else [],
            "notes": draft.notes,
            "created_at": draft.created_at.isoformat() if draft.created_at else None,
        }

# Initialize database on module import
init_db()
