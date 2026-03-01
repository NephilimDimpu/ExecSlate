# ==================== AUTH ROUTES ====================
# Extracted from app.py for maintainability

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

router = APIRouter(tags=["auth"])


def setup(app_module):
    """
    Wire up auth routes with shared state from app.py.
    Called once during app initialization.
    """
    templates = app_module.templates
    limiter = app_module.limiter
    users = app_module.users
    db = app_module.db
    verify_password = app_module.verify_password
    hash_password = app_module.hash_password
    log = app_module.log
    PLAN_LIMITS = app_module.PLAN_LIMITS

    # ── Login ──

    @router.get("/login")
    def login_page(request: Request):
        """Display login page"""
        return templates.TemplateResponse("login.html", {"request": request})

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, email: str = Form(...), password: str = Form(...)):
        """Handle login authentication (database + fallback to demo users)"""
        # Try database first
        user = db.get_user_by_email(email)

        if user and verify_password(password, user["password_hash"]):
            request.session["user"] = {
                "id": user["id"],
                "email": user["email"],
                "plan": user["plan"],
                "is_admin": False
            }
            log(f"User logged in (DB): {email}")
            return RedirectResponse("/", status_code=303)

        # Fallback to demo users (for testing)
        demo_user = users.get(email)
        if demo_user and verify_password(password, demo_user["password"]):
            request.session["user"] = {
                "email": demo_user["email"],
                "plan": demo_user["plan"],
                "is_admin": demo_user.get("is_admin", False)
            }
            log(f"User logged in (DEMO): {email}")
            return RedirectResponse("/", status_code=303)

        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password"
        })

    # ── Register ──

    @router.get("/register")
    def register_page(request: Request, plan: str = None):
        """Display registration page, optionally with a pre-selected plan"""
        # Validate plan param
        valid_plans = ['free', 'pro', 'business']
        if plan and plan not in valid_plans:
            plan = None
        return templates.TemplateResponse("register.html", {
            "request": request,
            "plan": plan
        })

    @router.post("/register")
    @limiter.limit("5/minute")
    async def register(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        confirm_password: str = Form(...),
        selected_plan: str = Form('free')
    ):
        """Handle user registration"""
        # Validate the selected plan
        valid_plans = ['free', 'pro', 'business']
        if selected_plan not in valid_plans:
            selected_plan = 'free'

        if password != confirm_password:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Passwords do not match",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        if len(password) < 6:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Password must be at least 6 characters",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        existing_user = db.get_user_by_email(email)
        if existing_user:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Email already registered. Please login instead.",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        password_hash = hash_password(password)
        user_id = db.create_user(email, password_hash, plan='free')

        if not user_id:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error": "Registration failed. Please try again."
            })

        request.session["user"] = {
            "id": user_id,
            "email": email,
            "plan": "free",
            "is_admin": False
        }

        log(f"New user registered: {email} (selected plan: {selected_plan})")

        # If they selected a paid plan, redirect to pricing to complete payment
        if selected_plan in ('pro', 'business'):
            return RedirectResponse("/pricing", status_code=303)

        return RedirectResponse("/", status_code=303)

    # ── Logout ──

    @router.get("/logout")
    def logout(request: Request):
        """Handle user logout"""
        user = request.session.get("user")
        if user:
            log(f"User logged out: {user['email']}")
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # ── Demo Login ──

    @router.get("/demo")
    def demo_login(request: Request):
        """Auto-login as demo user"""
        request.session["user"] = {
            "email": "demo@execslate.ai",
            "plan": "demo",
            "is_admin": False
        }
        log(f"User logged in (DEMO): demo@execslate.ai - Plan: demo")
        return RedirectResponse("/", status_code=303)

    # ── Pricing ──

    @router.get("/pricing")
    def pricing_page(request: Request):
        """Display pricing page"""
        user = request.session.get("user")
        return templates.TemplateResponse("pricing.html", {
            "request": request,
            "PLAN_LIMITS": PLAN_LIMITS,
            "user": user
        })
