# ==================== PAYMENT ROUTES (Razorpay) ====================
# Handles order creation, payment verification, and plan upgrades

import hmac
import hashlib
import logging
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

logger = logging.getLogger("ExecSlate")

router = APIRouter(tags=["payments"])

# Plan pricing (amount in paise — Razorpay uses smallest currency unit)
# NOTE: Using INR until international payments are enabled in Razorpay dashboard.
# Once enabled, switch currency to "USD" and amounts to 4900/9900.
PLAN_PRICES = {
    "pro": {
        "name": "ExecSlate Professional",
        "amount": 410000,        # ₹4,100 (~$49 equivalent)
        "currency": "INR",
        "description": "20 uploads/mo, 10 AI insights, all exports"
    },
    "business": {
        "name": "ExecSlate Business",
        "amount": 830000,        # ₹8,300 (~$99 equivalent)
        "currency": "INR",
        "description": "Unlimited uploads, unlimited AI, all exports"
    }
}


def setup(app_module):
    """
    Wire up payment routes with shared state from app.py.
    """
    templates = app_module.templates
    db = app_module.db
    users = app_module.users
    log = app_module.log
    require_user = app_module.require_user
    razorpay_client = getattr(app_module, 'razorpay_client', None)
    RAZORPAY_KEY_ID = getattr(app_module, 'RAZORPAY_KEY_ID', '')
    RAZORPAY_KEY_SECRET = getattr(app_module, 'RAZORPAY_KEY_SECRET', '')

    # ── Create Order ──

    @router.post("/payment/create-order")
    async def create_order(request: Request, plan: str = Form(...)):
        """Create a Razorpay order for the selected plan"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Please login first")

        if plan not in PLAN_PRICES:
            raise HTTPException(status_code=400, detail="Invalid plan")

        if not razorpay_client:
            raise HTTPException(status_code=503, detail="Payment service not configured")

        plan_info = PLAN_PRICES[plan]

        try:
            order = razorpay_client.order.create({
                "amount": plan_info["amount"],
                "currency": plan_info["currency"],
                "receipt": f"order_{user['email']}_{plan}",
                "notes": {
                    "plan": plan,
                    "email": user["email"],
                    "user_id": str(user.get("id", ""))
                }
            })

            log(f"Razorpay order created: {order['id']} for {user['email']} ({plan})")

            return JSONResponse({
                "order_id": order["id"],
                "amount": plan_info["amount"],
                "currency": plan_info["currency"],
                "name": plan_info["name"],
                "description": plan_info["description"],
                "key_id": RAZORPAY_KEY_ID,
                "email": user["email"]
            })

        except Exception as e:
            logger.error(f"Order creation failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Could not create payment order")

    # ── Verify Payment ──

    @router.post("/payment/verify")
    async def verify_payment(
        request: Request,
        razorpay_order_id: str = Form(...),
        razorpay_payment_id: str = Form(...),
        razorpay_signature: str = Form(...),
        plan: str = Form(...)
    ):
        """Verify Razorpay payment signature and upgrade user plan"""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Please login first")

        # Verify signature
        message = f"{razorpay_order_id}|{razorpay_payment_id}"
        expected_signature = hmac.new(
            RAZORPAY_KEY_SECRET.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        if expected_signature != razorpay_signature:
            log(f"Payment verification FAILED for {user['email']}")
            raise HTTPException(status_code=400, detail="Payment verification failed")

        # Payment verified — upgrade user plan
        is_db_user = "id" in user

        if is_db_user:
            db.update_user_stats(user["id"], plan=plan)
            # Log the payment transaction to the database
            plan_info = PLAN_PRICES.get(plan, {"amount": 0, "currency": "INR"})
            db.create_payment(
                user_id=user["id"],
                email=user["email"],
                order_id=razorpay_order_id,
                payment_id=razorpay_payment_id,
                amount=float(plan_info["amount"]) / 100.0,
                currency=plan_info["currency"],
                plan=plan
            )
        else:
            user_email = user["email"]
            if user_email in users:
                users[user_email]["plan"] = plan

        # Update session
        user["plan"] = plan
        request.session["user"] = user

        log(f"✅ Payment verified! {user['email']} upgraded to {plan} (Payment: {razorpay_payment_id})")

        return JSONResponse({
            "success": True,
            "plan": plan,
            "message": f"Successfully upgraded to {plan.capitalize()}!"
        })

    # ── Webhook (server-to-server confirmation) ──

    @router.post("/payment/webhook")
    async def razorpay_webhook(request: Request):
        """
        Razorpay webhook for server-side payment confirmation.
        This is a backup to the client-side verification.
        Configure this URL in Razorpay Dashboard → Webhooks.
        """
        try:
            body = await request.body()
            signature = request.headers.get("X-Razorpay-Signature", "")

            # Verify webhook signature
            expected = hmac.new(
                RAZORPAY_KEY_SECRET.encode('utf-8'),
                body,
                hashlib.sha256
            ).hexdigest()

            if expected != signature:
                logger.warning("Webhook signature mismatch")
                raise HTTPException(status_code=400, detail="Invalid signature")

            import json
            payload = json.loads(body)
            event = payload.get("event", "")

            if event == "payment.captured":
                payment = payload["payload"]["payment"]["entity"]
                notes = payment.get("notes", {})
                email = notes.get("email", "")
                plan = notes.get("plan", "")
                user_id = notes.get("user_id", "")

                if email and plan:
                    # Upgrade via DB
                    if user_id:
                        db.update_user_stats(int(user_id), plan=plan)
                        # Log payment transaction if user is in DB
                        db.create_payment(
                            user_id=int(user_id),
                            email=email,
                            order_id=payment.get("order_id", ""),
                            payment_id=payment.get("id", ""),
                            amount=float(payment.get("amount", 0)) / 100.0,
                            currency=payment.get("currency", "INR"),
                            plan=plan
                        )
                    # Upgrade via in-memory
                    if email in users:
                        users[email]["plan"] = plan

                    log(f"✅ Webhook: {email} upgraded to {plan}")

            return JSONResponse({"status": "ok"})

        except Exception as e:
            logger.error(f"Webhook error: {e}", exc_info=True)
            return JSONResponse({"status": "error"}, status_code=500)
