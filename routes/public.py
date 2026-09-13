# ==================== PUBLIC SELF-SERVE FUNNEL ====================
# Anonymous, no-signup analytics at /try — the front door.
# Visitors get N free analyses per browser session; exporting requires a
# free account (the natural conversion point), and once the free run-count
# is exhausted they must register to continue.

import os
import re
import json
import time
import uuid
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import RedirectResponse, FileResponse

import analytics_engine as engine

router = APIRouter(tags=["public"])
logger = logging.getLogger("ExecSlate")


# ── Anonymous result store ────────────────────────────────────────────────────
# Results live on the local filesystem, NOT in process memory: production runs
# `gunicorn -w 2`, so an upload handled by one worker must be readable by
# whichever worker serves the follow-up GET. Workers share the container disk.
# Only the derived analysis is kept (never the raw upload), written atomically,
# and pruned by age and count.

ANON_STORE_DIR = Path(os.getenv("ANON_STORE_DIR") or (Path(tempfile.gettempdir()) / "execslate_anon"))
ANON_MAX_ENTRIES = 200
ANON_TTL_SECONDS = 24 * 3600
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _path_for(token):
    # Token comes from a signed cookie, but validate anyway — it becomes a filename.
    if not token or not _TOKEN_RE.match(token):
        return None
    return ANON_STORE_DIR / f"{token}.json"


def _json_default(o):
    # numpy scalars -> native Python numbers so templates can still format them
    if hasattr(o, "item"):
        return o.item()
    return str(o)


def load_result(token):
    p = _path_for(token)
    if not p or not p.exists():
        return None
    try:
        if time.time() - p.stat().st_mtime > ANON_TTL_SECONDS:
            p.unlink(missing_ok=True)
            return None
        with p.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        logger.warning(f"Could not load anonymous result: {e}")
        return None


def save_result(token, result):
    p = _path_for(token)
    if not p:
        return
    ANON_STORE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{token}.{uuid.uuid4().hex}.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, default=_json_default)
    os.replace(tmp, p)  # atomic: a reader never sees a half-written file
    _prune()


def delete_result(token):
    p = _path_for(token)
    if p:
        try:
            p.unlink(missing_ok=True)
        except Exception:
            pass


def _prune():
    now = time.time()
    try:
        # Orphaned temp files from interrupted writes
        for t in ANON_STORE_DIR.glob("*.tmp"):
            try:
                if now - t.stat().st_mtime > 3600:
                    t.unlink(missing_ok=True)
            except Exception:
                pass
        files = []
        for f in ANON_STORE_DIR.glob("*.json"):
            try:
                files.append((f.stat().st_mtime, f))
            except Exception:
                pass
    except Exception:
        return

    files.sort(key=lambda x: x[0])
    live = []
    for mtime, f in files:
        if now - mtime > ANON_TTL_SECONDS:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        else:
            live.append(f)
    for f in live[:max(0, len(live) - ANON_MAX_ENTRIES)]:
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


def setup(app_module):
    templates = app_module.templates
    ANON_FREE_LIMIT = app_module.ANON_FREE_LIMIT

    def _anon_token(request: Request) -> str:
        tok = request.session.get("anon_token")
        if not tok or not _TOKEN_RE.match(tok):
            tok = uuid.uuid4().hex
            request.session["anon_token"] = tok
        return tok

    def _uses(request: Request) -> int:
        try:
            return int(request.session.get("anon_uses", 0))
        except (TypeError, ValueError):
            return 0

    def _flash(request: Request, msg: str):
        request.session["try_error"] = msg
        return RedirectResponse("/try", status_code=303)

    # ── The public workspace ────────────────────────────────────────────────

    @router.get("/try")
    def try_page(request: Request):
        user = request.session.get("user")
        result = load_result(request.session.get("anon_token"))
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

        # Statistical insights only: /try is unauthenticated and un-metered for
        # AI, so AI here would let anonymous traffic spend paid API credits.
        result, err = engine.analyze_dataframe(df, currency, use_ai=False)
        if err:
            return _flash(request, err)

        tok = _anon_token(request)
        try:
            save_result(tok, result)
        except Exception as e:
            logger.error(f"Could not store anonymous result: {e}")
            return _flash(request, "Your analysis ran but couldn't be saved. Please try again.")

        # Only count runs that actually produced a viewable result
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

        result = load_result(request.session.get("anon_token"))
        if not result:
            return _flash(request, "Upload a file first — there's nothing to export yet.")

        exporters = {
            "pdf":  ("export_analytics_pdf",  "application/pdf"),
            "pptx": ("export_analytics_pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
            "docx": ("export_analytics_docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            "xlsx": ("export_analytics_xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        }
        if fmt not in exporters:
            return _flash(request, "Unknown export format.")
        fn_name, media = exporters[fmt]

        project = {
            "client": "ExecSlate Analysis",
            "period": datetime.now().strftime("%B %Y"),
            "currency": result.get("currency", "$"),
        }

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = app_module.EXPORT_DIR / f"execslate_analysis_{ts}_{uuid.uuid4().hex[:6]}.{fmt}"

        try:
            import exports.analytics_export as exporter
            getattr(exporter, fn_name)(project, result, None, out_path)
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
        delete_result(request.session.get("anon_token"))
        return RedirectResponse("/try", status_code=303)
