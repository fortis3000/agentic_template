import pytest
from fastapi.testclient import TestClient

from src.api.main import SESSIONS_DIR, app

HTTP_200_OK = 200
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404
HTTP_422_UNPROCESSABLE_ENTITY = 422


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


def test_chat_invalid_session_id(client):
    payload = {
        "session_id": "../../invalid/session",
        "config_path": "configs/agent_config.yaml",
        "query": "Hello",
    }
    response = client.post("/api/agent/chat", json=payload)
    # FastAPI returns 422 for pydantic validation errors
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_chat_invalid_config_path_traversal(client):
    payload = {
        "session_id": "valid-session-id",
        "config_path": "configs/../../../../etc/passwd",
        "query": "Hello",
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_chat_nonexistent_config_path(client):
    payload = {
        "session_id": "valid-session-id",
        "config_path": "configs/nonexistent_config_file_name.yaml",
        "query": "Hello",
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_chat_invalid_config_path_extension(client):
    payload = {
        "session_id": "valid-session-id",
        "config_path": "configs/agent_config.txt",
        "query": "Hello",
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_422_UNPROCESSABLE_ENTITY


def test_get_session_invalid_id(client):
    response = client.get("/api/sessions/invalid_id!")
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_stop_agent_invalid_id(client):
    response = client.post("/api/agent/stop/invalid_id!")
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_stream_agent_invalid_id(client):
    response = client.get("/api/agent/stream/invalid_id!")
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_delete_session_success(client):
    # 1. Create a dummy session file first
    session_id = "test-delete-session-abc"
    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text("[]", encoding="utf-8")
    assert session_file.exists()

    # 2. Delete the session
    response = client.delete(f"/api/sessions/{session_id}")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["session_id"] == session_id
    assert data["status"] == "deleted"

    # 3. Assert the file is deleted
    assert not session_file.exists()


def test_delete_session_not_found(client):
    response = client.delete("/api/sessions/nonexistent-session-id")
    assert response.status_code == HTTP_404_NOT_FOUND


def test_delete_session_invalid_id(client):
    response = client.delete("/api/sessions/invalid_id!")
    assert response.status_code == HTTP_400_BAD_REQUEST
