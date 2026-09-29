"""Integration and isolation tests for the Ingestion Microservice FastAPI application."""

from __future__ import annotations

import asyncio
import io
import os
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from src.ingestion.contracts import JobAction, JobStatus
from src.ingestion.delta import SQLiteDeltaEngine
from src.ingestion.queue import SQLiteJobQueue
from src.ingestion.service import (
    app,
    get_delta_engine,
    get_job_queue,
    get_qdrant_client,
)
from src.ingestion.worker import IngestionWorker

HTTP_200_OK = 200
HTTP_202_ACCEPTED = 202
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404
HTTP_409_CONFLICT = 409
HTTP_503_SERVICE_UNAVAILABLE = 503
EXPECTED_CHUNK_SIZE = 350


@pytest.fixture
def mock_qdrant():
    client = AsyncMock()
    mock_cols = AsyncMock()
    mock_cols.collections = []
    client.get_collections = AsyncMock(return_value=mock_cols)
    client.get_collection = AsyncMock()
    client.create_collection = AsyncMock()
    client.upsert = AsyncMock()
    client.delete = AsyncMock()
    client.close = AsyncMock()
    return client


@pytest.fixture
def isolated_env(tmp_path, monkeypatch, mock_qdrant):
    """Sets isolated temporary state DB and source docs directory with dependency overrides."""
    db_path = str(tmp_path / "test_service_state.db")
    docs_dir = str(tmp_path / "source_docs")
    os.makedirs(docs_dir, exist_ok=True)

    monkeypatch.setenv("STATE_DB_PATH", db_path)
    monkeypatch.setenv("SOURCE_DOCS_DIR", docs_dir)

    queue = SQLiteJobQueue(db_path=db_path)
    delta = SQLiteDeltaEngine(db_path=db_path)

    app.dependency_overrides[get_job_queue] = lambda: queue
    app.dependency_overrides[get_delta_engine] = lambda: delta
    app.dependency_overrides[get_qdrant_client] = lambda: mock_qdrant

    yield {
        "db_path": db_path,
        "docs_dir": docs_dir,
        "queue": queue,
        "delta": delta,
        "qdrant": mock_qdrant,
    }

    app.dependency_overrides.clear()


@pytest.fixture
def client(isolated_env):
    with TestClient(app) as test_client:
        yield test_client


def test_healthz_endpoint(client):
    """Test healthcheck endpoint returns 200 and healthy status."""
    response = client.get("/healthz")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ingestion-service"
    assert data["database"] == "ok"
    assert data["vectordb"] == "ok"


def test_healthz_failure(client, isolated_env):
    """Test healthcheck returns 503 when Qdrant connectivity fails."""
    isolated_env["qdrant"].get_collections.side_effect = RuntimeError("Qdrant connection refused")
    response = client.get("/healthz")
    assert response.status_code == HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()["detail"]
    assert data["status"] == "degraded"
    assert "unhealthy" in data["vectordb"]


def test_ingest_file_endpoint(client, isolated_env):
    """Test file upload endpoint enqueues job with PENDING status and stores file safely."""
    file_bytes = b"# Sample Document\n\nThis is a test markdown document for ingestion."
    response = client.post(
        "/ingest/file",
        files={"file": ("sample.md", io.BytesIO(file_bytes), "text/markdown")},
        data={"collection_name": "test_collection", "chunk_size": "350"},
    )
    assert response.status_code == HTTP_202_ACCEPTED
    data = response.json()
    assert "job_id" in data
    assert data["collection_name"] == "test_collection"
    assert data["filename"] == "sample.md"
    assert data["status"] == JobStatus.PENDING.value

    job_id = data["job_id"]
    job_resp = client.get(f"/jobs/{job_id}")
    assert job_resp.status_code == HTTP_200_OK
    job_data = job_resp.json()
    assert job_data["id"] == job_id
    assert job_data["status"] == JobStatus.PENDING.value
    assert job_data["options"]["chunk_size"] == EXPECTED_CHUNK_SIZE


def test_ingest_file_path_traversal_protection(client):
    """Test that path traversal attempts in uploaded filenames are rejected or sanitized."""
    file_bytes = b"Malicious payload"
    # Traversals like ../../etc/passwd should be rejected or stripped of directory components
    response = client.post(
        "/ingest/file",
        files={"file": ("../../escaped.txt", io.BytesIO(file_bytes), "text/plain")},
        data={"collection_name": "test_collection"},
    )
    # The endpoint strips directory components with os.path.basename, sanitizing it to escaped.txt
    assert response.status_code == HTTP_202_ACCEPTED
    assert response.json()["filename"] == "escaped.txt"

    # Invalid empty or dot filename
    bad_resp = client.post(
        "/ingest/file",
        files={"file": ("..", io.BytesIO(file_bytes), "text/plain")},
        data={"collection_name": "test_collection"},
    )
    assert bad_resp.status_code == HTTP_400_BAD_REQUEST


