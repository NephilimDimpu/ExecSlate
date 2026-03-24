# ==================== AUTH ROUTES ====================
# Extracted from app.py for maintainability

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
import secrets
import re
from datetime import datetime, timedelta
import email_service

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
        return templates.TemplateResponse(request=request, name="login.html", context= {"request": request})

    @router.post("/login")
    @limiter.limit("5/minute")
    async def login(request: Request, email: str = Form(...), password: str = Form(...)):
        """Handle login authentication (database + fallback to demo users)"""
        email = email.lower()
        # Try database first
        user = db.get_user_by_email(email)

        if user and verify_password(password, user["password_hash"]):
            request.session["user"] = {
                "id": user["id"],
                "username": user.get("username", email.split('@')[0]),
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
                "username": demo_user.get("username", email.split('@')[0]),
                "plan": demo_user["plan"],
                "is_admin": demo_user.get("is_admin", False)
            }
            log(f"User logged in (DEMO): {email}")
            return RedirectResponse("/", status_code=303)

        return templates.TemplateResponse(request=request, name="login.html", context= {
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
        return templates.TemplateResponse(request=request, name="register.html", context= {
            "request": request,
            "plan": plan
        })

    @router.post("/register")
    @limiter.limit("5/minute")
    async def register(
        request: Request,
        username: str = Form(None),
        email: str = Form(...),
        password: str = Form(...),
        confirm_password: str = Form(...),
        selected_plan: str = Form('free')
    ):
        email = email.lower().strip()
        username = username.strip() if username else ""
        
        # 1. Validate Email Format
        email_regex = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
        if not email_regex.match(email):
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Please enter a valid email address format.",
                "plan": selected_plan if selected_plan != 'free' else None
            })
            
        # 2. Block Disposable / Fake Domains
        # A basic list of known fake/abusive/disposable domains to reject
        blocked_domains = [
            "mailinator.com", "10minutemail.com", "guerrillamail.com", 
            "tempmail.com", "suckmynut.com", "dropmail.me", "yopmail.com",
            "staryeye.com", "staryeyes.com"
        ]
        domain = email.split('@')[-1]
        
        # We also block domains containing offensive words or temporary patterns
        if domain in blocked_domains or "suck" in domain or "temp" in domain.split('.')[0]:
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Registration is not permitted with this email provider. Please use a valid work or personal email.",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        # Validate the selected plan
        valid_plans = ['free', 'pro', 'business']
        if selected_plan not in valid_plans:
            selected_plan = 'free'

        if password != confirm_password:
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Passwords do not match",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        if len(password) < 6:
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Password must be at least 6 characters",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        existing_user = db.get_user_by_email(email)
        if existing_user:
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Email already registered. Please login instead.",
                "plan": selected_plan if selected_plan != 'free' else None
            })

        password_hash = hash_password(password)
        user_id = db.create_user(email, password_hash, plan='free', username=username)

        if not user_id:
            return templates.TemplateResponse(request=request, name="register.html", context= {
                "request": request,
                "error": "Registration failed. Please try again."
            })

        request.session["user"] = {
            "id": user_id,
            "username": username,
            "email": email,
            "plan": "free",
            "is_admin": False
        }

        log(f"New user registered: {username} ({email}) - plan: {selected_plan}")
        
        # Dispatch Welcome Email
        try:
            email_service.send_welcome_email(email)
        except Exception as e:
            log(f"Failed to send welcome email to {email}: {e}")

        # If they selected a paid plan, redirect to pricing to complete payment
        if selected_plan in ('pro', 'business'):
            return RedirectResponse("/pricing", status_code=303)

        return RedirectResponse("/", status_code=303)

    # ── Password Reset ──

    @router.get("/forgot-password")
    def forgot_password_page(request: Request):
        return templates.TemplateResponse(request=request, name="forgot_password.html", context= {"request": request})

    @router.post("/forgot-password")
    @limiter.limit("3/minute")
    async def forgot_password(request: Request, email: str = Form(...)):
        email = email.lower()
        user = db.get_user_by_email(email)
        if user:
            token = secrets.token_urlsafe(32)
            # Expires in 1 hour
            expiry = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
            db.set_reset_token(email, token, expiry)
            
            host = request.headers.get("host", "app.execslate.com")
            
            try:
                email_service.send_password_reset(email, token, host)
                log(f"Password reset email dispatched to {email}")
            except Exception as e:
                log(f"Failed to send reset email: {e}")
            
            return templates.TemplateResponse(request=request, name="reset_sent.html", context= {
                "request": request, 
                "email": email
            })
            
        # Also show success if user not found to prevent email enumeration
        return templates.TemplateResponse(request=request, name="reset_sent.html", context= {
            "request": request,
            "email": email
        })

    @router.get("/reset-password")
    def reset_password_page(request: Request, token: str):
        if not token:
            return RedirectResponse("/login")
        return templates.TemplateResponse(request=request, name="reset_password.html", context= {
            "request": request,
            "token": token
        })

    @router.post("/reset-password")
    @limiter.limit("3/minute")
    async def reset_password(
        request: Request, 
        token: str = Form(...),
        password: str = Form(...),
        confirm_password: str = Form(...)
    ):
        if password != confirm_password:
            return templates.TemplateResponse(request=request, name="reset_password.html", context= {
                "request": request,
                "token": token,
                "error": "Passwords do not match"
            })
            
        if len(password) < 6:
            return templates.TemplateResponse(request=request, name="reset_password.html", context= {
                "request": request,
                "token": token,
                "error": "Password must be at least 6 characters"
            })
            
        user = db.get_user_by_reset_token(token)
        if not user:
            return templates.TemplateResponse(request=request, name="reset_password.html", context= {
                "request": request,
                "token": token,
                "error": "Invalid or expired reset token. Please request a new one."
            })
            
        # Update password
        new_hash = hash_password(password)
        db.update_user_password(user["id"], new_hash)
        log(f"Password reset successful for {user['email']}")
        
        # Log them in automatically
        request.session["user"] = {
            "id": user["id"],
            "email": user["email"],
            "plan": user["plan"],
            "is_admin": False
        }
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
            "username": "Demo User",
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
        return templates.TemplateResponse(request=request, name="pricing.html", context= {
            "request": request,
            "PLAN_LIMITS": PLAN_LIMITS,
            "user": user
        })
