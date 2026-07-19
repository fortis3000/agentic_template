from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.agents.config import EmbeddingModelConfigSchema
from src.agents.embeddings import BatchEmbeddingResponse, EmbeddingModelFactory, EmbeddingResponse


def test_embedding_response_schema():
    """Verify that EmbeddingResponse enforces float validation and dimension constraints."""
    # Test valid response
    resp = EmbeddingResponse(embedding=[0.1, 0.2], dimensions=2, model_name="test")
    assert resp.embedding == [0.1, 0.2]

    # Test dimension mismatch raises ValueError
    with pytest.raises(ValueError, match="does not match expected dimensions"):
        EmbeddingResponse(embedding=[0.1, 0.2, 0.3], dimensions=2, model_name="test")

    # Test empty embedding list raises ValueError
    with pytest.raises(ValueError, match="cannot be empty"):
        EmbeddingResponse(embedding=[], dimensions=0, model_name="test")

    # Test non-numeric elements raise ValidationError
    with pytest.raises(ValidationError):
        EmbeddingResponse(embedding=cast(Any, ["a", "b"]), dimensions=2, model_name="test")


def test_batch_embedding_response_schema():
    """Verify that BatchEmbeddingResponse enforces batch structure."""
    resp = BatchEmbeddingResponse(
        embeddings=[[0.1, 0.2], [0.3, 0.4]], dimensions=2, model_name="test"
    )
    assert len(resp.embeddings) == 2  # noqa: PLR2004

    with pytest.raises(ValueError, match="does not match expected dimensions"):
        BatchEmbeddingResponse(
            embeddings=[[0.1, 0.2], [0.3, 0.4, 0.5]], dimensions=2, model_name="test"
        )


@pytest.mark.asyncio
async def test_google_embedding_client_compatibility():
    """Verify GoogleEmbeddingClient throws ValueError if image is passed to text-only model."""
    cfg = EmbeddingModelConfigSchema(
        provider="google",
        model="text-embedding-004",
        dimensions=768,
    )
    client = EmbeddingModelFactory.create(cfg)

    with pytest.raises(ValueError, match="does not support multimodal/image inputs"):
        await client.embed_image(b"fake_image_data", "image/png")


@pytest.mark.asyncio
async def test_openai_embedding_client_compatibility():
    """Verify OpenAIEmbeddingClient throws ValueError on image inputs."""
    cfg = EmbeddingModelConfigSchema(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=1536,
    )
    client = EmbeddingModelFactory.create(cfg)

    with pytest.raises(ValueError, match="does not support multimodal/image inputs"):
        await client.embed_image(b"fake_image_data", "image/png")


@pytest.mark.asyncio
async def test_google_embedding_client_generation():
    """Test standard text embedding generation using Google client mock."""
    cfg = EmbeddingModelConfigSchema(
        provider="google",
        model="text-embedding-004",
        dimensions=4,
    )
    client = EmbeddingModelFactory.create(cfg)

    mock_values = MagicMock()
    mock_values.values = [0.1, 0.2, 0.3, 0.4]
    mock_res = MagicMock()
    mock_res.embeddings = [mock_values]

    with patch.object(
        cast(Any, client).client.models, "embed_content", return_value=mock_res
    ) as mock_embed:
        res = await client.embed_text("hello world")
        assert res.embedding == [0.1, 0.2, 0.3, 0.4]
        assert res.dimensions == 4  # noqa: PLR2004
        mock_embed.assert_called_once_with(model="text-embedding-004", contents="hello world")
