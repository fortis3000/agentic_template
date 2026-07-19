import base64
import shutil

import pymupdf
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.agents.config import FileConstraints
from src.api.main import (
    SESSIONS_DIR,
    UPLOADS_DIR,
    app,
    process_and_validate_file,
)

HTTP_200_OK = 200
HTTP_400_BAD_REQUEST = 400


@pytest.fixture
def client():
    return TestClient(app)


def create_test_pdf(text: str = "Dummy PDF", num_pages: int = 1) -> bytes:
    doc = pymupdf.open()
    for i in range(num_pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"{text} - Page {i + 1}")
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# --- Validation Unit Tests ---


def test_validate_file_accepted_mime_pdf():
    pdf_bytes = create_test_pdf("Test PDF")
    constraints = FileConstraints()
    result = process_and_validate_file(
        file_bytes=pdf_bytes,
        filename="test.pdf",
        mime_type="application/pdf",
        constraints=constraints,
    )
    assert result is not None


def test_validate_file_accepted_mime_txt():
    txt_bytes = b"Hello world"
    constraints = FileConstraints()
    result = process_and_validate_file(
        file_bytes=txt_bytes,
        filename="test.txt",
        mime_type="text/plain",
        constraints=constraints,
    )
    assert result is not None


def test_validate_file_accepted_mime_md():
    md_bytes = b"# Title\nContent"
    constraints = FileConstraints()
    result = process_and_validate_file(
        file_bytes=md_bytes,
        filename="test.md",
        mime_type="text/markdown",
        constraints=constraints,
    )
    assert result is not None


def test_validate_file_accepted_mime_html():
    html_bytes = b"<html><body><p>Hello</p></body></html>"
    constraints = FileConstraints()
    result = process_and_validate_file(
        file_bytes=html_bytes,
        filename="test.html",
        mime_type="text/html",
        constraints=constraints,
    )
    assert result is not None


def test_validate_file_rejected_mime():
    zip_bytes = b"PK\x03\x04"
    constraints = FileConstraints()
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_file(
            file_bytes=zip_bytes,
            filename="test.zip",
            mime_type="application/zip",
            constraints=constraints,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST


def test_validate_file_within_size_limit():
    constraints = FileConstraints(max_file_size_bytes=20 * 1024 * 1024)
    # 20 MB exactly
    data = b"0" * (20 * 1024 * 1024)
    result = process_and_validate_file(
        file_bytes=data,
        filename="large.txt",
        mime_type="text/plain",
        constraints=constraints,
    )
    assert result is not None


def test_validate_file_exceeds_size_limit():
    constraints = FileConstraints(max_file_size_bytes=20 * 1024 * 1024)
    # 20 MB + 1 byte
    data = b"0" * (20 * 1024 * 1024 + 1)
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_file(
            file_bytes=data,
            filename="toolarge.txt",
            mime_type="text/plain",
            constraints=constraints,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST


# --- API Integration Tests ---


def test_chat_with_text_file_attachment(client):
    txt_bytes = b"Hello world"
    txt_b64 = base64.b64encode(txt_bytes).decode("utf-8")

    payload = {
        "session_id": "test-file-session-1",
        "config_path": "configs/agent_config.yaml",
        "query": "What is in this file?",
        "files": [{"data": txt_b64, "mime_type": "text/plain", "filename": "test.txt"}],
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["status"] == "processing"

    # Stop and clean up
    client.post("/api/agent/stop/test-file-session-1")
    session_file = SESSIONS_DIR / "test-file-session-1.json"
    if session_file.exists():
        session_file.unlink()


def test_chat_with_multiple_files(client):
    txt_b64 = base64.b64encode(b"Hello world").decode("utf-8")
    md_b64 = base64.b64encode(b"# Markdown").decode("utf-8")

    payload = {
        "session_id": "test-file-session-2",
        "config_path": "configs/agent_config.yaml",
        "query": "Read these files",
        "files": [
            {"data": txt_b64, "mime_type": "text/plain", "filename": "hello.txt"},
            {"data": md_b64, "mime_type": "text/markdown", "filename": "readme.md"},
        ],
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_200_OK

    client.post("/api/agent/stop/test-file-session-2")
    session_file = SESSIONS_DIR / "test-file-session-2.json"
    if session_file.exists():
        session_file.unlink()


def test_chat_with_files_exceeds_max_count(client):
    # Default max_files_per_message is 5
    txt_b64 = base64.b64encode(b"Hello").decode("utf-8")
    files = [
        {"data": txt_b64, "mime_type": "text/plain", "filename": f"file_{i}.txt"} for i in range(6)
    ]

    payload = {
        "session_id": "test-file-session-3",
        "config_path": "configs/agent_config.yaml",
        "query": "Too many files",
        "files": files,
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_chat_with_unsupported_file_type(client):
    zip_b64 = base64.b64encode(b"PK\x03\x04").decode("utf-8")

    payload = {
        "session_id": "test-file-session-4",
        "config_path": "configs/agent_config.yaml",
        "query": "Unsupported file",
        "files": [{"data": zip_b64, "mime_type": "application/zip", "filename": "test.zip"}],
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_chat_with_oversized_file():
    # Covered by test_validate_file_exceeds_size_limit
    pass


def test_config_detail_includes_file_constraints(client):
    response = client.get("/api/configs/detail?config_path=configs/agent_config.yaml")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "acceptable_file_types" in data


def test_uploaded_files_endpoint(client):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = "test-uploads-session-1"
    session_upload_dir = UPLOADS_DIR / session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)

    # Create dummy uploaded file
    dummy_file = session_upload_dir / "doc.txt"
    dummy_file.write_text("dummy")

    try:
        response = client.get(f"/api/files/uploads/{session_id}")
        assert response.status_code == HTTP_200_OK
        data = response.json()
        assert "files" in data
        assert any(f["filename"] == "doc.txt" for f in data["files"])
    finally:
        # Clean up
        if session_upload_dir.exists():
            shutil.rmtree(session_upload_dir)


def test_delete_session_cleans_uploaded_files(client):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    session_id = "test-delete-session-1"
    session_upload_dir = UPLOADS_DIR / session_id
    session_upload_dir.mkdir(parents=True, exist_ok=True)

    dummy_file = session_upload_dir / "doc.txt"
    dummy_file.write_text("dummy")

    # Create dummy session file
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    session_file = SESSIONS_DIR / f"{session_id}.json"
    session_file.write_text("[]")

    response = client.delete(f"/api/sessions/{session_id}")
    assert response.status_code == HTTP_200_OK

    # Assert session file is removed
    assert not session_file.exists()
    # Assert upload dir is removed
    assert not session_upload_dir.exists()
