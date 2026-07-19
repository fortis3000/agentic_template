from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils.chunkers import fixed_chunker, markdown_chunker, semantic_chunker


def test_fixed_chunker():
    text = "Hello world. This is a sentence. And another one."
    chunks = fixed_chunker(text, chunk_size=20, chunk_overlap=5)
    assert len(chunks) > 1


def test_markdown_chunker():
    text = "# Header 1\nContent 1\n## Header 2\nContent 2"
    chunks = markdown_chunker(text, max_chunk_size=50, chunk_overlap=5)
    assert len(chunks) == 2  # noqa: PLR2004
    assert chunks[0] == "# Header 1\nContent 1"
    assert chunks[1] == "## Header 2\nContent 2"


@pytest.mark.asyncio
async def test_semantic_chunker():
    mock_client = MagicMock()
    mock_batch_res = MagicMock()
    mock_batch_res.embeddings = [
        [1.0, 0.0],
        [1.0, 0.0],
        [0.0, 1.0],
    ]
    mock_client.embed_batch = AsyncMock(return_value=mock_batch_res)

    text = "First sentence. Second sentence. Third sentence."
    chunks = await semantic_chunker(
        text,
        embedding_client=mock_client,
        semantic_threshold=0.5,
        max_chunk_size=500,
        chunk_overlap=50,
    )
    assert len(chunks) == 2  # noqa: PLR2004
    assert chunks[0] == "First sentence. Second sentence."
    assert chunks[1] == "Third sentence."
