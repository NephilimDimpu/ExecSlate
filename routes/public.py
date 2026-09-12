# ==================== PUBLIC SELF-SERVE FUNNEL ====================
# Anonymous, no-signup analytics at /try — the front door.
# Visitors get N free analyses per browser session; exporting requires a
# free account (the natural conversion point), and once the free run-count
# is exhausted they must register to continue.

import re
import uuid
import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, FileResponse

import analytics_engine as engine

router = APIRouter(tags=["public"])
logger = logging.getLogger("ExecSlate")

# Keep anonymous results in memory only. Each entry holds two base64 charts,
# so cap the store and evict oldest-first to bound memory on small dynos.
ANON_MAX_ENTRIES = 50


def setup(app_module):
    templates = app_module.templates
    anon_results = app_module.anon_results_mem
    ANON_FREE_LIMIT = app_module.ANON_FREE_LIMIT

    def _anon_token(request: Request) -> str:
        tok = request.session.get("anon_token")
        if not tok:
            tok = uuid.uuid4().hex
            request.session["anon_token"] = tok
        return tok

    def _uses(request: Request) -> int:
        return int(request.session.get("anon_uses", 0))

    def _store_result(tok: str, result: dict):
        # Evict oldest entries if we're at the cap
        while len(anon_results) >= ANON_MAX_ENTRIES:
            try:
                anon_results.pop(next(iter(anon_results)))
            except StopIteration:
                break
        anon_results[tok] = result

    def _flash(request: Request, msg: str):
        request.session["try_error"] = msg
        return RedirectResponse("/try", status_code=303)

    # ── The public workspace ────────────────────────────────────────────────

    @router.get("/try")
    def try_page(request: Request):
        user = request.session.get("user")
        tok = request.session.get("anon_token")
        result = anon_results.get(tok) if tok else None
        used = _uses(request)

        return templates.TemplateResponse(
            request=request,
            name="try.html",
            context={
                "request": request,
                "user": user,
                "result": result,
                "used": used,
                "limit": ANON_FREE_LIMIT,
                "remaining": max(0, ANON_FREE_LIMIT - used),
                "limit_reached": used >= ANON_FREE_LIMIT,
                "error": request.session.pop("try_error", None),
            },
        )

    # ── Anonymous analysis ──────────────────────────────────────────────────

    @router.post("/try/analyze")
    async def try_analyze(
        request: Request,
        files: List[UploadFile] = File(...),
        currency: str = Form("$"),
    ):
        user = request.session.get("user")
        used = _uses(request)

        # Signed-in users aren't metered here — they have their own workspace
        if not user and used >= ANON_FREE_LIMIT:
            return _flash(
                request,
                f"You've used all {ANON_FREE_LIMIT} free analyses. "
                "Create a free account to keep going.",
            )

        if not files:
            return _flash(request, "Please choose at least one CSV or Excel file.")

        files_data = [(f.filename, await f.read()) for f in files]

        df, err = engine.read_and_stack_files(files_data)
        if err:
            return _flash(request, err)

        result, err = engine.analyze_dataframe(df, currency)
        if err:
            return _flash(request, err)

        tok = _anon_token(request)
        _store_result(tok, result)

        if not user:
            request.session["anon_uses"] = used + 1

        return RedirectResponse("/try", status_code=303)

    # ── Export gate — the conversion point ──────────────────────────────────

    @router.get("/try/export/{fmt}")
    def try_export(fmt: str, request: Request):
        user = request.session.get("user")
        if not user:
            # This is the moment we ask for the account.
            request.session["try_error"] = (
                "Create a free account to download your report — it takes 20 seconds "
                "and your analysis will still be here."
            )
            return RedirectResponse("/register?next=/try", status_code=303)

        tok = request.session.get("anon_token")
        result = anon_results.get(tok) if tok else None
        if not result:
            return _flash(request, "Upload a file first — there's nothing to export yet.")

        if fmt not in ("pdf", "pptx", "docx", "xlsx"):
            return _flash(request, "Unknown export format.")

        project = {
            "client": "ExecSlate Analysis",
            "period": datetime.now().strftime("%B %Y"),
            "currency": result.get("currency", "$"),
        }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = app_module.EXPORT_DIR / f"execslate_analysis_{ts}.{fmt}"

        try:
            if fmt == "pdf":
                from exports.analytics_export import export_analytics_pdf as fn
                media = "application/pdf"
            elif fmt == "pptx":
                from exports.analytics_export import export_analytics_pptx as fn
                media = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            elif fmt == "docx":
                from exports.analytics_export import export_analytics_docx as fn
                media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            else:
                from exports.analytics_export import export_analytics_xlsx as fn
                media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

            fn(project, result, None, out_path)
        except Exception as e:
            logger.error(f"Public {fmt} export failed: {e}")
            return _flash(request, f"Could not generate the {fmt.upper()} file. Please try again.")

        return FileResponse(
            path=str(out_path),
            filename=f"execslate_analysis.{fmt}",
            media_type=media,
        )

    # ── Clear the current anonymous result ──────────────────────────────────

    @router.post("/try/reset")
    def try_reset(request: Request):
        tok = request.session.get("anon_token")
        if tok:
            anon_results.pop(tok, None)
        return RedirectResponse("/try", status_code=303)
