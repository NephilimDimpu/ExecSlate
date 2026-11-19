"""
Shared test setup.

Every environment variable is set BEFORE `app` is imported, so the suite never
touches the real database, never reads a developer's local .env, and never
makes a paid AI call. pytest loads conftest.py before collecting test modules,
so this runs first.
"""

import os
import sys
import glob
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="execslate-tests-"))

os.environ["DATABASE_URL"] = f"sqlite:///{_TMP.as_posix()}/test.db"
os.environ["ENV"] = "development"
# Blank every provider key so no test can reach a paid API, even if the
# developer has a .env in a parent directory.
for _key in (
    "OPENAI_API_KEY", "GEMINI_API_KEY", "GROQ_API_KEY",
    "CEREBRAS_API_KEY", "OPENROUTER_API_KEY", "RESEND_API_KEY",
):
    os.environ[_key] = ""


def sample(name):
    """A (filename, bytes, content-type) tuple ready for a multipart upload."""
    return (name, (SAMPLES / name).read_bytes(), "text/csv")


@pytest.fixture(scope="session")
def app_module():
    import app
    # The suite registers several accounts from one client address, which trips
    # the 5/minute limit on /register. Rate limiting isn't what these tests
    # exercise, so turn it off for the session.
    if hasattr(app.limiter, "enabled"):
        app.limiter.enabled = False
    return app


@pytest.fixture
def client(app_module):
    from fastapi.testclient import TestClient
    return TestClient(app_module.app)


@pytest.fixture
def signed_in(client):
    """A client logged in as a fresh account with no usage caps."""
    email = f"test-{uuid.uuid4().hex[:8]}@example.org"
    r = client.post("/register", data={
        "email": email, "password": "secret123", "confirm_password": "secret123",
        "selected_plan": "founding",
    }, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    return client


@pytest.fixture
def project(signed_in):
    """A new empty project; yields its id."""
    import re
    r = signed_in.post("/project/create", follow_redirects=False)
    return re.search(r"/report/(\d+)", r.headers["location"]).group(1)


@pytest.fixture(autouse=True)
def _clean_generated_exports():
    """Exports are written to disk; don't leave them in the repo."""
    yield
    for pattern in ("*_analytics_*", "execslate_analysis_*"):
        for path in glob.glob(str(ROOT / "exports" / pattern)):
            try:
                os.remove(path)
            except OSError:
                pass


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
