"""
ExecSlate Database Module
SQLite-based persistence for users and projects
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Database file location
DB_FILE = Path(__file__).parent / "execslate.db"

def get_db():
    """Get database connection"""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def init_db():
    """Initialize database with schema"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            plan TEXT DEFAULT 'free',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            uploads INTEGER DEFAULT 0,
            ai_used BOOLEAN DEFAULT 0,
            ai_regens INTEGER DEFAULT 0
        )
    """)
    
    # Migration: Check if users table has all required columns
    try:
        cursor.execute("PRAGMA table_info(users)")
        user_columns = {row[1] for row in cursor.fetchall()}
        required_columns = {'id', 'email', 'password_hash', 'plan', 'created_at', 'uploads', 'ai_used', 'ai_regens'}
        # Add any missing columns (future-proof for migrations)
    except Exception as e:
        logger.warning(f"Could not check user table schema: {e}")
    
    # Create projects table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            client TEXT NOT NULL,
            period TEXT,
            currency TEXT DEFAULT '$',
            total_revenue REAL DEFAULT 0,
            avg_revenue REAL DEFAULT 0,
            median_revenue REAL DEFAULT 0,
            growth_rate REAL DEFAULT 0,
            trend TEXT,
            top_region TEXT,
            row_count INTEGER DEFAULT 0,
            confidence INTEGER DEFAULT 0,
            revenue_series TEXT,
            region_labels TEXT,
            region_values TEXT,
            ai_summary TEXT,
            ai_insights TEXT,
            ai_recommendations TEXT,
            ai_qa TEXT,
            revenue_chart TEXT,
            region_chart TEXT,
            chart_narratives TEXT,
            available_columns TEXT,
            column_map TEXT,
            kpi_metrics TEXT,
            primary_kpi TEXT,
            report_title TEXT,
            last_uploaded_file TEXT,
            report_type TEXT DEFAULT 'statistical',
            generated BOOLEAN DEFAULT 0,
            error TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    
    # Migration: Add missing columns to existing projects table
    try:
        cursor.execute("PRAGMA table_info(projects)")
        existing_columns = {row[1] for row in cursor.fetchall()}
        
        # List of columns that should exist
        required_columns = {
            'revenue_chart': 'TEXT',
            'region_chart': 'TEXT', 
            'chart_narratives': 'TEXT',
            'available_columns': 'TEXT',
            'column_map': 'TEXT',
            'kpi_metrics': 'TEXT',
            'primary_kpi': 'TEXT',
            'report_title': 'TEXT',
            'last_uploaded_file': 'TEXT'
        }
        
        # Add any missing columns
        for col_name, col_type in required_columns.items():
            if col_name not in existing_columns:
                try:
                    cursor.execute(f"ALTER TABLE projects ADD COLUMN {col_name} {col_type}")
                    logger.info(f"✅ Added missing column: projects.{col_name}")
                except Exception as e:
                    logger.warning(f"Could not add column {col_name}: {e}")
    except Exception as e:
        logger.warning(f"Could not check projects table schema: {e}")
    
    conn.commit()
    conn.close()
    logger.info(f"✅ Database initialized at {DB_FILE}")

# ==================== USER OPERATIONS ====================

def create_user(email, password_hash, plan='free'):
    """Create a new user"""
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, plan)
            VALUES (?, ?, ?)
        """, (email, password_hash, plan))
        conn.commit()
        user_id = cursor.lastrowid
        logger.info(f"✅ Created user: {email} (ID: {user_id})")
        return user_id
    except sqlite3.IntegrityError:
        logger.warning(f"⚠️ User already exists: {email}")
        return None
    finally:
        conn.close()

def get_user_by_email(email):
    """Get user by email"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def get_user_by_id(user_id):
    """Get user by ID"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    conn.close()
    return dict(user) if user else None

