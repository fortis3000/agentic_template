"""Integration tests for the Ingestion Microservice FastAPI application."""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.ingestion.contracts import JobStatus
from src.ingestion.service import app

HTTP_200_OK = 200
HTTP_202_ACCEPTED = 202
HTTP_400_BAD_REQUEST = 400
HTTP_404_NOT_FOUND = 404


@pytest.fixture
def client():
    return TestClient(app)


def test_healthz_endpoint(client):
    """Test healthcheck endpoint returns 200 and healthy status."""
    response = client.get("/healthz")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ingestion-service"
    assert data["version"] == "1.0.0"


def test_ingest_file_endpoint(client):
    """Test file upload endpoint enqueues job and returns 202 Accepted."""
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
    assert data["status"] == "QUEUED"

    # Verify job can be retrieved via GET /jobs/{id}
    job_id = data["job_id"]
    job_resp = client.get(f"/jobs/{job_id}")
    assert job_resp.status_code == HTTP_200_OK
    job_data = job_resp.json()
    assert job_data["id"] == job_id
    assert job_data["status"] == JobStatus.PENDING.value


def test_ingest_sync_endpoint(client):
    """Test directory delta sync endpoint computes deltas and enqueues jobs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        doc1 = os.path.join(tmpdir, "doc1.txt")
        with open(doc1, "w") as f:
            f.write("Delta sync test content")

        payload = {
            "source_directory": tmpdir,
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


def test_job_cancellation_endpoint(client):
    """Test cancelling an existing pending job."""
    file_bytes = b"Document to cancel"
    response = client.post(
        "/ingest/file",
        files={"file": ("cancel_me.txt", io.BytesIO(file_bytes), "text/plain")},
        data={"collection_name": "cancel_collection"},
    )
    assert response.status_code == HTTP_202_ACCEPTED
    job_id = response.json()["job_id"]

    cancel_resp = client.post(f"/jobs/{job_id}/cancel")
    assert cancel_resp.status_code == HTTP_200_OK
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Check status changed
    status_resp = client.get(f"/jobs/{job_id}")
    assert status_resp.json()["status"] == "CANCELLED"


def test_list_jobs_endpoint(client):
    """Test listing jobs with collection filter."""
    response = client.get("/jobs?limit=10")
    assert response.status_code == HTTP_200_OK
    data = response.json()
    assert "total_jobs" in data
    assert "jobs" in data
    assert isinstance(data["jobs"], list)


@pytest.mark.asyncio
async def test_create_collection_endpoint(client):
    """Test creating a vector collection with Qdrant client."""
    with patch("src.ingestion.service.qdrant_client") as mock_qdrant:
        mock_collections = AsyncMock()
        mock_collections.collections = []
        mock_qdrant.get_collections = AsyncMock(return_value=mock_collections)
        mock_qdrant.create_collection = AsyncMock(return_value=True)

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
