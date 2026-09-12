# ==================== ANALYTICS ROUTES ====================
# Analytics tab is fully independent from the Report/Project upload pipeline.
# Users upload data here for exploration; Report tab is for final deliverable generation.

import logging

from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, RedirectResponse, FileResponse
from pydantic import BaseModel
from typing import List, Optional

# Shared analysis pipeline — identical logic powers the anonymous /try funnel.
import analytics_engine as engine

router = APIRouter(tags=["analytics"])
logger = logging.getLogger("ExecSlate")

MAX_ANALYTICS_FILE_SIZE = engine.MAX_UPLOAD_SIZE



# ── Pydantic model for draft saving ───────────────────────────────────────────

class DraftPayload(BaseModel):
    name: Optional[str] = "Draft"
    kpi_snapshot: Optional[List[str]] = []
    selected_insights: Optional[List[str]] = []
    notes: Optional[str] = ""


class InsightsPayload(BaseModel):
    insights: List[str]


# ── Route setup ────────────────────────────────────────────────────────────────

def setup(app_module):
    db = app_module.db
    templates = app_module.templates
    require_user = app_module.require_user
    ea = app_module.ea
    ai_providers = app_module.ai_providers
    is_demo_user = app_module.is_demo_user

    def _is_db_user(user):
        """Registered users have a DB id; admin/demo are in-memory."""
        return "id" in user

    def _find_project(pid, user):
        """Look up a project for both DB-backed and in-memory accounts."""
        if _is_db_user(user):
            return db.get_project(pid, user["id"])
        return next(
            (x for x in app_module.projects
             if x.get("id") == pid and x.get("user_email") == user["email"]),
            None,
        )

    def _save_session(pid, user, **kw):
        if _is_db_user(user):
            db.create_analytics_session(project_id=pid, **kw)
        else:
            app_module.analytics_sessions_mem[pid] = {"id": pid, "project_id": pid, **kw}

    def _latest_session(pid, user):
        if _is_db_user(user):
            return db.get_latest_analytics_session(pid)
        return app_module.analytics_sessions_mem.get(pid)

    def _save_draft(pid, user, name, kpi_snapshot, selected_insights, notes):
        if _is_db_user(user):
            return db.create_analytics_draft(
                project_id=pid, name=name,
                kpi_snapshot=kpi_snapshot, selected_insights=selected_insights, notes=notes,
            )
        store = app_module.analytics_drafts_mem.setdefault(pid, [])
        draft_id = len(store) + 1
        store.insert(0, {
            "id": draft_id, "project_id": pid, "name": name,
            "kpi_snapshot": kpi_snapshot, "selected_insights": selected_insights,
            "notes": notes, "created_at": None,
        })
        return draft_id

    def _list_drafts(pid, user):
        if _is_db_user(user):
            return db.get_analytics_drafts(pid)
        return app_module.analytics_drafts_mem.get(pid, [])

    def _flash_error(request, pid, msg):
        """Soft, recoverable upload error: stash it and bounce back to the
        upload page so the user can fix and retry without losing the page."""
        request.session["analytics_error"] = msg
        return RedirectResponse(f"/analytics/{pid}", status_code=303)

    def _update_session_insights(pid, user, insights):
        """Persist edited insight list, dual-storage aware."""
        if _is_db_user(user):
            return db.update_analytics_session_insights(pid, insights)
        sess = app_module.analytics_sessions_mem.get(pid)
        if not sess:
            return False
        sess["ai_insights"] = list(insights or [])
        return True

    def _update_project_working_theory(pid, user, text):
        """Append/replace project working_theory, dual-storage aware."""
        if _is_db_user(user):
            db.update_project(pid, user["id"], working_theory=text)
            return True
        for p in app_module.projects:
            if p.get("id") == pid and p.get("user_email") == user["email"]:
                p["working_theory"] = text
                return True
        return False

    # ── Analytics workspace page ──────────────────────────────────────────────

    @router.get("/analytics/{pid}")
    def analytics_workspace(pid: int, request: Request, user=Depends(require_user)):
        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        session = None
        drafts = []
        try:
            session = _latest_session(pid, user)
            drafts = _list_drafts(pid, user)
        except Exception:
            pass

        # Pop any soft upload error stashed by a failed upload attempt
        upload_error = request.session.pop("analytics_error", None)

        return templates.TemplateResponse(
            request=request,
            name="analytics.html",
            context={
                "request": request,
                "user": user,
                "project": project,
                "session": session,
                "drafts": drafts,
                "upload_error": upload_error,
            },
        )

    # ── Independent analytics file upload ─────────────────────────────────────

    @router.post("/analytics/{pid}/upload")
    async def analytics_upload(
        pid: int,
        request: Request,
        files: List[UploadFile] = File(...),
        currency: str = Form("$"),
        user=Depends(require_user),
    ):
        if is_demo_user(user):
            raise HTTPException(status_code=403, detail="Demo accounts cannot upload in Analytics. Please register a free account.")

        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # ── Read files in the user's chosen order, then run the shared engine ──
        files_data = [(f.filename, await f.read()) for f in files]

        df, err = engine.read_and_stack_files(files_data)
        if err:
            return _flash_error(request, pid, err)

        result, err = engine.analyze_dataframe(df, currency)
        if err:
            return _flash_error(request, pid, err)

        result.pop("chart_strategy", None)  # not part of the stored session schema

        # ── Save session (DB for registered users, in-memory for admin/demo) ──
        try:
            _save_session(pid, user, **result)
        except Exception as e:
            logger.error(f"Failed to save analytics session: {e}")
            raise HTTPException(status_code=500, detail="Analysis complete but could not save session.")

        return RedirectResponse(f"/analytics/{pid}", status_code=303)

    # ── Save analytics draft ──────────────────────────────────────────────────

    @router.post("/api/analytics/{pid}/draft")
    async def save_analytics_draft(pid: int, payload: DraftPayload, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if is_demo_user(user):
            return JSONResponse({"ok": False, "error": "Demo accounts cannot save drafts"}, status_code=403)

        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        try:
            draft_id = _save_draft(
                pid, user,
                name=payload.name or "Draft",
                kpi_snapshot=payload.kpi_snapshot or [],
                selected_insights=payload.selected_insights or [],
                notes=payload.notes or "",
            )
            return {"ok": True, "draft_id": draft_id}
        except Exception as e:
            logger.error(f"Failed to save draft: {e}")
            raise HTTPException(status_code=500, detail="Could not save draft")

    # ── List saved drafts ────────────────────────────────────────────────────

    @router.get("/api/analytics/{pid}/drafts")
    def list_analytics_drafts(pid: int, request: Request):
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return {"drafts": _list_drafts(pid, user)}

    # ── Edit AI insights inline ──────────────────────────────────────────────

    @router.post("/api/analytics/{pid}/insights")
    async def update_insights(pid: int, payload: InsightsPayload, request: Request):
        """Persist edited insight text back to the latest analytics session."""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if is_demo_user(user):
            return JSONResponse({"ok": False, "error": "Demo accounts cannot edit insights"}, status_code=403)

        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Sanitise: strip whitespace, drop empties, cap each item length
        cleaned = [str(s).strip()[:600] for s in (payload.insights or []) if str(s).strip()]
        try:
            ok = _update_session_insights(pid, user, cleaned)
            if not ok:
                return JSONResponse({"ok": False, "error": "No active analytics session to edit. Upload data first."}, status_code=400)
            return {"ok": True, "count": len(cleaned)}
        except Exception as e:
            logger.error(f"Failed to update insights: {e}")
            raise HTTPException(status_code=500, detail="Could not save edits")

    # ── Send analytics work to the Report tab ────────────────────────────────

    @router.post("/analytics/{pid}/send-to-report")
    async def send_to_report(
        pid: int,
        request: Request,
        notes: str = Form(""),
        pinned: str = Form(""),  # newline-joined pinned insights
    ):
        """Carry the current analytics narrative into the Report tab's working
        theory, then redirect to the Report. Non-destructive: prepends to any
        existing working_theory with a clear timestamped header."""
        user = request.session.get("user")
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if is_demo_user(user):
            return _flash_error(request, pid, "Demo accounts cannot send analytics to the Report. Please register.")

        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        # Build a clean carry-over block from the latest session + this form data
        session = _latest_session(pid, user) or {}
        insights = session.get("ai_insights") or []
        primary = session.get("primary_col") or ""
        trend_lbl = session.get("trend") or ""

        from datetime import datetime
        header = f"--- Analytics carry-over ({datetime.now().strftime('%Y-%m-%d %H:%M')}) ---"
        parts = [header]
        if primary or trend_lbl:
            parts.append(f"Primary metric: {primary} | Pattern: {trend_lbl}")
        if insights:
            parts.append("\nKey observations:")
            parts.extend(f"• {ins}" for ins in insights)
        pinned_lines = [p.strip() for p in (pinned or "").split("\n") if p.strip()]
        if pinned_lines:
            parts.append("\nPinned for the report:")
            parts.extend(f"• {p}" for p in pinned_lines)
        if notes and notes.strip():
            parts.append(f"\nAnalyst notes:\n{notes.strip()}")
        carry_block = "\n".join(parts)

        # Prepend to existing working_theory (preserve any prior context)
        existing = (project.get("working_theory") or "").strip()
        new_theory = carry_block if not existing else f"{carry_block}\n\n{existing}"

        try:
            _update_project_working_theory(pid, user, new_theory)
        except Exception as e:
            logger.error(f"send-to-report failed: {e}")

        # Flash flag so the Report page can show a "Draft arrived" banner.
        n_obs = len(insights)
        n_pinned = len(pinned_lines)
        request.session["analytics_carryover"] = {
            "pid": pid,
            "n_observations": n_obs,
            "n_pinned": n_pinned,
            "has_notes": bool(notes and notes.strip()),
        }

        return RedirectResponse(f"/report/{pid}", status_code=303)

    # ── Export the Analytics workspace ───────────────────────────────────────

    def _do_analytics_export(pid, request, user, fmt):
        project = _find_project(pid, user)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        session = _latest_session(pid, user)
        if not session:
            return _flash_error(request, pid, "Upload data first — there is no analytics session to export yet.")

        drafts = _list_drafts(pid, user)
        latest_draft = drafts[0] if drafts else None

        import re
        safe_client = re.sub(r"[^A-Za-z0-9_-]+", "_", str(project.get("client") or "report")).strip("_") or "report"
        from datetime import datetime as _dt
        ts = _dt.now().strftime("%Y%m%d_%H%M%S")

        try:
            if fmt == "pdf":
                from exports.analytics_export import export_analytics_pdf
                out_path = app_module.EXPORT_DIR / f"{safe_client}_analytics_{ts}.pdf"
                export_analytics_pdf(project, session, latest_draft, out_path)
                media = "application/pdf"
                ext = "pdf"
            elif fmt == "pptx":
                from exports.analytics_export import export_analytics_pptx
                out_path = app_module.EXPORT_DIR / f"{safe_client}_analytics_{ts}.pptx"
                export_analytics_pptx(project, session, latest_draft, out_path)
                media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
                ext = "pptx"
            elif fmt == "docx":
                from exports.analytics_export import export_analytics_docx
                out_path = app_module.EXPORT_DIR / f"{safe_client}_analytics_{ts}.docx"
                export_analytics_docx(project, session, latest_draft, out_path)
                media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                ext = "docx"
            elif fmt == "xlsx":
                from exports.analytics_export import export_analytics_xlsx
                out_path = app_module.EXPORT_DIR / f"{safe_client}_analytics_{ts}.xlsx"
                export_analytics_xlsx(project, session, latest_draft, out_path)
                media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                ext = "xlsx"
            else:
                raise HTTPException(status_code=400, detail="Unknown export format")
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Analytics {fmt.upper()} export failed: {e}")
            raise HTTPException(status_code=500, detail=f"Could not generate {fmt.upper()}: {e}")

        return FileResponse(
            path=str(out_path),
            filename=f"{safe_client}_analytics.{ext}",
            media_type=media,
        )

    @router.get("/analytics/{pid}/export/pdf")
    def export_analytics_pdf_route(pid: int, request: Request, user=Depends(require_user)):
        return _do_analytics_export(pid, request, user, "pdf")

    @router.get("/analytics/{pid}/export/pptx")
    def export_analytics_pptx_route(pid: int, request: Request, user=Depends(require_user)):
        return _do_analytics_export(pid, request, user, "pptx")

    @router.get("/analytics/{pid}/export/docx")
    def export_analytics_docx_route(pid: int, request: Request, user=Depends(require_user)):
        return _do_analytics_export(pid, request, user, "docx")

    @router.get("/analytics/{pid}/export/xlsx")
    def export_analytics_xlsx_route(pid: int, request: Request, user=Depends(require_user)):
        return _do_analytics_export(pid, request, user, "xlsx")
