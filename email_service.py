import os
import logging
from datetime import datetime
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
    """Send premium welcome onboarding email"""
    html = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, Arial, sans-serif; background-color: #f8fafc; padding: 40px 0; color: #334155;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
            <!-- Header -->
            <div style="background-color: #0f172a; padding: 32px 40px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 2px; color: #ffffff;">
                    <span style="color: #3b82f6;">■</span> E X E C S L A T E
                </h1>
            </div>
            
            <!-- Body -->
            <div style="padding: 40px;">
                <h2 style="color: #0f172a; margin-top: 0; font-size: 22px;">Welcome to the Boardroom.</h2>
                <p style="font-size: 16px; line-height: 1.6; color: #475569; margin-bottom: 24px;">
                    Your ultimate Executive Reporting OS is ready. You can now transform raw CSVs into consulting-grade presentations instantly.
                </p>
                <div style="background-color: #f1f5f9; border-left: 4px solid #3b82f6; padding: 16px 20px; border-radius: 4px; margin-bottom: 32px;">
                    <p style="margin: 0; font-size: 15px; color: #334155;"><strong>Next Step:</strong> Upload your first revenue dataset to generate AI insights, multidimensional analysis, and presentation-ready PDFs.</p>
                </div>
                
                <a href="https://app.execslate.com" style="display: inline-block; background-color: #3b82f6; color: #ffffff; text-decoration: none; padding: 14px 28px; font-size: 16px; font-weight: 600; border-radius: 6px; text-align: center; box-shadow: 0 2px 4px rgba(59, 130, 246, 0.3);">Go to Dashboard</a>
                
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 40px 0 24px;" />
                <p style="margin: 0; font-size: 14px; color: #64748b;">Best regards,<br/><strong style="color: #0f172a;">The ExecSlate Team</strong></p>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f8fafc; padding: 24px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0; font-size: 13px; color: #94a3b8;">&copy; {datetime.now().year} ExecSlate. All rights reserved.</p>
                <p style="margin: 8px 0 0; font-size: 12px; color: #cbd5e1;">CONFIDENTIAL — FOR INTERNAL USE ONLY</p>
            </div>
        </div>
    </div>
    """
    return send_email(to_email, "Welcome to ExecSlate", html)

def send_password_reset(to_email: str, reset_token: str, request_host: str):
    """Send premium password reset link"""
    reset_link = f"https://{request_host}/reset-password?token={reset_token}"
    html = f"""
    <div style="font-family: 'Inter', -apple-system, BlinkMacSystemFont, Arial, sans-serif; background-color: #f8fafc; padding: 40px 0; color: #334155;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);">
            <!-- Header -->
            <div style="background-color: #0f172a; padding: 32px 40px; text-align: center;">
                <h1 style="margin: 0; font-size: 24px; font-weight: 700; letter-spacing: 2px; color: #ffffff;">
                    <span style="color: #3b82f6;">■</span> E X E C S L A T E
                </h1>
            </div>
            
            <!-- Body -->
            <div style="padding: 40px;">
                <h2 style="color: #0f172a; margin-top: 0; font-size: 22px;">Reset Your Password</h2>
                <p style="font-size: 16px; line-height: 1.6; color: #475569; margin-bottom: 32px;">
                    We received a request to securely reset the password for your ExecSlate account associated with <strong>{to_email}</strong>. 
                    Click the button below to establish a new password.
                </p>
                
                <a href="{reset_link}" style="display: block; width: 100%; max-width: 250px; margin: 0 auto; background-color: #0f172a; color: #ffffff; text-decoration: none; padding: 14px 0; font-size: 16px; font-weight: 600; border-radius: 6px; text-align: center; border: 1px solid #1e293b;">Secure Password Reset</a>
                
                <p style="font-size: 14px; text-align: center; color: #64748b; margin-top: 24px; margin-bottom: 32px;">
                    This link will expire in 1 hour.
                </p>
                
                <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 40px 0 24px;" />
                <p style="margin: 0; font-size: 14px; color: #64748b;">If you did not request this change, please ignore this email or contact security immediately.</p>
            </div>
            
            <!-- Footer -->
            <div style="background-color: #f8fafc; padding: 24px 40px; text-align: center; border-top: 1px solid #e2e8f0;">
                <p style="margin: 0; font-size: 13px; color: #94a3b8;">&copy; {datetime.now().year} ExecSlate Security</p>
                <p style="margin: 8px 0 0; font-size: 12px; color: #cbd5e1;">CONFIDENTIAL — FOR INTERNAL USE ONLY</p>
            </div>
        </div>
    </div>
    """
    return send_email(to_email, "Secure Password Reset - ExecSlate", html)
