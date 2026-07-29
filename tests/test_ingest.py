import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import EmbeddingModelConfigSchema
from src.ingestion.chunkers import fixed_chunker as chunk_text
from src.ingestion.pipeline import IngestionConfigSchema, IngestionPipeline


def test_chunk_text_boundaries():
    """Verify that chunk_text splits content correctly near boundaries and respects separators."""
    text = "Paragraph 1 is here.\n\nParagraph 2 is here. Paragraph 2 sentence 2."

    # Large chunk size keeps it together
    chunks = chunk_text(text, chunk_size=200, chunk_overlap=10)
    assert len(chunks) == 1
    assert chunks[0] == text

    # Smaller chunk size breaks on double newline
    chunks2 = chunk_text(text, chunk_size=30, chunk_overlap=10)
    assert len(chunks2) >= 2  # noqa: PLR2004
    assert chunks2[0] == "Paragraph 1 is here."
    assert "Paragraph 2 is here" in chunks2[1]


@pytest.mark.asyncio
async def test_ingestion_pipeline_delta_updates(tmp_path):
    """Test full ingestion pipeline scanning, delta queuing, updates, and deletes."""
    # 1. Prepare temporary directory and test files
    source_dir = tmp_path / "source"
    source_dir.mkdir()

    file_txt = source_dir / "doc1.txt"
    file_txt.write_text("Hello world text content.")

    file_md = source_dir / "doc2.md"
    file_md.write_text("Markdown header\n\nContent.")

    state_db = tmp_path / "state.db"

    # 2. Mock embedding config and vectordb configs
    config = IngestionConfigSchema(
        source_directory=str(source_dir),
        collection_name="test_collection",
        chunk_size=100,
        chunk_overlap=10,
        file_types=[".txt", ".md"],
        embedding_model=EmbeddingModelConfigSchema(
            provider="google",
            model="text-embedding-004",
            dimensions=4,
        ),
        vectordb={
            "type": "qdrant",
            "location": ":memory:",
        },
        state_db_path=str(state_db),
    )

    # 3. Create pipeline
    pipeline = IngestionPipeline(config)

    # Mock DB insert and delete calls
    mock_db = AsyncMock()
    mock_db.create_collection = AsyncMock()
    mock_db.insert = AsyncMock()
    mock_db.delete = AsyncMock()

    mock_embed = AsyncMock()
    mock_embed.embed_batch = AsyncMock(
        return_value=MagicMock(embeddings=[[0.1, 0.2, 0.3, 0.4], [0.5, 0.6, 0.7, 0.8]])
    )

    with (
        patch("src.ingestion.pipeline.VectorDBFactory.create", return_value=mock_db),
        patch("src.ingestion.pipeline.EmbeddingModelFactory.create", return_value=mock_embed),
    ):
        # Scan for initial files (should find 2 NEW files)
        jobs_count = pipeline.check_deltas_and_queue_jobs()
        assert jobs_count == 2  # noqa: PLR2004

        # Verify job list in SQLite
        cursor = pipeline.conn.cursor()
        cursor.execute("SELECT action FROM ingest_jobs ORDER BY id")
        actions = [r["action"] for r in cursor.fetchall()]
        assert actions == ["NEW", "NEW"]

        # Run process queue
        await pipeline.process_queue()
        assert mock_db.insert.call_count == 2  # noqa: PLR2004
        assert mock_db.delete.call_count == 0

        # Verify state is updated in files table
        cursor.execute("SELECT filepath FROM files")
        saved_files = [r["filepath"] for r in cursor.fetchall()]
        assert len(saved_files) == 2  # noqa: PLR2004
        assert str(file_txt) in saved_files
        assert str(file_md) in saved_files

        # 4. Modify one file (doc1.txt) and delete the other (doc2.md)
        mock_db.insert.reset_mock()
        mock_db.delete.reset_mock()

        # Modify txt file
        file_txt.write_text("Hello world text content. MODIFIED.")
        os.utime(file_txt, (os.path.getatime(file_txt) + 10, os.path.getmtime(file_txt) + 10))

        # Delete md file
        os.remove(file_md)

        # Scan again (should detect 1 MODIFIED, 1 DELETED)
        jobs_count = pipeline.check_deltas_and_queue_jobs()
        assert jobs_count == 2  # noqa: PLR2004

        cursor.execute("SELECT action FROM ingest_jobs ORDER BY id")
        actions2 = [r["action"] for r in cursor.fetchall()]
        assert set(actions2) == {"MODIFIED", "DELETED"}

        # Run process queue to apply updates/deletions
        await pipeline.process_queue()

        # 1 delete for DELETED file, 1 delete for MODIFIED file before re-insert
        assert mock_db.delete.call_count == 2  # noqa: PLR2004
        assert mock_db.insert.call_count == 1  # 1 re-insert for modified file

        # Check files table: only doc1.txt should remain
        cursor.execute("SELECT filepath FROM files")
        final_files = [r["filepath"] for r in cursor.fetchall()]
        assert len(final_files) == 1
        assert str(file_txt) in final_files

    pipeline.close()
