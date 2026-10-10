"""
ExecSlate — Portfolio Monitor

Turns a project's analysis history into a plain-English status line and a
recommendation ("Proceed" / "Review" / "Needs fresh data").

Deliberately deterministic and AI-free: every label comes from a rule that can
be pointed at and explained. AI may later be used to reword these sentences,
but it must never decide the label.
"""

from datetime import datetime, timezone

# ── Rules (the whole policy lives here) ──────────────────────────────────────
STALE_DAYS = 60      # no new upload for this long -> ask for fresh data
MOVE_PCT = 5.0       # smaller swings than this count as "steady"

ACTION_PROCEED = "Proceed"
ACTION_REVIEW = "Review"
ACTION_FRESH = "Needs fresh data"
ACTION_BASELINE = "Baseline set"
ACTION_AWAITING = "Awaiting data"


def _parse_dt(value):
    """Accept ISO strings (DB dicts) or datetimes (in-memory store)."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def _days_since(value, now=None):
    dt = _parse_dt(value)
    if not dt:
        return None
    # Stored timestamps are naive UTC (SQLite/Postgres now()), so compare in UTC.
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0, (now - dt).days)


def _pretty_date(value):
    dt = _parse_dt(value)
    return dt.strftime("%b %d") if dt else "an earlier date"


def _label_of(kpi, key):
    return (kpi or {}).get("label") or str(key).replace("_", " ").title()


def _primary_kpi(session):
    """Return (key, kpi_dict) for the session's primary metric."""
    kpis = session.get("kpi_metrics") or {}
    key = session.get("primary_col")
    if key and key in kpis:
        return key, kpis[key]
    if kpis:
        first = next(iter(kpis))
        return first, kpis[first]
    return None, None


def _pct_change(new, old):
    try:
        new, old = float(new), float(old)
    except (TypeError, ValueError):
        return None
    if old == 0:
        return None
    return (new - old) / abs(old) * 100.0


def _is_good(delta, direction):
    """A falling cost is good; a falling revenue is not."""
    if direction == "down_good":
        return delta < 0
    return delta > 0


def kpi_moves(latest, previous, limit=3):
    """Percentage moves for KPIs present in both runs, biggest first."""
    new_kpis = latest.get("kpi_metrics") or {}
    old_kpis = previous.get("kpi_metrics") or {}
    moves = []
    for key, kpi in new_kpis.items():
        if key not in old_kpis:
            continue
        delta = _pct_change(kpi.get("value"), old_kpis[key].get("value"))
        if delta is None:
            continue
        moves.append({
            "key": key,
            "label": _label_of(kpi, key),
            "delta": round(delta, 1),
            "direction": kpi.get("direction", "up_good"),
            "good": _is_good(delta, kpi.get("direction", "up_good")),
        })
    moves.sort(key=lambda m: abs(m["delta"]), reverse=True)
    return moves[:limit]


def project_status(project, sessions, now=None):
    """
    Build the dashboard status for one project.

    `sessions` must be newest-first. Returns a dict the template renders
    directly; never raises on odd data.
    """
    name = (project or {}).get("client") or "Untitled project"
    out = {
        "id": (project or {}).get("id"),
        "name": name,
        "action": ACTION_AWAITING,
        "headline": "No data yet — upload a file to start tracking this project.",
        "details": [],
        "runs": len(sessions or []),
        "days_since": None,
        "delta": None,
        "good": None,
    }
    if not sessions:
        return out

    latest = sessions[0]
    out["days_since"] = _days_since(latest.get("created_at"), now)
    out["currency"] = latest.get("currency") or "$"
    key, kpi = _primary_kpi(latest)
    out["primary_label"] = _label_of(kpi, key) if key else None

    # Rule 1: gone quiet -> ask for fresh data, whatever the numbers said.
    if out["days_since"] is not None and out["days_since"] > STALE_DAYS:
        out["action"] = ACTION_FRESH
        out["headline"] = (
            f"No new data in {out['days_since']} days. "
            f"Last run was {_pretty_date(latest.get('created_at'))}."
        )
        return out

    # Rule 2: only one run -> nothing to compare against yet.
    if len(sessions) == 1:
        out["action"] = ACTION_BASELINE
        bits = []
        if out.get("primary_label"):
            bits.append(f"tracking {out['primary_label'].lower()}")
        if latest.get("row_count"):
            bits.append(f"{latest['row_count']:,} rows")
        out["headline"] = (
            "First analysis saved" + (" — " + ", ".join(bits) if bits else "")
            + ". Upload next period's data to see what changed."
        )
        return out

    # Rule 3: two or more runs -> compare the primary metric.
    previous = sessions[1]
    moves = kpi_moves(latest, previous)
    out["moves"] = moves
    primary_move = next((m for m in moves if m["key"] == key), None) or (moves[0] if moves else None)

    if not primary_move:
        out["action"] = ACTION_PROCEED
        out["headline"] = (
            f"{out['runs']} analyses saved, but the metrics changed between runs "
            "so there is nothing directly comparable."
        )
        return out

    delta, good = primary_move["delta"], primary_move["good"]
    out["delta"] = delta
    out["good"] = good
    word = "up" if delta > 0 else "down"
    since = _pretty_date(previous.get("created_at"))

    if abs(delta) < MOVE_PCT:
        out["action"] = ACTION_PROCEED
        out["headline"] = (
            f"{primary_move['label']} is broadly flat ({delta:+.1f}%) since your "
            f"previous upload ({since})."
        )
    elif good:
        out["action"] = ACTION_PROCEED
        out["headline"] = (
            f"{primary_move['label']} is {word} {abs(delta):.1f}% since your "
            f"previous upload ({since})."
        )
    else:
        out["action"] = ACTION_REVIEW
        out["headline"] = (
            f"{primary_move['label']} is {word} {abs(delta):.1f}% since your "
            f"previous upload ({since}) — worth a look."
        )

    # Supporting detail: the next biggest movers, then data-quality caveats.
    for m in moves:
        if primary_move and m["key"] == primary_move["key"]:
            continue
        out["details"].append(
            f"{m['label']} {'up' if m['delta'] > 0 else 'down'} {abs(m['delta']):.1f}%"
        )
    confidence = latest.get("confidence")
    if isinstance(confidence, (int, float)) and confidence < 70:
        out["details"].append(f"data completeness only {int(confidence)}% — treat with caution")

    return out


def portfolio_summary(items):
    """One plain-English line covering every project."""
    total = len(items or [])
    if not total:
        return "No analyses yet. Create one and upload a file to get started."

    counts = {}
    for it in items:
        counts[it["action"]] = counts.get(it["action"], 0) + 1

    improving = sum(1 for it in items
                    if it["action"] == ACTION_PROCEED and (it.get("delta") or 0) >= MOVE_PCT)
    order = [
        (improving, "improving"),
        (counts.get(ACTION_REVIEW, 0), "need review"),
        (counts.get(ACTION_FRESH, 0), "need fresh data"),
        (counts.get(ACTION_BASELINE, 0), "awaiting a second upload"),
        (counts.get(ACTION_AWAITING, 0), "with no data yet"),
    ]
    parts = [f"{n} {word}" for n, word in order if n]
    noun = "analysis" if total == 1 else "analyses"
    if not parts:
        return f"{total} {noun} tracked."
    return f"{total} {noun}: " + ", ".join(parts) + "."
