# ==================== ADMIN ROUTES ====================
# Extracted from app.py for maintainability

from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["admin"])


def setup(app_module):
    """
    Wire up admin routes with shared state from app.py.
    Called once during app initialization.
    """
    templates = app_module.templates
    users = app_module.users
    projects = app_module.projects
    db = app_module.db
    log = app_module.log
    require_admin = app_module.require_admin
    PLAN_LIMITS = app_module.PLAN_LIMITS

    @router.get("/admin")
    def admin_dashboard(request: Request, user=Depends(require_admin)):
        """Admin-only dashboard to view all users and usage"""
        log("Admin dashboard accessed")

        user_data = []
        seen_emails = set()

        # 1. DB registered users
        db_users = db.get_all_users()
        for db_u in db_users:
            email = db_u["email"]
            seen_emails.add(email)
            db_projects = db.get_user_projects(db_u["id"])
            user_data.append({
                "email": email,
                "plan": db_u.get("plan", "free"),
                "uploads_used": db_u.get("uploads", 0),
                "ai_used": db_u.get("ai_used", 0),
                "ai_regens": db_u.get("ai_regens", 0),
                "project_count": len(db_projects),
                "projects": db_projects,
                "source": "database"
            })

        # 2. In-memory demo users (skip if already in DB)
        for email, user_info in users.items():
            if email in seen_emails:
                continue
            user_projects = [p for p in projects if p.get("user_email") == email]
            user_data.append({
                "email": email,
                "plan": user_info.get("plan", "free"),
                "uploads_used": user_info.get("uploads_used", 0),
                "ai_used": user_info.get("ai_generations_used", 0),
                "ai_regens": user_info.get("ai_regens_used", 0),
                "project_count": len(user_projects),
                "projects": user_projects,
                "source": "memory"
            })

        total_users = len(user_data)
        free_users = sum(1 for u in user_data if u["plan"] == "free")
        pro_users = sum(1 for u in user_data if u["plan"] == "pro")
        business_users = sum(1 for u in user_data if u["plan"] == "business")

        return templates.TemplateResponse(request=request, name="admin.html", context= {
            "request": request,
            "user_data": user_data,
            "all_projects": projects,
            "PLAN_LIMITS": PLAN_LIMITS,
            "total_users": total_users,
            "free_users": free_users,
            "pro_users": pro_users,
            "business_users": business_users
        })

    @router.post("/admin/plan/{email}")
    async def change_user_plan(
        email: str,
        plan: str = Form(...),
        request: Request = None,
        user=Depends(require_admin)
    ):
        """Admin endpoint to change user's plan"""
        if plan not in ("free", "pro", "business"):
            raise HTTPException(status_code=400, detail="Invalid plan")

        db_user = db.get_user_by_email(email)
        if db_user:
            db.update_user_stats(db_user["id"], plan=plan)
            log(f"Admin changed {email} plan to {plan} (DB)")
        elif email in users:
            users[email]["plan"] = plan
            log(f"Admin changed {email} plan to {plan} (memory)")
        else:
            raise HTTPException(status_code=404, detail="User not found")

        return RedirectResponse("/admin?admin=1", status_code=303)

    @router.post("/admin/reset-usage/{email}")
    async def reset_user_usage(
        email: str,
        request: Request = None,
        user=Depends(require_admin)
    ):
        """Admin endpoint to reset user's usage counters"""
        db_user = db.get_user_by_email(email)
        if db_user:
            db.update_user_stats(db_user["id"], uploads=0, ai_used=0, ai_regens=0)
            log(f"Admin reset usage counters for {email} (DB)")
        elif email in users:
            users[email]["uploads_used"] = 0
            users[email]["ai_generations_used"] = 0
            users[email]["ai_regens_used"] = 0
            log(f"Admin reset usage counters for {email} (memory)")
        else:
            raise HTTPException(status_code=404, detail="User not found")

        return RedirectResponse("/admin?admin=1", status_code=303)
