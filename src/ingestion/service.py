"""FastAPI dedicated document ingestion microservice.

Provides REST endpoints for document uploads, directory delta synchronization,
vector collection management, and background job status tracking.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import tempfile
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile, status
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
    IngestJobDTO,
    IngestJobListResponse,
    IngestJobResponse,
    IngestSyncResponse,
    JobAction,
    JobStatus,
    PdfExtractionTier,
)
from src.ingestion.delta import SQLiteDeltaEngine
from src.ingestion.queue import SQLiteJobQueue
from src.ingestion.worker import IngestionWorker
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Environment Configuration
STATE_DB_PATH = os.getenv("STATE_DB_PATH", "data/service_ingestion_state.db")
SOURCE_DOCS_DIR = os.getenv("SOURCE_DOCS_DIR", "data/source_docs")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan hook initializing engines, crash recovery, and worker tasks."""
    db_path = os.getenv("STATE_DB_PATH", STATE_DB_PATH)
    docs_dir = os.getenv("SOURCE_DOCS_DIR", SOURCE_DOCS_DIR)
    q_host = os.getenv("QDRANT_HOST", QDRANT_HOST)
    q_port = int(os.getenv("QDRANT_PORT", str(QDRANT_PORT)))

    os.makedirs(docs_dir, exist_ok=True)
    queue = SQLiteJobQueue(db_path=db_path)
    delta = SQLiteDeltaEngine(db_path=db_path)
    qdrant = AsyncQdrantClient(host=q_host, port=q_port)

    # Startup recovery sweep for expired leases
    queue.recover_stale_leases(max_retries=3)

    worker = IngestionWorker(
        queue=queue,
        delta_engine=delta,
        qdrant_client=qdrant,
        concurrency=int(os.getenv("INGESTION_CONCURRENCY", "2")),
    )
    await worker.start()

    app.state.job_queue = queue
    app.state.delta_engine = delta
    app.state.qdrant_client = qdrant
    app.state.worker = worker

    yield

    # Shutdown
    await worker.stop()
    await qdrant.close()


app = FastAPI(
    title="Document Ingestion Microservice",
    description="Dedicated microservice for document parsing, hierarchical chunking, and delta synchronization.",
    version="1.0.0",
    lifespan=lifespan,
)

# Restrict CORS to trusted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# Dependency Providers
def get_job_queue() -> SQLiteJobQueue:
    queue = getattr(app.state, "job_queue", None)
    if queue is None:
        queue = SQLiteJobQueue(db_path=os.getenv("STATE_DB_PATH", STATE_DB_PATH))
    return queue


def get_delta_engine() -> SQLiteDeltaEngine:
    engine = getattr(app.state, "delta_engine", None)
    if engine is None:
        engine = SQLiteDeltaEngine(db_path=os.getenv("STATE_DB_PATH", STATE_DB_PATH))
    return engine


def get_qdrant_client() -> AsyncQdrantClient:
    client = getattr(app.state, "qdrant_client", None)
    if client is None:
        client = AsyncQdrantClient(
            host=os.getenv("QDRANT_HOST", QDRANT_HOST),
            port=int(os.getenv("QDRANT_PORT", str(QDRANT_PORT))),
        )
    return client


# ============================================================================
# Request Models
# ============================================================================


class SyncDirectoryRequest(BaseModel):
    source_directory: str = Field(default="")
    collection_name: str = Field(default="default_collection")
    file_types: list[str] = Field(default_factory=lambda: [".pdf", ".txt", ".md", ".html"])
    prune_orphans: bool = Field(default=True)
    chunking_strategy: ChunkingStrategy = Field(default=ChunkingStrategy.HIERARCHICAL)


class CreateCollectionBody(BaseModel):
    collection_name: str
    dimensions: int = 768
    distance: DistanceMetric = DistanceMetric.COSINE
    enable_quantization: bool = True


def _dto_to_response(dto: IngestJobDTO) -> IngestJobResponse:
    """Maps internal IngestJobDTO to external REST IngestJobResponse."""
    return IngestJobResponse(
        id=dto.id,
        filepath=dto.filepath,
        collection_name=dto.collection_name,
        action=dto.action.value,
        status=dto.status.value,
        stage=dto.stage.value if dto.stage else None,
        progress=dto.progress.to_dict(),
        options=dto.options,
        retry_count=dto.retry_count,
        created_at=dto.created_at,
        completed_at=dto.completed_at,
        error=dto.error,
    )


