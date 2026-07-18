import base64
import io
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image, ImageSequence
from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.agents.base import ImagePart
from src.agents.config import ImageConstraints
from src.api.main import (
    SESSIONS_DIR,
    RequestImagePart,
    app,
    load_session_history,
    process_and_validate_image,
    run_agent_in_background,
)

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


def create_dummy_animated_gif(width: int, height: int, num_frames: int = 3) -> bytes:
    """Helper to generate a dummy animated GIF in memory."""
    frames = []
    for i in range(num_frames):
        color = (i * 80, 0, 255 - i * 80)
        img = Image.new("RGB", (width, height), color=color)
        frames.append(img)
    buf = io.BytesIO()
    frames[0].save(
        buf,
        save_all=True,
        append_images=frames[1:],
        format="GIF",
        loop=0,
        duration=100,
    )
    return buf.getvalue()


def test_process_and_validate_image_valid():
    img_bytes = create_dummy_image(512, 512, "PNG")
    constraints = ImageConstraints(
        acceptable_data_types=["image/png", "image/jpeg"],
        min_image_width=128,
        min_image_height=128,
        max_image_width=1024,
        max_image_height=1024,
    )
    processed_bytes, resolved_mime, was_resized = process_and_validate_image(
        image_bytes=img_bytes,
        mime_type="image/png",
        constraints=constraints,
    )
    assert resolved_mime == "image/png"
    assert not was_resized
    img = Image.open(io.BytesIO(processed_bytes))
    assert img.size == (512, 512)


def test_process_and_validate_image_below_lower_limit():
    img_bytes = create_dummy_image(100, 200, "PNG")
    constraints = ImageConstraints(
        acceptable_data_types=["image/png"],
        min_image_width=128,
        min_image_height=128,
        max_image_width=1024,
        max_image_height=1024,
    )
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_image(
            image_bytes=img_bytes,
            mime_type="image/png",
            constraints=constraints,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST
    assert "below the minimum allowed limit" in exc_info.value.detail


def test_process_and_validate_image_unacceptable_type():
    img_bytes = create_dummy_image(500, 500, "GIF")
    constraints = ImageConstraints(
        acceptable_data_types=["image/png", "image/jpeg"],
        min_image_width=128,
        min_image_height=128,
        max_image_width=1024,
        max_image_height=1024,
    )
    with pytest.raises(HTTPException) as exc_info:
        process_and_validate_image(
            image_bytes=img_bytes,
            mime_type="image/gif",
            constraints=constraints,
        )
    assert exc_info.value.status_code == HTTP_400_BAD_REQUEST
    assert "Unsupported image format" in exc_info.value.detail


def test_process_and_validate_image_resizing_aspect_ratio():
    img_bytes = create_dummy_image(2000, 1000, "JPEG")
    constraints = ImageConstraints(
        acceptable_data_types=["image/jpeg"],
        min_image_width=128,
        min_image_height=128,
        max_image_width=1000,
        max_image_height=1000,
    )
    processed_bytes, resolved_mime, was_resized = process_and_validate_image(
        image_bytes=img_bytes,
        mime_type="image/jpeg",
        constraints=constraints,
    )
    assert resolved_mime == "image/jpeg"
    assert was_resized
    img = Image.open(io.BytesIO(processed_bytes))
    assert img.size == (1000, 500)


def test_process_and_validate_image_animated_gif_resizing():
    img_bytes = create_dummy_animated_gif(2000, 1000, num_frames=3)
    constraints = ImageConstraints(
        acceptable_data_types=["image/gif"],
        min_image_width=128,
        min_image_height=128,
        max_image_width=1000,
        max_image_height=1000,
    )
    processed_bytes, resolved_mime, was_resized = process_and_validate_image(
        image_bytes=img_bytes,
        mime_type="image/gif",
        constraints=constraints,
    )
    assert resolved_mime == "image/gif"
    assert was_resized
    img = Image.open(io.BytesIO(processed_bytes))
    assert img.size == (1000, 500)
    # Check that it's still animated and contains all 3 frames
    frames = [f.copy() for f in ImageSequence.Iterator(img)]
    assert len(frames) == 3  # noqa: PLR2004
    for f in frames:
        assert f.size == (1000, 500)


def test_image_part_pydantic_validation(tmp_path):
    # Test valid Base64 decoding
    img_bytes = create_dummy_image(128, 128, "PNG")
    img_b64 = base64.b64encode(img_bytes).decode("utf-8")
    part = RequestImagePart(data=img_b64.encode("utf-8"), mime_type="image/png")
    assert part.data == img_bytes

    # Test valid FilePath validation
    file_path = Path(tmp_path / "test.png")
    file_path.write_bytes(img_bytes)
    part_file = ImagePart(path=file_path, mime_type="image/png")
    assert part_file.path == file_path

    # Test rejection when path doesn't exist
    with pytest.raises(ValueError):
        ImagePart(path=Path("nonexistent.png"), mime_type="image/png")

    # Test rejection when both are empty
    with pytest.raises(ValueError):
        ImagePart(mime_type="image/png")


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


@pytest.mark.asyncio
async def test_run_agent_in_background_serializes_images(tmp_path, monkeypatch):
    # 1. Create a dummy image
    img_bytes = create_dummy_image(200, 200, "PNG")
    img_part = ImagePart.from_bytes(data=img_bytes, mime_type="image/png")

    # 2. Mock SESSIONS_DIR in main.py to point to tmp_path
    monkeypatch.setattr("src.api.main.SESSIONS_DIR", tmp_path)

    # 3. Mock PydanticAIAgentGenerator.create_agent to return a mock agent
    mock_agent = MagicMock()
    mock_agent.prompt_manager = None
    mock_agent.default_user_prompt_source = None

    async def mock_call_stream(*args, **kwargs):
        yield "token1 "
        yield "token2"

    mock_agent.call_stream = mock_call_stream

    monkeypatch.setattr(
        "src.api.main.PydanticAIAgentGenerator.create_agent", lambda *args, **kwargs: mock_agent
    )

    # 4. Run the background agent task
    session_id = "test-session-123"
    await run_agent_in_background(
        session_id=session_id,
        config="configs/agent_config.yaml",
        query="Explain this image",
        images=[img_part],
    )

    # 5. Verify that the session history was loaded and saved with the images serialized
    history = load_session_history(session_id)
    assert len(history) == 2  # noqa: PLR2004
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Explain this image"
    assert "images" in history[0]
    assert len(history[0]["images"]) == 1
    assert history[0]["images"][0]["mime_type"] == "image/png"
    assert history[0]["images"][0]["data"].startswith("data:image/png;base64,")

    # 6. Verify assistant response
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "token1 token2"
