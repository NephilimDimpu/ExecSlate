"""The public /try funnel: analyse without an account, sign up to export."""

import re

from conftest import sample


def test_landing_and_pricing_are_open(client):
    landing = client.get("/")
    assert landing.status_code == 200
    assert "Private Beta" not in landing.text
    assert 'href="/try"' in landing.text

    pricing = client.get("/pricing")
    assert "Public Registration Closed" not in pricing.text
    assert "Upgrade to Pro" in pricing.text


def test_register_page_is_open_and_has_founding_variant(client):
    assert "Create your free account" in client.get("/register").text
    assert "Join as a Founding Analyst" in client.get("/register?plan=founding").text


def test_anonymous_analysis_then_export_gate(client):
    assert "Turn a spreadsheet" in client.get("/try").text

    r = client.post("/try/analyze", files=[("files", sample("monthly_revenue.csv"))],
                    data={"currency": "$"}, follow_redirects=False)
    assert r.status_code == 303

    page = client.get("/try").text
    assert "Your analysis is ready" in page
    assert "Increasing" in page  # time-series detected

    gated = client.get("/try/export/pdf", follow_redirects=False)
    assert gated.headers.get("location") == "/register?next=/try"


def test_categorical_data_is_not_given_a_fake_trend(client):
    client.post("/try/analyze", files=[("files", sample("customer_segments.csv"))],
                data={"currency": "$"}, follow_redirects=False)
    assert "Categorical" in client.get("/try").text


def test_files_are_stacked_in_the_order_given(client):
    client.post("/try/analyze", files=[
        ("files", sample("q1_sales.csv")),
        ("files", sample("q2_sales.csv")),
        ("files", sample("q3_sales.csv")),
    ], data={"currency": "$"}, follow_redirects=False)
    assert "<strong>27</strong> rows" in client.get("/try").text


def test_mismatched_columns_show_a_banner_not_an_error_page(client):
    r = client.post("/try/analyze", files=[
        ("files", sample("monthly_revenue.csv")),
        ("files", sample("customer_segments.csv")),
    ], data={"currency": "$"}, follow_redirects=False)
    assert r.status_code == 303

    page = client.get("/try").text
    assert "Column mismatch" in page
    assert "2</strong> of 2" in page  # a failed run costs no free credit


def test_free_limit_is_enforced(client):
    for name in ("monthly_revenue.csv", "customer_segments.csv", "q1_sales.csv"):
        client.post("/try/analyze", files=[("files", sample(name))],
                    data={"currency": "$"}, follow_redirects=False)
    assert "used all 2 free analyses" in client.get("/try").text


def test_signup_returns_to_the_analysis_and_unlocks_exports(client):
    client.post("/try/analyze", files=[("files", sample("monthly_revenue.csv"))],
                data={"currency": "$"}, follow_redirects=False)

    assert 'name="next" value="/try"' in client.get("/register?next=/try").text

    r = client.post("/register", data={
        "email": "funnel@example.org", "password": "secret123",
        "confirm_password": "secret123", "next": "/try",
    }, follow_redirects=False)
    assert r.headers.get("location") == "/try"
    assert "Your analysis is ready" in client.get("/try").text

    for fmt, magic in (("pdf", b"%PDF"), ("xlsx", b"PK"), ("docx", b"PK"), ("pptx", b"PK")):
        got = client.get(f"/try/export/{fmt}")
        assert got.status_code == 200
        assert got.content.startswith(magic), fmt


def test_reset_clears_the_current_result(client):
    client.post("/try/analyze", files=[("files", sample("monthly_revenue.csv"))],
                data={"currency": "$"}, follow_redirects=False)
    client.post("/try/reset", follow_redirects=False)
    assert "Turn a spreadsheet" in client.get("/try").text


def test_offsite_redirects_are_refused(client):
    assert 'value="//evil.example"' not in client.get("/register?next=//evil.example").text


def test_result_tokens_cannot_escape_the_store_directory():
    import routes.public as public
    assert public._path_for("../../etc/passwd") is None
    assert public._path_for("not-a-token") is None
    assert public._path_for("a" * 32) is not None
