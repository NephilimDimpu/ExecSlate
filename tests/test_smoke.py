"""The public pages render and the app boots with no AI providers configured."""


def test_health_endpoint(client):
    assert client.get("/health").status_code == 200


def test_landing_page_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "ExecSlate" in r.text


def test_pricing_and_login_render(client):
    assert client.get("/pricing").status_code == 200
    assert client.get("/login").status_code == 200


def test_founding_signup_form_renders(client):
    r = client.get("/register?plan=founding")
    assert r.status_code == 200
    assert "Join as a Founding Analyst" in r.text


def test_app_runs_without_ai_providers(app_module):
    """Statistical fallback must work when no provider key is set."""
    import ai_providers
    assert ai_providers.is_ai_available() is False


def test_dashboard_requires_login(client):
    """Signed out, / is the landing page, not the dashboard."""
    assert "Active Engagements" not in client.get("/").text
