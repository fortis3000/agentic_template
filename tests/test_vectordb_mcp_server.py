import base64
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

from src.agents.embeddings import BaseEmbeddingClient, EmbeddingResponse
from src.tools.local.vectordb_base import BaseVectorDB
from src.tools.local.vectordb_mcp import VectorDBMcpTool
from src.tools.mcp.servers.vectordb import (
    _extract_image_bytes_and_mime,
    create_vectordb_mcp_server,
)

EXPECTED_HTTP_OK = 200
EXPECTED_HTTP_UNAVAILABLE = 503
EXPECTED_SCORE = 0.95
DEFAULT_TEST_LIMIT = 3
MOCK_DIMENSIONS = 4


class MockEmbeddingClient(BaseEmbeddingClient):
    """Mock embedding client returning deterministic vectors."""

    def __init__(self, dimensions: int = 4):
        self.dimensions = dimensions

    async def embed_text(self, text: str) -> EmbeddingResponse:
        return EmbeddingResponse(
            embedding=[0.1] * self.dimensions,
            dimensions=self.dimensions,
            model_name="mock-model",
        )

    async def embed_image(
        self, image_bytes: bytes, mime_type: str = "image/png"
    ) -> EmbeddingResponse:
        return EmbeddingResponse(
            embedding=[0.9] * self.dimensions,
            dimensions=self.dimensions,
            model_name="mock-model",
        )

    async def embed_batch(self, texts: list[str]) -> Any:
        raise NotImplementedError


@pytest.fixture
def mock_embed_client():
    return MockEmbeddingClient(dimensions=4)


@pytest.fixture
def mock_db():
    db = MagicMock(spec=BaseVectorDB)
    db.collection_exists = AsyncMock(return_value=True)
    db.health_check = AsyncMock(return_value={"status": "connected", "collections": ["test_coll"]})
    db.create_collection = AsyncMock()
    db.insert = AsyncMock()
    db.search = AsyncMock(
        return_value=[
            {
                "id": "point-1",
                "score": 0.95,
                "payload": {"text": "Hello world", "filepath": "doc.txt"},
            }
        ]
    )
    return db


@pytest.mark.asyncio
async def test_extract_image_bytes_and_mime_data_url():
    """Test extracting image bytes from a data URL."""
    sample_bytes = b"fake-image-bytes-png"
    b64_str = base64.b64encode(sample_bytes).decode("utf-8")
    data_url = f"data:image/png;base64,{b64_str}"

    extracted_bytes, mime = await _extract_image_bytes_and_mime(data_url)
    assert extracted_bytes == sample_bytes
    assert mime == "image/png"


@pytest.mark.asyncio
async def test_extract_image_bytes_and_mime_local_file(tmp_path, monkeypatch):
    """Test extracting image bytes from an allowed local file path."""
    monkeypatch.setenv("ALLOWED_IMAGE_DIR", str(tmp_path))
    img_file = tmp_path / "test.jpg"
    img_file.write_bytes(b"jpeg-content")

    extracted_bytes, mime = await _extract_image_bytes_and_mime(str(img_file))
    assert extracted_bytes == b"jpeg-content"
    assert mime == "image/jpeg"


@pytest.mark.asyncio
async def test_extract_image_bytes_path_traversal_blocked(tmp_path, monkeypatch):
    """Test that arbitrary file path outside ALLOWED_IMAGE_DIR is strictly blocked."""
    allowed_dir = tmp_path / "allowed"
    allowed_dir.mkdir()
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    secret_file = secret_dir / "secret.env"
    secret_file.write_text("SECRET=123")

    monkeypatch.setenv("ALLOWED_IMAGE_DIR", str(allowed_dir))

    with pytest.raises(ValueError, match="outside allowed directory"):
        await _extract_image_bytes_and_mime(str(secret_file))


@pytest.mark.asyncio
async def test_extract_image_bytes_invalid():
    """Test that invalid image string raises ValueError."""
    with pytest.raises(ValueError, match="is neither an accessible file in"):
        await _extract_image_bytes_and_mime("non_existent_file_and_not_base64")


