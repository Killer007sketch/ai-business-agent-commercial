from fastapi.testclient import TestClient

from app import app


def test_demo_page():
    client = TestClient(app)
    response = client.get('/demo')
    assert response.status_code == 200
    assert 'AI Business Agent Starter Kit' in response.text
    assert 'Safe mode by default' in response.text
    assert 'Run high-risk test' in response.text
