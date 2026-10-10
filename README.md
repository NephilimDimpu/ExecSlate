# ExecSlate

![CI](https://github.com/NephilimDimpu/ExecSlate/actions/workflows/ci.yml/badge.svg)

Turn a business spreadsheet into a board-ready analysis — KPIs, the right chart
for the shape of the data, plain-English observations, and a PDF / PowerPoint /
Word / Excel deliverable — in about a minute.

**Try it without an account: [execslate.onrender.com/try](https://execslate.onrender.com/try)**

---

## The workflow

```
  CSV / Excel  ──►  Analytics workspace  ──►  Report  ──►  Export
  one or many       KPIs, charts,            SCQA narrative,   PDF · PPTX
  stacked in        editable observations,   frameworks,       DOCX · XLSX
  your order        pin to a draft           hypotheses, Q&A
                           │
                           └──►  Dashboard: what changed since last upload,
                                 and whether to proceed or review
```

Three places to start, depending on who you are:

| | |
|---|---|
| **`/try`** | Upload and get an analysis with no account. Exports need a free account. |
| **Analytics workspace** | Explore, edit the observations, pin what matters, carry it into a report. |
| **Report** | Framework-driven narrative (profitability, market entry, cost reduction, …), strategic hypotheses, and a Copilot that answers questions about the uploaded data. |

---

## Why it isn't just "CSV in, chart out"

**It picks the chart that matches the data.** A date column produces a trend
over time; a category column produces a ranking; neither produces a fabricated
trend line over row order. The AI prompt is told which shape it is, so it can't
narrate a trend that doesn't exist.

**Growth is computed in time order, not row order.** A file sorted by
`(month, region)` ends on the smallest region of the latest month. Comparing
the first row to the last row reports a decline for a business that grew — so
the engine groups by the detected date column first.

**The AI never decides, it only writes.** Dashboard labels (Proceed / Review /
Needs fresh data) come from explicit rules in [`monitor.py`](monitor.py). A
falling cost reads as good; falling revenue reads as bad; swings under 5% read
as flat. If every AI provider is down, the whole product still works on
statistical insights.

**Five AI providers, automatic failover.**
[`ai_providers.py`](ai_providers.py) tries OpenAI → Gemini → Groq → Cerebras →
OpenRouter, then falls back to statistics. Model output is parsed defensively
(markdown fences, stray prose, control characters inside JSON).

**The anonymous funnel survives multiple workers.** Production runs
`gunicorn -w 2`. Results are written atomically to a shared directory rather
than kept in one process's memory, so an upload handled by one worker is
readable by the other. Verified by a two-process test.

---

## Architecture

| Module | Responsibility |
|---|---|
| `app.py` | FastAPI app, dashboard, report generation, charts, auth helpers |
| `analytics_engine.py` | File ingestion, stacking, KPI detection, shape-aware analysis |
| `monitor.py` | Rule-based "what changed" and next-action labels (no AI) |
| `ai_providers.py` | Provider failover chain and response parsing |
| `enhanced_analysis.py` | Column typing, segmentation, period comparison, hypotheses |
| `agent_copilot.py` | Copilot Q&A over the uploaded dataframe |
| `database.py` | SQLAlchemy models (users, projects, analytics sessions, drafts, payments) |
| `routes/` | `public` (/try), `analytics`, `auth`, `exports`, `payments`, `admin`, `agent` |
| `exports/` | PDF, PowerPoint, Word and Excel builders |

**Stack:** FastAPI · SQLAlchemy (PostgreSQL in production, SQLite locally) ·
pandas · matplotlib · Jinja2 · ReportLab / python-pptx / python-docx / openpyxl ·
Razorpay · deployed on Render.

---

## Running locally

```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000
```

Configuration goes in a `.env` file (git-ignored). Everything is optional for
local use — without AI keys the app runs on statistical insights.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL; defaults to a local SQLite file |
| `SESSION_SECRET` | Cookie signing key; **required** when `ENV=production` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` | Any one enables AI insights; several enable failover |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Payments; without them the upgrade flow is disabled |
| `RESEND_API_KEY` | Transactional email |
| `ANON_FREE_LIMIT` | Free `/try` analyses per browser session (default 10) |
| `ANON_STORE_DIR` | Where anonymous results are cached (default: system temp) |

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite sets its own temporary database and blanks every provider key before
importing the app, so it never touches real data and never makes a paid API
call. It covers the monitor's rules, the public funnel end to end (analyse,
export gate, free limit, signup round-trip, path-traversal guard) and the
dashboard comparison against the sample files in [`samples/`](samples).

---

## Known limitations

- AI observations in the Analytics workspace currently fall back to statistical
  text: the call passes an argument `get_ai_response()` doesn't accept. The fix
  is held back until AI usage is metered per plan, since that path has no limit.
- `app.py` is still ~2,100 lines. Routes, the analysis engine, the monitor and
  the exporters have been extracted; report and chart generation are next.
- Anonymous `/try` results are cached for 24 hours and are lost on redeploy.
- Payments are one-time Razorpay orders, not recurring subscriptions, and are
  INR-only until international payments are enabled.
- Uploads are capped at 5 MB.
