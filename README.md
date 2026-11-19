# ExecSlate

![CI](https://github.com/NephilimDimpu/ExecSlate/actions/workflows/ci.yml/badge.svg)

Turn a business spreadsheet into a board-ready analysis — KPIs, the right chart
for the shape of the data, consulting-style observations, and a PDF /
PowerPoint / Word / Excel deliverable — in about a minute.

**Live:** [execslate.onrender.com](https://execslate.onrender.com) ·
[`/demo`](https://execslate.onrender.com/demo) opens a pre-populated account
with no signup. *(Free Render tier — the first request after a quiet period can
take up to a minute to wake.)*

---

## The workflow

```
  CSV / Excel  ──►  Analytics workspace  ──►  Report  ──►  Export
  one or many       KPIs, charts,            SCQA narrative,   PDF · PPTX
  stacked in        editable observations,   frameworks,       DOCX · XLSX
  your order        pinned to a draft        hypotheses, Q&A
```

**Analytics workspace** — upload one file or several, ordered; auto-detected
KPIs; a chart chosen to match the data; observations you can edit in place and
pin to a draft board; export in four formats, or carry the draft into a report.

**Report** — a framework-driven narrative (profitability, market entry, cost
reduction, growth, due diligence) in SCQA form, strategic hypotheses with
validation plans, executive Q&A, and a Copilot that answers questions about the
uploaded data.

---

## Why it isn't just "CSV in, chart out"

**It picks the chart that matches the data.** A date column produces a trend
over time; a category column produces a ranking; neither produces a fabricated
trend line over row order. The AI prompt is told which shape it is, so it can't
narrate a trend that doesn't exist.

**Growth is computed in time order, not row order.** A file sorted by
`(month, region)` ends on the smallest region of the latest month, so comparing
the first row to the last reports a decline for a business that grew. The
engine groups by the detected date column first — pinned by a regression test
in [`tests/test_report_growth.py`](tests/test_report_growth.py).

**Five AI providers, automatic failover.** [`ai_providers.py`](ai_providers.py)
tries OpenAI → Gemini → Groq → Cerebras → OpenRouter, then falls back to
statistical insights. Model output is parsed defensively: markdown fences,
stray prose around the JSON, and control characters inside strings. **The
product works end to end with no API key at all.**

**Recoverable errors stay recoverable.** A column mismatch across stacked files
returns an inline banner with the upload form still populated, not a dead-end
error page.

---

## Architecture

| Module | Responsibility |
|---|---|
| `app.py` | FastAPI app, dashboard, report generation, charts, auth helpers |
| `enhanced_analysis.py` | Column typing, KPI classification, segmentation, period comparison, hypotheses |
| `ai_providers.py` | Provider failover chain and defensive response parsing |
| `agent_copilot.py` | Copilot Q&A over the uploaded dataframe |
| `database.py` | SQLAlchemy models (users, projects, analytics sessions, drafts, payments) |
| `routes/` | `analytics`, `auth`, `exports`, `payments`, `admin`, `agent` |
| `exports/` | PDF, PowerPoint, Word and Excel builders |
| `samples/` | Sample CSVs covering each analysis path — see [samples/README.md](samples/README.md) |

**Stack:** FastAPI · SQLAlchemy (PostgreSQL in production, SQLite locally) ·
pandas · matplotlib · Jinja2 · ReportLab / python-pptx / python-docx / openpyxl ·
Razorpay · deployed on Render under `gunicorn -w 2`.

---

## Running locally

```bash
pip install -r requirements.txt
python app.py            # http://localhost:8000
```

Configuration goes in a `.env` file (git-ignored). All of it is optional
locally — without AI keys the app runs on statistical insights.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL URL; defaults to a local SQLite file |
| `SESSION_SECRET` | Cookie signing key; **required** when `ENV=production` |
| `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`, `OPENROUTER_API_KEY` | Any one enables AI insights; several enable failover |
| `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET` | Payments; without them the upgrade flow is disabled |
| `RESEND_API_KEY` | Transactional email |

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

The suite points at a temporary database and blanks every provider key before
importing the app, so it never touches real data and never makes a paid API
call. It covers the analytics workspace end to end (multi-file stacking, chart
selection for time-series vs categorical data, the mismatch banner, all four
export formats, the report handoff, editing observations) and the growth
regression above.

---

## Known limitations

- **AI observations in the analytics workspace never run.** The call at
  `routes/analytics.py:490` passes `max_tokens`, which `get_ai_response()`
  doesn't accept, so it always falls back to statistical text. The fix is held
  back until AI usage is metered per plan, since that path has no limit.
- `app.py` is ~2,100 lines. Routes and exporters have been extracted; report
  and chart generation are next.
- Public registration is currently gated: the open form is reachable at
  `/register?plan=founding`. A no-signup public trial (`/try`) exists on a
  branch and is not merged.
- Payments are one-time Razorpay orders, not recurring subscriptions, and are
  INR-only until international payments are enabled.
- Uploads are capped at 5 MB.
