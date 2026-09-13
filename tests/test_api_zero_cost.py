import os
from pathlib import Path

from fastapi.testclient import TestClient

# Ensure this test uses an isolated SQLite database.
TEST_DB = Path("test_commercial.db")
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"

from app import app  # noqa: E402


def test_create_opportunity_reports_zero_llm_calls():
    client = TestClient(app)
    response = client.post(
        "/opportunities",
        json={
            "source": "test",
            "title": "n8n API automation",
            "budget_max_usd": 500,
            "problem": "Build webhook workflow automation",
            "requirements": ["n8n", "API", "webhook"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["llm_calls"] == 0
