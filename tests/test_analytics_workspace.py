"""The analytics workspace: ingestion, chart choice, errors and exports."""

from conftest import sample


def upload(client, pid, *names, currency="$"):
    return client.post(
        f"/analytics/{pid}/upload",
        files=[("files", sample(n)) for n in names],
        data={"currency": currency},
        follow_redirects=False,
    )


def test_single_file_analysis(signed_in, project):
    assert upload(signed_in, project, "monthly_revenue.csv").status_code == 303
    page = signed_in.get(f"/analytics/{project}").text
    assert "<strong>36</strong> rows" in page


def test_time_series_data_gets_a_trend(signed_in, project):
    upload(signed_in, project, "monthly_revenue.csv")
    page = signed_in.get(f"/analytics/{project}").text
    assert "Pattern <strong>Increasing</strong>" in page


def test_categorical_data_is_not_given_a_fake_trend(signed_in, project):
    """Segment data has no time axis, so it must not be plotted as a trend."""
    upload(signed_in, project, "customer_segments.csv")
    page = signed_in.get(f"/analytics/{project}").text
    assert "Pattern <strong>Categorical</strong>" in page


def test_files_are_stacked_in_the_order_given(signed_in, project):
    assert upload(signed_in, project, "q1_sales.csv", "q2_sales.csv", "q3_sales.csv").status_code == 303
    assert "<strong>27</strong> rows" in signed_in.get(f"/analytics/{project}").text


def test_mismatched_columns_show_a_banner_not_an_error_page(signed_in, project):
    r = upload(signed_in, project, "monthly_revenue.csv", "customer_segments.csv")
    assert r.status_code == 303  # not a 400 error page

    page = signed_in.get(f"/analytics/{project}").text
    assert "analytics-error-banner" in page
    assert "Column mismatch" in page


def test_all_four_export_formats(signed_in, project):
    upload(signed_in, project, "monthly_revenue.csv")
    for fmt, magic in (("pdf", b"%PDF"), ("pptx", b"PK"), ("docx", b"PK"), ("xlsx", b"PK")):
        r = signed_in.get(f"/analytics/{project}/export/{fmt}")
        assert r.status_code == 200, fmt
        assert r.content.startswith(magic), fmt


def test_send_to_report_carries_the_work_across(signed_in, project):
    upload(signed_in, project, "monthly_revenue.csv")
    r = signed_in.post(f"/analytics/{project}/send-to-report",
                       data={"notes": "Margin pressure in APAC.", "pinned": "Revenue up"},
                       follow_redirects=False)
    assert r.headers["location"] == f"/report/{project}"

    report = signed_in.get(f"/report/{project}").text
    assert "Analytics draft received" in report
    assert "Margin pressure in APAC." in report


def test_editing_an_observation_persists(signed_in, project):
    upload(signed_in, project, "monthly_revenue.csv")
    r = signed_in.post(f"/api/analytics/{project}/insights",
                       json={"insights": ["Revenue grew on the back of APAC."]})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert "Revenue grew on the back of APAC." in signed_in.get(f"/analytics/{project}").text