# ============================================================================
# REST Endpoints
# ============================================================================


@app.get("/healthz", status_code=status.HTTP_200_OK)
async def healthcheck(
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> dict[str, str]:
    """Active healthcheck probe testing SQLite state DB and Qdrant connectivity."""
    db_status = "ok"
    try:
        with job_queue.conn:
            job_queue.conn.execute("SELECT 1")
    except Exception as e:
        logger.error(f"Healthcheck SQLite probe failed: {e}")
        db_status = f"unhealthy: {e}"

    qdrant_status = "ok"
    try:
        await qdrant_client.get_collections()
    except Exception as e:
        logger.warning(f"Healthcheck Qdrant probe failed: {e}")
        qdrant_status = f"unhealthy: {e}"

    overall = "healthy" if db_status == "ok" and qdrant_status == "ok" else "degraded"
    status_code = (
        status.HTTP_200_OK if overall == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    )
    res = {
        "status": overall,
        "service": "ingestion-service",
        "version": "1.0.0",
        "database": db_status,
        "vectordb": qdrant_status,
    }
    if status_code != status.HTTP_200_OK:
        raise HTTPException(status_code=status_code, detail=res)
    return res


@app.post("/ingest/file", response_model=IngestFileResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest_file(
    file: UploadFile = File(...),
    collection_name: str = Form("default_collection"),
    chunk_size: int = Form(350),
    chunk_overlap: int = Form(50),
    chunking_strategy: ChunkingStrategy = Form(ChunkingStrategy.HIERARCHICAL),
    pdf_tier: PdfExtractionTier = Form(PdfExtractionTier.TIER1_NATIVE),
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
) -> IngestFileResponse:
    """Accepts document file upload and enqueues it for background ingestion."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename in upload")

    clean_filename = os.path.basename(file.filename)
    if clean_filename in {"", ".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    base_docs_dir = Path(os.getenv("SOURCE_DOCS_DIR", SOURCE_DOCS_DIR)).resolve()
    target_dir = base_docs_dir / collection_name
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{uuid.uuid4().hex[:8]}_{clean_filename}"

    if not target_path.resolve().is_relative_to(base_docs_dir):
        raise HTTPException(status_code=400, detail="Path traversal detected in upload")

    try:
        with open(target_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        logger.error(f"Failed to persist uploaded file {file.filename}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {e}") from e

    job_options: dict[str, str | int | float | bool] = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "chunking_strategy": chunking_strategy.value,
        "pdf_tier": pdf_tier.value,
    }

    job_id = job_queue.enqueue(
        filepath=str(target_path),
        collection_name=collection_name,
        action=JobAction.NEW,
        options=job_options,
    )

    logger.info(f"Queued file ingestion job #{job_id} for {clean_filename} -> {collection_name}")
    return IngestFileResponse(
        job_id=job_id,
        collection_name=collection_name,
        filename=clean_filename,
        status=JobStatus.PENDING.value,
        message="Document uploaded and queued for processing.",
    )


@app.post("/ingest/sync", response_model=IngestSyncResponse)
async def ingest_sync(
    payload: SyncDirectoryRequest,
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
    delta_engine: SQLiteDeltaEngine = Depends(get_delta_engine),
) -> IngestSyncResponse:
    """Triggers directory delta synchronization across documents, offloading to threadpool."""
    base_docs_dir = Path(os.getenv("SOURCE_DOCS_DIR", SOURCE_DOCS_DIR)).resolve()
    raw_source = payload.source_directory if payload.source_directory else str(base_docs_dir)
    req_dir = Path(raw_source).resolve()

    if not req_dir.exists():
        raise HTTPException(status_code=400, detail=f"Source directory does not exist: {req_dir}")

    # Prevent directory walking outside authorized data/temp roots
    temp_root = Path(tempfile.gettempdir()).resolve()
    if not req_dir.is_relative_to(base_docs_dir) and not req_dir.is_relative_to(temp_root):
        raise HTTPException(
            status_code=400, detail="Source directory must be located inside SOURCE_DOCS_DIR"
        )

    def _sync_worker() -> IngestSyncResponse:
        result = delta_engine.compute_deltas(
            source_directory=str(req_dir),
            collection_name=payload.collection_name,
            file_types=payload.file_types,
        )

        new_count = 0
        mod_count = 0
        del_count = 0
        unchanged_count = 0

        options: dict[str, str | int | float | bool] = {
            "chunking_strategy": payload.chunking_strategy.value,
        }

        for delta in result.deltas:
            if delta.action == DeltaAction.ADD:
                job_queue.enqueue(
                    delta.filepath, payload.collection_name, JobAction.NEW, options=options
                )
                new_count += 1
            elif delta.action == DeltaAction.UPDATE:
                job_queue.enqueue(
                    delta.filepath, payload.collection_name, JobAction.MODIFIED, options=options
                )
                mod_count += 1
            elif delta.action == DeltaAction.DELETE:
                if payload.prune_orphans:
                    job_queue.enqueue(
                        delta.filepath, payload.collection_name, JobAction.DELETED, options=options
                    )
                    del_count += 1
            else:
                unchanged_count += 1

        total_enqueued = new_count + mod_count + del_count
        logger.info(
            f"Delta sync complete for {req_dir}: {total_enqueued} jobs enqueued "
            f"({new_count} new, {mod_count} modified, {del_count} deleted, {unchanged_count} unchanged)"
        )

        return IngestSyncResponse(
            collection_name=payload.collection_name,
            source_directory=str(req_dir),
            files_scanned=result.scanned_count,
            new_jobs_queued=new_count,
            modified_jobs_queued=mod_count,
            deleted_jobs_queued=del_count,
            unchanged_files=unchanged_count,
            total_jobs_enqueued=total_enqueued,
        )

    return await asyncio.to_thread(_sync_worker)


@app.post("/collections", response_model=CreateCollectionResponse)
async def create_collection(
    payload: CreateCollectionBody,
    qdrant_client: AsyncQdrantClient = Depends(get_qdrant_client),
) -> CreateCollectionResponse:
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
            existing_dims: int = payload.dimensions
            existing_dist: str = payload.distance.value
            try:
                col_info = await qdrant_client.get_collection(payload.collection_name)
                vectors_cfg = col_info.config.params.vectors
                if hasattr(vectors_cfg, "size") and isinstance(vectors_cfg.size, int):
                    existing_dims = vectors_cfg.size
                if hasattr(vectors_cfg, "distance"):
                    existing_dist = str(vectors_cfg.distance)
            except Exception as e:
                logger.debug(f"Could not retrieve existing collection vectors config: {e}")

            return CreateCollectionResponse(
                collection_name=payload.collection_name,
                dimensions=existing_dims,
                distance=existing_dist,
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
async def get_job_status(
    job_id: int,
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
) -> IngestJobResponse:
    """Retrieves operational progress and status of an ingestion job."""
    dto = job_queue.get_job_dto(job_id)
    if not dto:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    return _dto_to_response(dto)


@app.get("/jobs", response_model=IngestJobListResponse)
async def list_jobs(
    collection_name: str | None = None,
    status: JobStatus | None = None,
    limit: int = 50,
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
) -> IngestJobListResponse:
    """Lists ingestion jobs matching optional criteria."""
    dtos = job_queue.list_jobs(collection_name=collection_name, status=status, limit=limit)
    responses = [_dto_to_response(d) for d in dtos]
    return IngestJobListResponse(total_jobs=len(responses), jobs=responses)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job(
    job_id: int,
    job_queue: SQLiteJobQueue = Depends(get_job_queue),
) -> dict[str, str | int]:
    """Aborts a pending or running ingestion job."""
    job = job_queue.get_job_dto(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job #{job_id} not found")
    if job.status in (JobStatus.COMPLETED, JobStatus.FAILED):
        raise HTTPException(
            status_code=409,
            detail=f"Job #{job_id} is in terminal state '{job.status.value}' and cannot be cancelled",
        )
    success = job_queue.cancel_job(job_id)
    if not success:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to cancel job #{job_id}",
        )
    return {
        "job_id": job_id,
        "status": JobStatus.CANCELLED.value,
        "message": "Job cancelled successfully.",
    }
