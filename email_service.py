import os
import logging
import resend

logger = logging.getLogger(__name__)

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "notifications@execslate.com")

if RESEND_API_KEY:
    resend.api_key = RESEND_API_KEY
else:
    logger.warning("⚠️ RESEND_API_KEY not configured — email delivery disabled")

def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """Send an HTML email using Resend"""
    if not RESEND_API_KEY:
        logger.info(f"Mock Email to {to_email} | Subject: {subject}")
        return False
        
    try:
        r = resend.Emails.send({
            "from": FROM_EMAIL,
            "to": to_email,
            "subject": subject,
            "html": html_content
        })
        logger.info(f"✅ Sent email to {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False

def send_welcome_email(to_email: str):
    """Send welcome onboarding email"""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #334155;">
        <h2 style="color: #667eea;">Welcome to ExecSlate!</h2>
        <p>Your ultimate Executive Reporting OS is ready.</p>
        <p>You can now upload your revenue data and instantly generate board-ready reports and AI insights.</p>
        <br/>
        <p>Best,<br/>The ExecSlate Team</p>
    </div>
    """
    return send_email(to_email, "Welcome to ExecSlate", html)

def send_password_reset(to_email: str, reset_token: str, request_host: str):
    """Send password reset link"""
    reset_link = f"https://{request_host}/reset-password?token={reset_token}"
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #334155;">
        <h2>Password Reset Request</h2>
        <p>We received a request to reset your password. Click the link below to set a new password:</p>
        <p><a href="{reset_link}" style="display:inline-block; padding:10px 20px; background:#667eea; color:white; text-decoration:none; border-radius:5px;">Reset Password</a></p>
        <p>If you did not request this, please ignore this email.</p>
    </div>
    """
    return send_email(to_email, "Reset Your Password - ExecSlate", html)
