"""FastAPI dedicated document ingestion microservice.

Provides REST endpoints for document uploads, directory delta synchronization,
vector collection management, and background job status tracking.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.ingestion.contracts import (
    ChunkingStrategy,
    CreateCollectionResponse,
    DeltaAction,
    DistanceMetric,
    IngestFileResponse,
    IngestJobListResponse,
    IngestJobResponse,
    IngestSyncResponse,
    JobAction,
    JobStatus,
    PdfExtractionTier,
)
from src.ingestion.delta import SQLiteDeltaEngine
from src.ingestion.queue import SQLiteJobQueue
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Environment Configuration
STATE_DB_PATH = os.getenv("STATE_DB_PATH", "data/ingestion_state.db")
SOURCE_DOCS_DIR = os.getenv("SOURCE_DOCS_DIR", "data/source_docs")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))

app = FastAPI(
    title="Document Ingestion Microservice",
    description="Dedicated microservice for document parsing, hierarchical chunking, and delta synchronization.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Core State Engines
job_queue = SQLiteJobQueue(db_path=STATE_DB_PATH)
delta_engine = SQLiteDeltaEngine(db_path=STATE_DB_PATH)
qdrant_client = AsyncQdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)


# ============================================================================
# Request Models
# ============================================================================


class SyncDirectoryRequest(BaseModel):
    source_directory: str = Field(default=SOURCE_DOCS_DIR)
    collection_name: str = Field(default="default_collection")
    file_types: list[str] = Field(default_factory=lambda: [".pdf", ".txt", ".md", ".html"])
    prune_orphans: bool = Field(default=True)


class CreateCollectionBody(BaseModel):
    collection_name: str
    dimensions: int = 768
    distance: DistanceMetric = DistanceMetric.COSINE
    enable_quantization: bool = True


# ============================================================================
# REST Endpoints
# ============================================================================


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def healthcheck() -> dict[str, Any]:
    """Microservice liveness probe."""
    return {
        "status": "healthy",
        "service": "ingestion-service",
        "version": "1.0.0",
        "database": STATE_DB_PATH,
    }


@app.post("/ingest/file", response_model=IngestFileResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_file(
    file: UploadFile = File(...),
    collection_name: str = Form("default_collection"),
    chunk_size: int = Form(350),
    chunk_overlap: int = Form(50),
    chunking_strategy: ChunkingStrategy = Form(ChunkingStrategy.HIERARCHICAL),
    pdf_tier: PdfExtractionTier = Form(PdfExtractionTier.TIER1_NATIVE),
) -> IngestFileResponse:
    """Accepts document file upload and enqueues it for background ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in upload")

    os.makedirs(SOURCE_DOCS_DIR, exist_ok=True)
    target_path = os.path.join(SOURCE_DOCS_DIR, file.filename)

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to persist uploaded file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}") from e

    job_id = job_queue.enqueue(
        filepath=target_path,
        collection_name=collection_name,
        action=JobAction.NEW,
    )

    logger.info(f"Queued file ingestion job #{job_id} for {file.filename} -> {collection_name}")
    return IngestFileResponse(
        job_id=job_id,
        collection_name=collection_name,
        filename=file.filename,
        status="QUEUED",
        message="Document uploaded and queued for processing.",
    )


@app.post("/ingest/sync", response_model=IngestSyncResponse)
async def ingest_sync(payload: SyncDirectoryRequest) -> IngestSyncResponse:
    """Triggers directory delta synchronization across documents."""
    result = delta_engine.compute_deltas(
        source_directory=payload.source_directory,
        collection_name=payload.collection_name,
        file_types=payload.file_types,
    )

    new_count = 0
    mod_count = 0
    del_count = 0
    unchanged_count = 0

    for delta in result.deltas:
        if delta.action == DeltaAction.ADD:
            job_queue.enqueue(delta.filepath, payload.collection_name, JobAction.NEW)
            new_count += 1
        elif delta.action == DeltaAction.UPDATE:
            job_queue.enqueue(delta.filepath, payload.collection_name, JobAction.MODIFIED)
            mod_count += 1
        elif delta.action == DeltaAction.DELETE:
            job_queue.enqueue(delta.filepath, payload.collection_name, JobAction.DELETED)
            del_count += 1
        else:
            unchanged_count += 1

    total_enqueued = new_count + mod_count + del_count
    logger.info(
        f"Delta sync complete for {payload.source_directory}: {total_enqueued} jobs enqueued "
        f"({new_count} new, {mod_count} modified, {del_count} deleted, {unchanged_count} unchanged)"
    )

    return IngestSyncResponse(
        collection_name=payload.collection_name,
        source_directory=payload.source_directory,
        files_scanned=result.scanned_count,
        new_jobs_queued=new_count,
        modified_jobs_queued=mod_count,
        deleted_jobs_queued=del_count,
        unchanged_files=unchanged_count,
        total_jobs_enqueued=total_enqueued,
    )


@app.post("/collections", response_model=CreateCollectionResponse)
async def create_collection(payload: CreateCollectionBody) -> CreateCollectionResponse:
    """Provisions a Qdrant collection directly using AsyncQdrantClient."""
    dist_map = {
        DistanceMetric.COSINE: qmodels.Distance.COSINE,
        DistanceMetric.EUCLID: qmodels.Distance.EUCLID,
        DistanceMetric.DOT: qmodels.Distance.DOT,
    }

    q_distance = dist_map.get(payload.distance, qmodels.Distance.COSINE)
    try:
        collections = await qdrant_client.get_collections()
        existing = [c.name for c in collections.collections]

        if payload.collection_name in existing:
            return CreateCollectionResponse(
                collection_name=payload.collection_name,
                dimensions=payload.dimensions,
                distance=payload.distance.value,
                status="EXISTS",
                message=f"Collection '{payload.collection_name}' already exists.",
            )

        quantization_config = (
            qmodels.ScalarQuantization(
                scalar=qmodels.ScalarQuantizationConfig(
                    type=qmodels.ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True,
                )
            )
            if payload.enable_quantization
            else None
        )

        await qdrant_client.create_collection(
            collection_name=payload.collection_name,
            vectors_config=qmodels.VectorParams(
                size=payload.dimensions,
                distance=q_distance,
            ),
            quantization_config=quantization_config,
        )

        return CreateCollectionResponse(
            collection_name=payload.collection_name,
            dimensions=payload.dimensions,
            distance=payload.distance.value,
            status="CREATED",
            message=f"Collection '{payload.collection_name}' created successfully.",
        )
    except Exception as e:
        logger.error(f"Failed to create collection {payload.collection_name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Qdrant collection creation failed: {e}"
        ) from e


@app.get("/jobs/{job_id}", response_model=IngestJobResponse)
async def get_job_status(job_id: int) -> IngestJobResponse:
    """Retrieves operational progress and status of an ingestion job."""
    job = job_queue.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    return job


@app.get("/jobs", response_model=IngestJobListResponse)
async def list_jobs(
    collection_name: str | None = None,
    status: JobStatus | None = None,
    limit: int = 50,
) -> IngestJobListResponse:
    """Lists ingestion jobs matching optional criteria."""
    jobs = job_queue.list_jobs(collection_name=collection_name, status=status, limit=limit)
    return IngestJobListResponse(total_jobs=len(jobs), jobs=jobs)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: int) -> dict[str, Any]:
    """Aborts a pending or running ingestion job."""
    success = job_queue.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to cancel job #{job_id} (already completed or not found)",
        )
    return {"job_id": job_id, "status": "CANCELLED", "message": "Job cancelled successfully."}
