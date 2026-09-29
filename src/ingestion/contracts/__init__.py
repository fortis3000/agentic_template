"""Leaf contracts and data transfer objects for the ingestion microservice.

All modules in this package import only from the Python standard library,
guaranteeing zero circular dependencies and clean dependency inversion.
"""

from __future__ import annotations

from .delta_engine import DeltaSyncEngineProtocol
from .job_queue import JobQueueProtocol
from .schemas import (
    CreateCollectionRequest,
    CreateCollectionResponse,
    DeltaSyncResult,
    FileDelta,
    IngestFileRequest,
    IngestFileResponse,
    IngestJobDTO,
    IngestJobListResponse,
    IngestJobResponse,
    IngestSyncRequest,
    IngestSyncResponse,
    IngestedChunkPayload,
    JobProgress,
)
from .types import (
    ChunkingStrategy,
    DeltaAction,
    DistanceMetric,
    JobAction,
    JobStage,
    JobStatus,
    PageClassification,
    PdfExtractionTier,
)

__all__ = [
    "ChunkingStrategy",
    "CreateCollectionRequest",
    "CreateCollectionResponse",
    "DeltaAction",
    "DeltaSyncEngineProtocol",
    "DeltaSyncResult",
    "DistanceMetric",
    "FileDelta",
    "IngestJobListResponse",
    "IngestFileRequest",
    "IngestFileResponse",
    "IngestJobDTO",
    "IngestJobResponse",
    "IngestSyncRequest",
    "IngestSyncResponse",
    "IngestedChunkPayload",
    "JobAction",
    "JobProgress",
    "JobQueueProtocol",
    "JobStage",
    "JobStatus",
    "PageClassification",
    "PdfExtractionTier",
]
