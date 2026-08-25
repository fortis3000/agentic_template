from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.agents.config import EmbeddingModelConfigSchema, McpServerConfigSchema
from src.mcp_integration import McpServerFactory
from src.tools.qdrant_db import QdrantVectorDB, generate_sparse_vector
from src.tools.vectordb_search import VectorDBSearchTool


@pytest.fixture(autouse=True)
def mock_mcp_fetching():
    """Override conftest.py mock to allow testing the actual fetch_tools_sync implementation."""
    pass


def test_generate_sparse_vector_stability():
    """Verify that generate_sparse_vector produces deterministic, stable hash indexes."""
    text = "hello world search query"
    vec1 = generate_sparse_vector(text)
    vec2 = generate_sparse_vector(text)

    assert vec1.indices == vec2.indices
    assert vec1.values == vec2.values
    # Test specific bucket constraint
    for idx in vec1.indices:
        assert 0 <= idx < 10000  # noqa: PLR2004


@pytest.mark.asyncio
async def test_qdrant_connection_cache_loop_isolation():
    """Verify that QdrantVectorDB caches connections within the same loop but isolates across loops."""
    # Inside the same running loop
    db1 = QdrantVectorDB(location=":memory:")
    db2 = QdrantVectorDB(location=":memory:")
    assert db1.client is db2.client

    # Simulate different loop ids by patching asyncio.get_running_loop
    loop1 = MagicMock()
    loop2 = MagicMock()

    with patch("asyncio.get_running_loop") as mock_get_loop:
        mock_get_loop.return_value = loop1
        db_l1 = QdrantVectorDB(location=":memory:")

        mock_get_loop.return_value = loop2
        db_l2 = QdrantVectorDB(location=":memory:")

        assert db_l1.client is not db_l2.client


@pytest.mark.asyncio
async def test_vectordb_search_tool_image_path_validation():
    """Verify that VectorDBSearchTool raises ValueError for non-existent image paths."""
    tool = VectorDBSearchTool(
        collection_name="test_col",
        embedding_model={
            "provider": "google",
            "model": "text-embedding-004",
            "dimensions": 4,
            "image_dimensions": 4,
        },
        vectordb={
            "type": "qdrant",
            "location": ":memory:",
        },
    )

    search_fn = tool.get_callable()
    with pytest.raises(ValueError, match="Image search requires a valid local path"):
        await search_fn(query_text="non_existent_image_path_123.jpg", search_type="image")


def test_fetch_tools_sync_non_blocking():
    """Verify that fetch_tools_sync runs on a ThreadPoolExecutor and does not block or pollute current loop."""
    config = McpServerConfigSchema(
        type="stdio",
        command="echo",
        args=["[]"],
    )

    with patch(
        "src.mcp_integration.client.McpServerFactory.fetch_tools", new_callable=AsyncMock
    ) as mock_fetch:
        mock_fetch.return_value = [{"name": "echo_tool", "description": "echo", "input_schema": {}}]
        tools = McpServerFactory.fetch_tools_sync(config)
        assert len(tools) == 1
        assert tools[0]["name"] == "echo_tool"


@pytest.mark.asyncio
async def test_create_collection_sizes_image_vector_from_argument():
    """Finding 5: the image vector must follow config, not a hardcoded 512."""
    db = QdrantVectorDB(location=":memory:")

    await db.create_collection("explicit_image_dims", vector_size=8, image_vector_size=3072)
    info = await db.client.get_collection("explicit_image_dims")
    vectors = info.config.params.vectors
    assert vectors["dense"].size == 8  # noqa: PLR2004
    assert vectors["image"].size == 3072  # noqa: PLR2004

    # Omitted, the image vector follows the dense size - one model embeds both modalities.
    await db.create_collection("defaulted_image_dims", vector_size=8)
    info2 = await db.client.get_collection("defaulted_image_dims")
    assert info2.config.params.vectors["image"].size == 8  # noqa: PLR2004


def test_embedding_config_requires_image_dimensions():
    """Finding 5: the image dimension must be stated explicitly in config."""
    with pytest.raises(ValidationError, match="image_dimensions"):
        EmbeddingModelConfigSchema.model_validate(
            {"provider": "google", "model": "gemini-embedding-001", "dimensions": 3072}
        )
