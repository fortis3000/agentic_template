"""Ingestion package for document processing, chunking, and vector DB indexing."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.ingestion.chunkers import fixed_chunker, markdown_chunker, semantic_chunker
    from src.ingestion.helper import ingest_document
    from src.ingestion.pipeline import IngestionConfigSchema, IngestionPipeline

__all__ = [
    "IngestionConfigSchema",
    "IngestionPipeline",
    "fixed_chunker",
    "ingest_document",
    "markdown_chunker",
    "semantic_chunker",
]


def __getattr__(name: str) -> Any:
    """Lazy import components on demand to prevent eager loading of heavy dependencies."""
    if name in {"fixed_chunker", "markdown_chunker", "semantic_chunker"}:
        from src.ingestion import chunkers  # noqa: PLC0415

        return getattr(chunkers, name)
    if name == "ingest_document":
        from src.ingestion import helper  # noqa: PLC0415

        return getattr(helper, name)
    if name in {"IngestionConfigSchema", "IngestionPipeline"}:
        from src.ingestion import pipeline  # noqa: PLC0415

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
