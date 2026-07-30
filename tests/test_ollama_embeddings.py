from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import EmbeddingModelConfigSchema
from src.agents.embeddings import EmbeddingModelFactory, OllamaEmbeddingClient


@pytest.mark.asyncio
async def test_ollama_embedding_client():
    cfg = EmbeddingModelConfigSchema(
        provider="ollama",
        model="nomic-embed-text",
        dimensions=3,
        image_dimensions=3,
        supported_data_types=["text"],
    )
    client = EmbeddingModelFactory.create(cfg)
    assert isinstance(client, OllamaEmbeddingClient)

    # Mock httpx response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": [0.5, 0.6, 0.7]}

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        res = await client.embed_text("hello test")
        assert res.embedding == [0.5, 0.6, 0.7]
        assert res.dimensions == 3  # noqa: PLR2004

        # Test batch
        batch_res = await client.embed_batch(["hello", "world"])
        assert len(batch_res.embeddings) == 2  # noqa: PLR2004
        assert batch_res.embeddings[0] == [0.5, 0.6, 0.7]

    # Test that embed_image raises ValueError
    with pytest.raises(ValueError, match="do not support multimodal"):
        await client.embed_image(b"fakebytes", "image/png")

    # Test dimension mismatch raises ValueError
    cfg_bad_dims = EmbeddingModelConfigSchema(
        provider="ollama",
        model="nomic-embed-text",
        dimensions=5,  # Mismatches length 3 of returned mock
        image_dimensions=5,
        supported_data_types=["text"],
    )
    client_bad = EmbeddingModelFactory.create(cfg_bad_dims)
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        with pytest.raises(ValueError, match="does not match the configured dimensions"):
            await client_bad.embed_text("hello test")
