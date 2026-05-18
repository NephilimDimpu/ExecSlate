# ==================== ANALYTICS ROUTES ====================

import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter(tags=["analytics"])
logger = logging.getLogger("ExecSlate")


class DraftPayload(BaseModel):
    name: Optional[str] = "Draft"
    kpi_snapshot: Optional[List[str]] = []
    selected_insights: Optional[List[str]] = []
    notes: Optional[str] = ""


def setup(app_module):
    db = app_module.db
    templates = app_module.templates
    require_user = app_module.require_user

    @router.get("/analytics/{pid}")
    def analytics_workspace(pid: int, request: Request, user=Depends(require_user)):
        """Analytics exploration workspace for a project."""
        if "id" in user:
            project = db.get_project(pid, user["id"])
        else:
            from app import projects
            project = next(
                (x for x in projects if x.get("id") == pid and x.get("user_email") == user["email"]),
                None,
            )

        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        drafts = []
        if "id" in user:
            try:
                drafts = db.get_analytics_drafts(pid)
            except Exception:
                drafts = []

        return templates.TemplateResponse(
            request=request,
            name="analytics.html",
            context={
                "request": request,
                "user": user,
                "project": project,
                "drafts": drafts,
            },
        )

    @router.post("/api/analytics/{pid}/draft")
    async def save_analytics_draft(pid: int, payload: DraftPayload, request: Request):
        """Save a pinned analytics draft."""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if "id" not in user:
            return JSONResponse({"ok": False, "error": "Demo users cannot save drafts"}, status_code=403)

        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            draft_id = db.create_analytics_draft(
                project_id=pid,
                name=payload.name or "Draft",
                kpi_snapshot=payload.kpi_snapshot or [],
                selected_insights=payload.selected_insights or [],
                notes=payload.notes or "",
            )
            return {"ok": True, "draft_id": draft_id}
        except Exception as e:
            logger.error(f"Failed to save analytics draft: {e}")
            raise HTTPException(status_code=500, detail="Could not save draft")

    @router.get("/api/analytics/{pid}/drafts")
    def list_analytics_drafts(pid: int, request: Request):
        """Return saved drafts for a project."""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if "id" not in user:
            return {"drafts": []}

        project = db.get_project(pid, user["id"])
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        drafts = db.get_analytics_drafts(pid)
        return {"drafts": drafts}
