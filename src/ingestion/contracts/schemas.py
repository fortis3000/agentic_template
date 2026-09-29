"""Data transfer objects and schemas for the ingestion microservice.

Contains zero internal project imports (standard library only) to ensure
clean dependency inversion and zero circular dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .types import (
    ChunkingStrategy,
    DeltaAction,
    DistanceMetric,
    JobAction,
    JobStage,
    JobStatus,
    PdfExtractionTier,
)


@dataclass
class JobProgress:
    """Quantitative progress metrics for an ingestion job."""

    pages_processed: int = 0
    total_pages: int = 0
    chunks_indexed: int = 0
    total_chunks: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serializes progress counters to a dictionary."""
        return {
            "pages_processed": self.pages_processed,
            "total_pages": self.total_pages,
            "chunks_indexed": self.chunks_indexed,
            "total_chunks": self.total_chunks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> JobProgress:
        """Constructs JobProgress from a dictionary."""
        if not data:
            return cls()
        return cls(
            pages_processed=data.get("pages_processed", 0),
            total_pages=data.get("total_pages", 0),
            chunks_indexed=data.get("chunks_indexed", 0),
            total_chunks=data.get("total_chunks", 0),
        )


@dataclass
class IngestJobDTO:
    """Detailed internal representation of an ingestion job record."""

    id: int
    filepath: str
    collection_name: str
    action: JobAction
    status: JobStatus
    stage: JobStage | None = None
    progress: JobProgress = field(default_factory=JobProgress)
    options: dict[str, str | int | float | bool] = field(default_factory=dict)
    worker_id: str | None = None
    lease_expires_at: float | None = None
    retry_count: int = 0
    created_at: float = 0.0
    completed_at: float | None = None
    error: str | None = None


@dataclass
class IngestJobResponse:
    """REST API response model for GET /jobs/{job_id}."""

    id: int
    filepath: str
    collection_name: str
    action: str
    status: str
    stage: str | None
    progress: dict[str, int]
    retry_count: int
    created_at: float
    options: dict[str, str | int | float | bool] = field(default_factory=dict)
    completed_at: float | None = None
    error: str | None = None


@dataclass
class IngestJobListResponse:
    """REST API response model for GET /jobs."""

    total_jobs: int
    jobs: list[IngestJobResponse]


@dataclass
class IngestFileRequest:
    """REST API request model for POST /ingest/file."""

    collection_name: str
    chunk_size: int = 350
    chunk_overlap: int = 50
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL
    pdf_tier: PdfExtractionTier = PdfExtractionTier.TIER1_NATIVE
    async_mode: bool = True  # If True, enqueues background job; If False, blocks until done


@dataclass
class IngestFileResponse:
    """REST API response model for POST /ingest/file."""

    job_id: int
    collection_name: str
    filename: str
    status: str
    message: str


@dataclass
class IngestSyncRequest:
    """REST API request model for POST /ingest/sync."""

    source_directory: str
    collection_name: str
    file_types: list[str] = field(default_factory=lambda: [".pdf", ".txt", ".md", ".html"])
    prune_orphans: bool = True
    chunking_strategy: ChunkingStrategy = ChunkingStrategy.HIERARCHICAL


@dataclass
class IngestSyncResponse:
    """REST API response model for POST /ingest/sync."""

    collection_name: str
    source_directory: str
    files_scanned: int
    new_jobs_queued: int
    modified_jobs_queued: int
    deleted_jobs_queued: int
    unchanged_files: int
    total_jobs_enqueued: int


@dataclass
class CreateCollectionRequest:
    """REST API request model for POST /collections."""

    collection_name: str
    dimensions: int = 768
    distance: DistanceMetric = DistanceMetric.COSINE
    enable_quantization: bool = True


@dataclass
class CreateCollectionResponse:
    """REST API response model for POST /collections."""

    collection_name: str
    dimensions: int
    distance: str
    status: str
    message: str


@dataclass
class IngestedChunkPayload:
    """Schema for chunk metadata payload stored in Qdrant points."""

    chunk_id: str
    parent_id: str | None
    article_id: str
    breadcrumbs: list[str]
    heading: str | None
    level: int | None
    is_atomic_block: bool
    block_type: str
    source_file: str
    page_number: int | None
    text: str
    metadata: dict[str, str | int | float | bool | list[str] | None] = field(default_factory=dict)


@dataclass
class FileDelta:
    """Delta status of a single tracked document file."""

    filepath: str
    collection_name: str
    action: DeltaAction
    current_hash: str
    stored_hash: str | None
    last_modified: float
    existing_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class DeltaSyncResult:
    """Summary of a delta scanning run."""

    source_directory: str
    collection_name: str
    scanned_count: int
    deltas: list[FileDelta]