def test_healthz_endpoint_healthy(mock_db, mock_embed_client):
    """Test that /healthz responds with HTTP 200 when Qdrant is connected."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )
    client = TestClient(mcp_server.sse_app())
    response = client.get("/healthz")
    assert response.status_code == EXPECTED_HTTP_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "vectordb-mcp"
    assert data["qdrant"]["status"] == "connected"


def test_healthz_endpoint_unhealthy(mock_db, mock_embed_client):
    """Test that /healthz responds with HTTP 503 when Qdrant connection fails."""
    mock_db.health_check = AsyncMock(
        return_value={"status": "error", "error": "Connection refused"}
    )
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )
    client = TestClient(mcp_server.sse_app())
    response = client.get("/healthz")
    assert response.status_code == EXPECTED_HTTP_UNAVAILABLE
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "error" in data


def _get_tool_text(result: Any) -> str:
    """Extract string content from FastMCP call_tool return value."""
    content = result[0] if isinstance(result, tuple) else result
    if isinstance(content, list) and content:
        return getattr(content[0], "text", str(content[0]))
    return getattr(content, "text", str(content))


@pytest.mark.asyncio
async def test_vectordb_search_dense(mock_db, mock_embed_client):
    """Test dense text vector search tool invocation."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    result = await mcp_server.call_tool(
        "vectordb_search",
        {"query_text": "How do agents work?", "search_type": "dense", "limit": DEFAULT_TEST_LIMIT},
    )

    parsed = json.loads(_get_tool_text(result))
    assert len(parsed) == 1
    assert parsed[0]["id"] == "point-1"
    assert parsed[0]["score"] == EXPECTED_SCORE

    mock_db.search.assert_awaited_once()
    call_kwargs = mock_db.search.await_args.kwargs
    assert call_kwargs["collection_name"] == "test_coll"
    assert call_kwargs["limit"] == DEFAULT_TEST_LIMIT
    assert call_kwargs["search_type"] == "dense"
    assert call_kwargs["query_vector"] == [0.1, 0.1, 0.1, 0.1]


@pytest.mark.asyncio
async def test_vectordb_search_image(mock_db, mock_embed_client):
    """Test image search with base64 data URL."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    b64_img = base64.b64encode(b"dummy-image").decode("utf-8")
    data_url = f"data:image/png;base64,{b64_img}"

    result = await mcp_server.call_tool(
        "vectordb_search",
        {"query_text": data_url, "search_type": "image"},
    )

    parsed = json.loads(_get_tool_text(result))
    assert len(parsed) == 1

    call_kwargs = mock_db.search.await_args.kwargs
    assert call_kwargs["search_type"] == "image"
    assert call_kwargs["query_vector"] == [0.9, 0.9, 0.9, 0.9]


@pytest.mark.asyncio
async def test_vectordb_search_invalid_type(mock_db, mock_embed_client):
    """Test that invalid search_type raises error in FastMCP."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    with pytest.raises(Exception, match="Invalid search_type 'invalid'"):
        await mcp_server.call_tool(
            "vectordb_search",
            {"query_text": "sample", "search_type": "invalid"},
        )


@pytest.mark.asyncio
async def test_vectordb_store_deterministic_id(mock_db, mock_embed_client):
    """Test storing text without explicit ID generates a deterministic UUIDv5."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    text_content = "Antigravity agents pattern"
    expected_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"test_coll:{text_content}"))

    result = await mcp_server.call_tool(
        "vectordb_store",
        {"text": text_content, "metadata": {"author": "engineer"}},
    )

    parsed = json.loads(_get_tool_text(result))
    assert parsed["status"] == "success"
    assert parsed["id"] == expected_id
    assert parsed["collection"] == "test_coll"
    assert parsed["dimensions"] == MOCK_DIMENSIONS

    mock_db.insert.assert_awaited_once()
    insert_kwargs = mock_db.insert.await_args.kwargs
    assert insert_kwargs["collection_name"] == "test_coll"
    assert insert_kwargs["ids"] == [expected_id]
    assert insert_kwargs["payloads"][0]["text"] == text_content
    assert insert_kwargs["payloads"][0]["author"] == "engineer"
    # Verify sparse vector contract
    assert "sparse_indices" in insert_kwargs["payloads"][0]
    assert "sparse_values" in insert_kwargs["payloads"][0]


@pytest.mark.asyncio
async def test_vectordb_store_custom_id(mock_db, mock_embed_client):
    """Test storing text with custom ID passes explicit ID."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    result = await mcp_server.call_tool(
        "vectordb_store",
        {"text": "Custom ID text", "id": "custom-id-999"},
    )

    parsed = json.loads(_get_tool_text(result))
    assert parsed["id"] == "custom-id-999"

    insert_kwargs = mock_db.insert.await_args.kwargs
    assert insert_kwargs["ids"] == ["custom-id-999"]


@pytest.mark.asyncio
async def test_vectordb_store_empty_text(mock_db, mock_embed_client):
    """Test storing empty text raises error."""
    mcp_server = create_vectordb_mcp_server(
        db=mock_db,
        embed_client=mock_embed_client,
        default_collection="test_coll",
    )

    with pytest.raises(Exception, match="must not be empty"):
        await mcp_server.call_tool(
            "vectordb_store",
            {"text": "   "},
        )


@pytest.mark.asyncio
async def test_vectordb_mcp_tool_callable():
    """Test VectorDBMcpTool callable creation and healthcheck."""
    tool = VectorDBMcpTool(
        url="http://localhost:8001/sse",
        tool_name="vectordb_search",
        collection_name="test_coll",
    )
    fn = tool.get_callable()
    assert callable(fn)
    assert getattr(fn, "__name__", "") == "search_vectordb_mcp"
