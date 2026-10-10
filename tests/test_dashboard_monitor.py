"""The dashboard reports what changed between uploads for each project."""

import re

from conftest import sample


def _new_project(client):
    r = client.post("/project/create", follow_redirects=False)
    return re.search(r"/report/(\d+)", r.headers["location"]).group(1)


def test_new_project_awaits_data(registered_client):
    _new_project(registered_client)
    page = registered_client.get("/").text
    assert "Where things stand" in page
    assert "Awaiting data" in page


def test_first_upload_sets_a_baseline(registered_client):
    pid = _new_project(registered_client)
    registered_client.post(f"/analytics/{pid}/upload", files=[("files", sample("q1_sales.csv"))],
                           data={"currency": "$"}, follow_redirects=False)
    page = registered_client.get("/").text
    assert "Baseline set" in page
    assert "Upload next period" in page


def test_second_upload_reports_the_real_change(registered_client):
    """Q1 -> Q2 revenue in the sample files rises 17.7%."""
    pid = _new_project(registered_client)
    for name in ("q1_sales.csv", "q2_sales.csv"):
        registered_client.post(f"/analytics/{pid}/upload", files=[("files", sample(name))],
                               data={"currency": "$"}, follow_redirects=False)

    page = registered_client.get("/").text
    match = re.search(r"is up (\d+\.\d)% since your previous upload", page)
    assert match, "no comparison rendered"
    assert match.group(1) == "17.7"
    assert "action-proceed" in page


def test_a_drop_is_flagged_for_review(registered_client):
    """Uploading the quarters backwards makes the metric fall."""
    pid = _new_project(registered_client)
    for name in ("q3_sales.csv", "q1_sales.csv"):
        registered_client.post(f"/analytics/{pid}/upload", files=[("files", sample(name))],
                               data={"currency": "$"}, follow_redirects=False)

    page = registered_client.get("/").text
    assert "worth a look" in page
    assert "action-review" in page


def test_history_query_skips_chart_blobs(registered_client, app_module):
    """The dashboard must not pull base64 images for every project."""
    pid = _new_project(registered_client)
    registered_client.post(f"/analytics/{pid}/upload", files=[("files", sample("q1_sales.csv"))],
                           data={"currency": "$"}, follow_redirects=False)

    history = app_module.db.get_analytics_session_history(int(pid))
    assert len(history) == 1
    assert "kpi_metrics" in history[0]
    assert "revenue_chart_b64" not in history[0]
