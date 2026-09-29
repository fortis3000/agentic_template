"""Domain types and enums for the ingestion microservice.

Contains zero internal project imports (standard library only) to ensure
clean dependency inversion and zero circular dependencies.
"""

from __future__ import annotations

from enum import StrEnum


class JobStatus(StrEnum):
    """Operational lifecycle state of an ingestion job."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobStage(StrEnum):
    """Active processing phase of a running ingestion job (per CONTEXT.md)."""

    EXTRACTING = "EXTRACTING"
    CHUNKING = "CHUNKING"
    EMBEDDING = "EMBEDDING"
    INDEXING = "INDEXING"


class JobAction(StrEnum):
    """Action associated with the file in an ingestion job."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    # Backwards-compatible aliases
    NEW = "NEW"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"


class DeltaAction(StrEnum):
    """Synchronization classification for a document file."""

    ADD = "ADD"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    UNCHANGED = "UNCHANGED"


DELTA_TO_JOB_ACTION: dict[DeltaAction, JobAction] = {
    DeltaAction.ADD: JobAction.ADD,
    DeltaAction.UPDATE: JobAction.UPDATE,
    DeltaAction.DELETE: JobAction.DELETE,
}


class ChunkingStrategy(StrEnum):
    """Supported text chunking strategies."""

    HIERARCHICAL = "hierarchical"
    FIXED = "fixed"
    MARKDOWN = "markdown"
    SEMANTIC = "semantic"


class PageClassification(StrEnum):
    """Classification returned by pdf-inspector."""

    TEXT_BASED = "TextBased"
    SCANNED = "Scanned"
    IMAGE_BASED = "ImageBased"
    MIXED = "Mixed"
    EMPTY = "Empty"


class PdfExtractionTier(StrEnum):
    """Three-tier extraction hierarchy for PDF processing."""

    TIER1_NATIVE = "tier1_native"  # Local native text extraction (<50ms, $0)
    TIER2_ONNX_OCR = "tier2_onnx_ocr"  # Local neural ONNX PP-OCRv6 (<800ms, $0)
    TIER3_CLOUD_VLM = "tier3_cloud_vlm"  # Gemini 2.0 Flash VLM fallback


class DistanceMetric(StrEnum):
    """Distance metrics supported by Qdrant vector collections."""

    COSINE = "Cosine"
    EUCLID = "Euclid"
    DOT = "Dot"