def update_user_stats(user_id, **kwargs):
    """Update user statistics (uploads, ai_used, ai_regens)"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Build dynamic UPDATE query
    fields = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [user_id]
    
    cursor.execute(f"""
        UPDATE users
        SET {fields}
        WHERE id = ?
    """, values)
    
    conn.commit()
    conn.close()

def get_all_users():
    """Get all registered users (for admin dashboard)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cursor.fetchall()
    conn.close()
    return [dict(u) for u in users]

def get_all_projects():
    """Get all projects across all users (for admin dashboard)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT p.*, u.email as user_email 
        FROM projects p 
        JOIN users u ON p.user_id = u.id 
        ORDER BY p.created_at DESC
    """)
    projects = cursor.fetchall()
    conn.close()
    return [dict(p) for p in projects]

# ==================== PROJECT OPERATIONS ====================

def create_project(user_id, client, period=""):
    """Create a new project"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO projects (user_id, client, period)
        VALUES (?, ?, ?)
    """, (user_id, client, period))
    conn.commit()
    project_id = cursor.lastrowid
    conn.close()
    logger.info(f"✅ Created project: {client} (ID: {project_id}) for user {user_id}")
    return project_id

def get_project(project_id, user_id):
    """Get a project by ID (with ownership check)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM projects 
        WHERE id = ? AND user_id = ?
    """, (project_id, user_id))
    project = cursor.fetchone()
    conn.close()
    
    if not project:
        return None
    
    # Convert to dict and deserialize JSON fields
    project_dict = dict(project)
    json_fields = ['revenue_series', 'region_labels', 'region_values', 
                   'ai_insights', 'ai_recommendations', 'ai_qa', 
                   'chart_narratives', 'available_columns', 'column_map', 'kpi_metrics']
                   
    for field in json_fields:
        if project_dict.get(field):
            try:
                project_dict[field] = json.loads(project_dict[field])
            except:
                project_dict[field] = None
    
    return project_dict

def get_user_projects(user_id):
    """Get all projects for a user"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM projects 
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (user_id,))
    projects = cursor.fetchall()
    conn.close()
    
    # Convert to list of dicts
    project_list = []
    json_fields = ['revenue_series', 'region_labels', 'region_values', 
                   'ai_insights', 'ai_recommendations', 'ai_qa', 
                   'chart_narratives', 'available_columns', 'column_map', 'kpi_metrics']
                   
    for project in projects:
        project_dict = dict(project)
        # Deserialize JSON fields
        for field in json_fields:
            if project_dict.get(field):
                try:
                    project_dict[field] = json.loads(project_dict[field])
                except:
                    project_dict[field] = None
        project_list.append(project_dict)
    
    return project_list

def update_project(project_id, user_id, **kwargs):
    """Update project data"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Serialize JSON fields
    json_fields = ['revenue_series', 'region_labels', 'region_values', 
                   'ai_insights', 'ai_recommendations', 'ai_qa', 
                   'chart_narratives', 'available_columns', 'column_map', 'kpi_metrics']
                   
    for field in json_fields:
        if field in kwargs and kwargs[field] is not None:
            kwargs[field] = json.dumps(kwargs[field])
    
    # Build dynamic UPDATE query
    fields = ", ".join([f"{key} = ?" for key in kwargs.keys()])
    values = list(kwargs.values()) + [project_id, user_id]
    
    cursor.execute(f"""
        UPDATE projects
        SET {fields}
        WHERE id = ? AND user_id = ?
    """, values)
    
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    
    return rows_affected > 0

def delete_project(project_id, user_id):
    """Delete a project (with ownership check)"""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM projects 
        WHERE id = ? AND user_id = ?
    """, (project_id, user_id))
    conn.commit()
    rows_affected = cursor.rowcount
    conn.close()
    
    if rows_affected > 0:
        logger.info(f"✅ Deleted project {project_id}")
        return True
    return False

# Initialize database on module import
init_db()
