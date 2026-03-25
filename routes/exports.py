# ==================== EXPORT ROUTES ====================
# Extracted from app.py for maintainability

import re
import logging
from datetime import datetime
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import FileResponse

logger = logging.getLogger("ExecSlate")

router = APIRouter(tags=["exports"])


def setup(app_module):
    """
    Wire up export routes with shared state from app.py.
    Called once during app initialization.
    """
    projects = app_module.projects
    db = app_module.db
    log = app_module.log
    require_user = app_module.require_user
    get_user_plan = app_module.get_user_plan
    PLAN_LIMITS = app_module.PLAN_LIMITS
    EXPORT_DIR = app_module.EXPORT_DIR
    export_pdf_enhanced = app_module.export_pdf_enhanced
    export_ppt_enhanced = app_module.export_ppt_enhanced
    export_docx_enhanced = app_module.export_docx_enhanced

    @router.get("/export/pdf/{pid}")
    def export_pdf(pid: int, request: Request, user=Depends(require_user)):
        """Export project as PDF"""
        user_email = user["email"]

        if "id" in user:
            project = db.get_project(pid, user["id"])
        else:
            project = next((x for x in projects if x["id"] == pid and x.get("user_email") == user_email), None)

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.get("generated"):
            raise HTTPException(status_code=400, detail="No data to export. Upload data first.")

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ExecSlate_{project['client'].replace(' ', '_')}_{timestamp}.pdf"
        file_path = EXPORT_DIR / filename
        plan = get_user_plan(request)

        try:
            export_pdf_enhanced(project, str(file_path), user_plan=plan)
            log(f"PDF exported for project {pid} (Plan: {plan})")
            return FileResponse(str(file_path), filename=filename, media_type="application/pdf")
        except Exception as e:
            logger.error(f"PDF export failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="PDF generation failed")

    @router.get("/export/ppt/{pid}")
    def export_ppt(pid: int, request: Request, user=Depends(require_user)):
        """Export project as PowerPoint"""
        user_email = user["email"]

        if "id" in user:
            project = db.get_project(pid, user["id"])
        else:
            project = next((x for x in projects if x["id"] == pid and x.get("user_email") == user_email), None)

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.get("generated"):
            raise HTTPException(status_code=400, detail="No data to export. Upload data first.")

        plan = get_user_plan(request)
        if not PLAN_LIMITS[plan]["ppt_export"]:
            if plan == 'demo':
                raise HTTPException(
                    status_code=403,
                    detail="PowerPoint export not available in demo. Sign up for free to unlock PDF/Word exports, or upgrade to Pro for full PowerPoint access."
                )
            else:
                raise HTTPException(
                    status_code=403,
                    detail="PowerPoint export requires Pro plan. Upgrade to unlock this feature."
                )

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"ExecSlate_{project['client'].replace(' ', '_')}_{timestamp}.pptx"
        file_path = EXPORT_DIR / filename

        try:
            export_ppt_enhanced(project, str(file_path), user_plan=plan)
            log(f"PowerPoint exported for project {pid} (Plan: {plan})")
            return FileResponse(
                str(file_path), filename=filename,
                media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation"
            )
        except Exception as e:
            logger.error(f"PowerPoint export failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="PowerPoint generation failed")

    @router.get("/export/docx/{pid}")
    def export_docx(pid: int, request: Request, user=Depends(require_user)):
        """Export project as Word document"""
        user_email = user["email"]

        if "id" in user:
            project = db.get_project(pid, user["id"])
        else:
            project = next((x for x in projects if x["id"] == pid and x.get("user_email") == user_email), None)

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        if not project.get("generated"):
            raise HTTPException(status_code=400, detail="No data to export")

        plan = get_user_plan(request)
        if plan == 'demo':
            raise HTTPException(
                status_code=403,
                detail="Word export not available in demo (PDF-only). Sign up free to unlock PDF + Word exports."
            )

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            clean_client = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(project.get('client', 'Client'))).replace(' ', '_')
            filename = f"ExecSlate_{clean_client}_{timestamp}.docx"
            path = EXPORT_DIR / filename
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)

            export_docx_enhanced(project, str(path), user_plan=plan)
            log(f"DOCX exported for project {pid} (Plan: {plan})")

            return FileResponse(
                str(path), filename=filename,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
        except Exception as e:
            logger.error(f"DOCX export failed: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to generate Word document")

