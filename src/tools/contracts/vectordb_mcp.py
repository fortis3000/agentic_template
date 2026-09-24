"""Leaf contracts and DTOs for VectorDB MCP tools and services.

Contains zero internal project imports (standard library only) to ensure
clean dependency inversion and zero circular dependencies.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class VectorDBSearchType(StrEnum):
    """Supported search modalities in VectorDB MCP."""

    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"
    IMAGE = "image"


@dataclass
class VectorSearchRequest:
    """Request DTO for vector search operations."""

    query: str | None = None
    image: str | None = None
    limit: int = 5
    score_threshold: float = 0.0
    filters: dict[str, Any] = field(default_factory=dict)
    sparse: bool = False
    collection_name: str | None = None


@dataclass
class VectorSearchResultItem:
    """Individual item returned by vector similarity search."""

    id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class VectorStoreRequest:
    """Request DTO for vector storage operations."""

    text: str | None = None
    image: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    collection_name: str | None = None


@dataclass
class VectorStoreResponse:
    """Response DTO for vector storage operations."""

    id: str
    status: str
    collection: str
    dimensions: int | None = None


@dataclass
class HealthCheckResponse:
    """Response DTO for microservice healthcheck."""

    status: str
    service: str
    qdrant: str
    collection: str | None = None
    points_count: int | None = None
    error: str | None = None