def test_ingest_sync_endpoint(client, isolated_env):
    """Test directory delta sync endpoint computes deltas and enqueues jobs."""
    docs_dir = isolated_env["docs_dir"]
    doc1 = os.path.join(docs_dir, "doc1.txt")
    with open(doc1, "w") as f:
        f.write("Delta sync test content")

    payload = {
        "source_directory": docs_dir,
        "collection_name": "sync_collection",
        "file_types": [".txt"],
        "prune_orphans": True,
    }
    response = client.post("/ingest/sync", json=payload)
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["files_scanned"] == 1
    assert data["new_jobs_queued"] == 1
    assert data["total_jobs_enqueued"] == 1


def test_job_cancellation_endpoint(client, isolated_env):
    """Test cancelling an existing pending job and error handling."""
    queue = isolated_env["queue"]
    job_id = queue.enqueue("/tmp/doc.txt", "cancel_col", JobAction.NEW)

    # Cancel the pending job
    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == HTTP_200_OK
    assert cancel_resp.json()["status"] == JobStatus.CANCELLED.value

    # Check status changed
    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.json()["status"] == JobStatus.CANCELLED.value

    # Cancelling again should return 400 or 409
    cancel_again = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_again.status_code in (HTTP_400_BAD_REQUEST, HTTP_409_CONFLICT)

    # Cancelling non-existent job returns 404
    not_found = client.post("/jobs/99999/cancel")
    assert not_found.status_code == HTTP_404_NOT_FOUND


def test_list_jobs_endpoint(client, isolated_env):
    """Test listing jobs with collection filter."""
    queue = isolated_env["queue"]
    queue.enqueue("/tmp/d1.txt", "col_a", JobAction.NEW)
    queue.enqueue("/tmp/d2.txt", "col_b", JobAction.NEW)

    response = client.get("/jobs?collection_name=col_a&limit=10")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["total_jobs"] == 1
    assert data["jobs"][0]["collection_name"] == "col_a"


def test_create_collection_endpoint(client, isolated_env):
    """Test creating a vector collection with Qdrant client and checking existing response."""
    mock_qdrant = isolated_env["qdrant"]

    payload = {
        "collection_name": "new_kb_collection",
        "dimensions": 768,
        "distance": "Cosine",
        "enable_quantization": True,
    }
    response = client.post("/collections", json=payload)
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["collection_name"] == "new_kb_collection"
    assert data["status"] == "CREATED"
    mock_qdrant.create_collection.assert_awaited_once()

    # Second call when collection exists
    mock_col = AsyncMock()
    mock_col.name = "new_kb_collection"
    mock_qdrant.get_collections.return_value.collections = [mock_col]

    mock_info = AsyncMock()
    mock_info.config.params.vectors.size = 768
    mock_info.config.params.vectors.distance = "Cosine"
    mock_qdrant.get_collection.return_value = mock_info

    exists_resp = client.post("/collections", json=payload)
    assert exists_resp.status_code == HTTP_200_OK
    assert exists_resp.json()["status"] == "EXISTS"


@pytest.mark.asyncio
async def test_end_to_end_worker_execution(isolated_env):
    """Test end-to-end ingestion pipeline execution by IngestionWorker."""
    queue = isolated_env["queue"]
    delta = isolated_env["delta"]
    qdrant = isolated_env["qdrant"]
    docs_dir = isolated_env["docs_dir"]

    # Write document
    doc_path = os.path.join(docs_dir, "report.md")
    with open(doc_path, "w") as f:
        f.write(
            "# Engineering Report\n\nDetailed breakdown of architectural patterns.\n\n## Subsystem A\n\nComponent specifications."
        )

    # Enqueue job
    job_id = queue.enqueue(doc_path, "prod_collection", JobAction.NEW, {"chunk_size": 200})
    assert job_id > 0
    assert queue.get_job_dto(job_id).status == JobStatus.PENDING

    # Run worker
    worker = IngestionWorker(
        queue=queue,
        delta_engine=delta,
        qdrant_client=qdrant,
        worker_id="integration-worker",
    )
    await worker.start()

    # Wait for job to process
    for _ in range(20):
        await asyncio.sleep(0.1)
        job = queue.get_job_dto(job_id)
        if job and job.status == JobStatus.COMPLETED:
            break

    await worker.stop()

    # Verify execution outcome
    job = queue.get_job_dto(job_id)
    assert job is not None
    assert job.status == JobStatus.COMPLETED
    assert job.progress.chunks_indexed > 0
    assert qdrant.upsert.called

    # Verify delta engine state recorded
    synced_chunk_ids = delta.get_existing_chunk_ids(doc_path, "prod_collection")
    assert len(synced_chunk_ids) > 0
