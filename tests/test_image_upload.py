import base64
import io

import pytest
from PIL import Image
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api.main import SESSIONS_DIR, app, process_and_validate_image

HTTP_200_OK = 200
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404
HTTP_422_UNPROCESSABLE_ENTITY = 422


@pytest.fixture
def client():
    return TestClient(app)


def create_dummy_image(width: int, height: int, format: str = "PNG") -> bytes:
    """Helper to generate a dummy image in memory."""
    img = Image.new("RGB", (width, height), color="blue")
    buf = io.BytesIO()
    img.save(buf, format=format)
    return buf.getvalue()


def test_process_and_validate_image_valid():
    # A valid image within bounds (512x512)
    img_bytes = create_dummy_image(512, 512, "PNG")
    processed_bytes, resolved_mime = process_and_validate_image(
        image_bytes=img_bytes,
        mime_type="image/png",
        acceptable_types=["image/png", "image/jpeg"],
        min_w=128,
        min_h=128,
        max_w=1024,
        max_h=1024,
    )
    assert resolved_mime == "image/png"
    # Dimensions should remain 512x512
    img = Image.open(io.BytesIO(processed_bytes))
    assert img.size == (512, 512)


def test_process_and_validate_image_below_lower_limit():
    # Image below minimum width/height (100x200 vs min 128x128)
    img_bytes = create_dummy_image(100, 200, "PNG")
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_image(
            image_bytes=img_bytes,
            mime_type="image/png",
            acceptable_types=["image/png"],
            min_w=128,
            min_h=128,
            max_w=1024,
            max_h=1024,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST
    assert "below the minimum allowed limit" in exc_info.value.detail


def test_process_and_validate_image_unacceptable_type():
    img_bytes = create_dummy_image(500, 500, "GIF")
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_image(
            image_bytes=img_bytes,
            mime_type="image/gif",
            acceptable_types=["image/png", "image/jpeg"],
            min_w=128,
            min_h=128,
            max_w=1024,
            max_h=1024,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST
    assert "Unsupported image format" in exc_info.value.detail


def test_process_and_validate_image_resizing_aspect_ratio():
    # Image exceeding upper limits: 2000x1000.
    # Max allowed: 1000x1000.
    # Aspect ratio resizing should yield 1000x500.
    img_bytes = create_dummy_image(2000, 1000, "JPEG")
    processed_bytes, resolved_mime = process_and_validate_image(
        image_bytes=img_bytes,
        mime_type="image/jpeg",
        acceptable_types=["image/jpeg"],
        min_w=128,
        min_h=128,
        max_w=1000,
        max_h=1000,
    )
    assert resolved_mime == "image/jpeg"
    img = Image.open(io.BytesIO(processed_bytes))
    assert img.size == (1000, 500)


def test_get_config_detail_endpoint(client):
    response = client.get("/api/configs/detail?config_path=configs/agent_config.yaml")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "acceptable_data_types" in data
    assert "image/png" in data["acceptable_data_types"]
    assert data["max_image_width"] == 1024  # noqa: PLR2004
    assert data["max_image_height"] == 1024  # noqa: PLR2004
    assert data["min_image_width"] == 128  # noqa: PLR2004
    assert data["min_image_height"] == 128  # noqa: PLR2004


def test_get_config_detail_invalid_path(client):
    response = client.get("/api/configs/detail?config_path=configs/nonexistent.yaml")
    assert response.status_code == HTTP_400_BAD_REQUEST


def test_chat_endpoint_valid_image(client):
    img_bytes = create_dummy_image(200, 200, "PNG")
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "session_id": "test-img-session-1",
        "config_path": "configs/agent_config.yaml",
        "query": "What is in this image?",
        "images": [{"data": img_b64, "mime_type": "image/png"}],
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["status"] == "processing"

    # Stop and clean up
    client.post("/api/agent/stop/test-img-session-1")
    session_file = SESSIONS_DIR / "test-img-session-1.json"
    if session_file.exists():
        session_file.unlink()


def test_chat_endpoint_invalid_image_resolution(client):
    img_bytes = create_dummy_image(50, 50, "PNG")  # below 128x128
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")

    payload = {
        "session_id": "test-img-session-2",
        "config_path": "configs/agent_config.yaml",
        "query": "What is in this image?",
        "images": [{"data": img_b64, "mime_type": "image/png"}],
    }
    response = client.post("/api/agent/chat", json=payload)
    assert response.status_code == HTTP_400_BAD_REQUEST
    assert "below the minimum allowed limit" in response.json()["detail"]
