import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.api.main import ingestion_queue, ingestion_worker


@pytest.mark.asyncio
async def test_inmemory_queue_processing():
    task_data = {
        "filepath": "dummy.txt",
        "file_bytes": b"hello test content",
        "mime_type": "text/plain",
        "config": "dummy_config",
        "vectordb": "dummy_db",
        "embed_client": "dummy_client",
    }

    # 1. Put task in the queue
    await ingestion_queue.put(task_data)

    # 2. Mock ingest_document in the background
    with patch("src.utils.ingestion_helper.ingest_document", new_callable=AsyncMock) as mock_ingest:
        # Start ingestion_worker task
        worker_task = asyncio.create_task(ingestion_worker())

        # Give worker time to process the queue
        await asyncio.sleep(0.1)

        # Verify it was called
        mock_ingest.assert_called_once_with(
            filepath="dummy.txt",
            file_bytes=b"hello test content",
            mime_type="text/plain",
            config="dummy_config",
            vectordb="dummy_db",
            embed_client="dummy_client",
        )

        # Cancel worker
        worker_task.cancel()
        try:
            await worker_task
        except asyncio.CancelledError:
            pass
