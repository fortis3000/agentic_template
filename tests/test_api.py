import pytest
from fastapi.testclient import TestClient

from src.api.main import SESSIONS_DIR, app

HTTP_200_OK = 200


@pytest.fixture
def client():
    return TestClient(app)


def test_get_configs(client):
    response = client.get("/api/configs")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "configs" in data
    # Configs directory has at least one config
    assert len(data["configs"]) >= 1
    assert any("agent_config.yaml" in cfg for cfg in data["configs"])


def test_get_files(client):
    response = client.get("/api/files")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "files" in data
    assert isinstance(data["files"], list)


def test_get_sessions_empty_or_listed(client):
    response = client.get("/api/sessions")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "sessions" in data
    assert isinstance(data["sessions"], list)


def test_chat_and_stop_flow(client):
    # Trigger chat request
    payload = {
        "session_id": "test-session-123",
        "config_path": "configs/agent_config.yaml",
        "query": "Hello test agent!",
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["session_id"] == "test-session-123"
    assert data["status"] == "processing"

    # Stop execution immediately
    response = client.post("/api/agent/stop/test-session-123")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["status"] == "cancelled"

    # Try to retrieve session history
    response = client.get("/api/sessions/test-session-123")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["session_id"] == "test-session-123"
    assert isinstance(data["history"], list)

    # Clean up test session file if created
    session_file = SESSIONS_DIR / "test-session-123.json"
    if session_file.exists():
        session_file.unlink()
