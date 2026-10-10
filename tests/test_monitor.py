"""Unit tests for the rule-based project monitor (no app, no DB, no AI)."""

from datetime import datetime, timedelta

import monitor

NOW = datetime(2026, 9, 24)
PROJECT = {"id": 1, "client": "Acme"}


def run(days_ago, revenue, cost=None, confidence=100):
    """One stored analysis run, `days_ago` days old."""
    kpis = {"revenue": {
        "label": "Revenue", "value": revenue, "avg": revenue / 10,
        "format": "currency", "direction": "up_good",
    }}
    if cost is not None:
        kpis["cost"] = {
            "label": "Cost", "value": cost, "avg": cost / 10,
            "format": "currency", "direction": "down_good",
        }
    return {
        "created_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "currency": "$", "row_count": 36, "confidence": confidence,
        "trend": "Increasing", "growth_rate": 5.0,
        "primary_col": "revenue", "kpi_metrics": kpis,
    }


def status(sessions):
    return monitor.project_status(PROJECT, sessions, now=NOW)


def test_no_runs_is_awaiting_data():
    assert status([])["action"] == monitor.ACTION_AWAITING


def test_single_run_is_a_baseline():
    s = status([run(1, 100)])
    assert s["action"] == monitor.ACTION_BASELINE
    assert "First analysis saved" in s["headline"]


def test_rising_revenue_proceeds():
    s = status([run(1, 120), run(31, 100)])
    assert s["action"] == monitor.ACTION_PROCEED
    assert s["delta"] == 20.0
    assert "up 20.0%" in s["headline"]


def test_falling_revenue_asks_for_review():
    s = status([run(1, 80), run(31, 100)])
    assert s["action"] == monitor.ACTION_REVIEW
    assert "down 20.0%" in s["headline"]


def test_small_moves_read_as_flat():
    s = status([run(1, 101), run(31, 100)])
    assert s["action"] == monitor.ACTION_PROCEED
    assert "flat" in s["headline"]


def test_quiet_project_asks_for_fresh_data():
    s = status([run(90, 100), run(150, 90)])
    assert s["action"] == monitor.ACTION_FRESH
    assert "90 days" in s["headline"]


def test_falling_cost_is_good_news():
    """A metric marked down_good improves when it falls."""
    sessions = [{
        "created_at": (NOW - timedelta(days=d)).isoformat(),
        "primary_col": "cost", "confidence": 100, "row_count": 10, "currency": "$",
        "kpi_metrics": {"cost": {
            "label": "Cost", "value": v, "format": "currency", "direction": "down_good",
        }},
    } for d, v in ((1, 80), (31, 100))]
    s = status(sessions)
    assert s["action"] == monitor.ACTION_PROCEED
    assert s["good"] is True


def test_details_mention_other_movers_and_weak_data():
    s = status([run(1, 120, cost=50, confidence=55), run(31, 100, cost=40)])
    assert any("Cost" in d for d in s["details"])
    assert any("completeness" in d for d in s["details"])


def test_portfolio_summary_counts_each_state():
    items = [
        status([run(1, 120), run(31, 100)]),   # improving
        status([run(1, 80), run(31, 100)]),    # review
        status([run(90, 100), run(150, 90)]),  # stale
        status([]),                            # no data
    ]
    line = monitor.portfolio_summary(items)
    assert "4 analyses" in line
    assert "1 improving" in line
    assert "1 need review" in line
    assert "1 need fresh data" in line


def test_portfolio_summary_handles_empty():
    assert "No analyses yet" in monitor.portfolio_summary([])


def test_bad_timestamps_do_not_crash():
    broken = [dict(run(1, 100), created_at="not-a-date"),
              dict(run(31, 90), created_at=None)]
    assert monitor.project_status(PROJECT, broken, now=NOW)["action"]
