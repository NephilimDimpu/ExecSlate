"""
Regression test for the growth-direction bug.

A file sorted by (month, region) ends on the smallest region of the latest
month. Comparing the first row to the last row therefore reported a decline
for a business that actually grew. Growth must be computed after grouping by
the detected date column.

samples/monthly_revenue.csv is exactly that shape: revenue rises every month,
but the last row (Dec, Asia Pacific) is smaller than the first (Jan, North
America).
"""

import pandas as pd

from conftest import SAMPLES


def _analysed_project(app_module):
    df = pd.read_csv(SAMPLES / "monthly_revenue.csv")
    project = {
        "id": 1,
        "client": "Growth Test",
        "currency": "$",
        "analysis_framework": "general",
        "column_map": {"revenue": "revenue", "region": "region"},
    }
    app_module.process_dataframe(project, df)
    return df, project


def test_naive_first_vs_last_row_would_mislead():
    """Guards the premise: row order really does point the wrong way."""
    df = pd.read_csv(SAMPLES / "monthly_revenue.csv")
    assert df["revenue"].iloc[-1] < df["revenue"].iloc[0]


def test_growth_is_measured_in_time_order(app_module):
    _, project = _analysed_project(app_module)
    assert project["trend"] == "Increasing"
    assert project["growth_rate"] > 0


def test_per_kpi_growth_also_uses_time_order(app_module):
    _, project = _analysed_project(app_module)
    revenue = project["kpi_metrics"]["revenue"]
    assert revenue["trend"] == "up"
    assert revenue["growth"] > 0
