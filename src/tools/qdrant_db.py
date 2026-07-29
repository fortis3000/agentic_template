import asyncio
import hashlib
import json
import os
import re
from typing import Any, cast

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    Fusion,
    FusionQuery,
    MatchValue,
    PointIdsList,
    PointStruct,
    Prefetch,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

from src.tools.vectordb_base import BaseVectorDB, VectorDBFactory
from src.utils.logger import get_logger

logger = get_logger(__name__)


def generate_sparse_vector(text: str) -> SparseVector:
    """Generate a lightweight bag-of-words sparse vector representation of the text."""
    words = re.findall(r"\w+", text.lower())
    index_counts: dict[int, float] = {}
    for w in words:
        idx = int(hashlib.sha256(w.encode("utf-8")).hexdigest(), 16) % 10000
        index_counts[idx] = index_counts.get(idx, 0.0) + 1.0

    sorted_indices = sorted(index_counts.keys())
    return SparseVector(
        indices=sorted_indices,
        values=[index_counts[i] for i in sorted_indices],
    )


@VectorDBFactory.register("qdrant")
class QdrantVectorDB(BaseVectorDB):
    """Qdrant Vector Database implementation with Arize Phoenix tracing support."""

    _instances: dict[str, AsyncQdrantClient] = {}

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        url: str | None = None,
        location: str | None = None,
        **kwargs: Any,
    ):
        """Initialize the Async Qdrant Client.

        Allows in-memory execution via location=':memory:'.
        """
        self.location = location
        self.url = url
        self.host = os.getenv("QDRANT_HOST") or host
        self.port = port
        self.kwargs = kwargs

        try:
            loop_id = id(asyncio.get_running_loop())
        except RuntimeError:
            loop_id = None

        key = (
            f"{loop_id}:{self.location or ''}:{self.host or ''}:{self.port or ''}:{self.url or ''}"
        )
        if key not in QdrantVectorDB._instances:
            if self.location:
                logger.info(f"Initializing QdrantVectorDB in-memory (location: {self.location}).")
                QdrantVectorDB._instances[key] = AsyncQdrantClient(location=self.location, **kwargs)
            elif self.url:
                logger.info(f"Initializing QdrantVectorDB with URL: {self.url}.")
                QdrantVectorDB._instances[key] = AsyncQdrantClient(url=self.url, **kwargs)
            else:
                logger.info(
                    f"Initializing QdrantVectorDB with host: {self.host}, port: {self.port}."
                )
                QdrantVectorDB._instances[key] = AsyncQdrantClient(
                    host=self.host, port=self.port, **kwargs
                )

        self.client = QdrantVectorDB._instances[key]

    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """Create a Qdrant collection supporting dense, sparse and image vector keys if it does not exist."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("create_collection") as span:
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)

            dist = Distance.COSINE
            dist_str = distance.upper()
            if dist_str in {"EUCLID", "L2"}:
                dist = Distance.EUCLID
            elif dist_str == "DOT":
                dist = Distance.DOT

            exists = await self.client.collection_exists(collection_name)
            if not exists:
                logger.info(
                    f"Creating collection '{collection_name}' with dense (dim: {vector_size}), image (dim: 512) and sparse support."
                )
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        "dense": VectorParams(size=vector_size, distance=dist),
                        "image": VectorParams(size=512, distance=dist),
                    },
                    sparse_vectors_config={"sparse": SparseVectorParams()},
                )
            else:
                logger.info(f"Collection '{collection_name}' already exists. Skipping creation.")

    async def insert(
        self,
        collection_name: str,
        ids: list[str | int],
        vectors: list[list[float]],
        payloads: list[dict[str, Any]] | None = None,
    ) -> None:
        """Insert vectors and payloads into a collection, dynamically populating sparse/image vectors if supported."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("insert") as span:
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)
            span.set_attribute("db.operation", "insert")
            span.set_attribute("db.insert.count", len(ids))

            uses_named = False
            try:
                coll_info = await self.client.get_collection(collection_name)
                uses_named = isinstance(coll_info.config.params.vectors, dict)
            except Exception:  # nosec B110
                pass

            points = []
            for i, (p_id, vec) in enumerate(zip(ids, vectors)):
                payload = payloads[i] if payloads else {}
                if uses_named:
                    vector_dict: dict[str, Any] = {"dense": vec}
                    if "text" in payload:
                        vector_dict["sparse"] = generate_sparse_vector(payload["text"])
                    if "image" in payload and isinstance(payload["image"], list):
                        vector_dict["image"] = payload.pop("image")
                    elif "image_vector" in payload and isinstance(payload["image_vector"], list):
                        vector_dict["image"] = payload.pop("image_vector")
                    points.append(PointStruct(id=p_id, vector=vector_dict, payload=payload))
                else:
                    points.append(PointStruct(id=p_id, vector=vec, payload=payload))

            await self.client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Upserted {len(points)} points into collection '{collection_name}'.")

    async def search(  # noqa: PLR0915
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
        query_text: str | None = None,
        search_type: str = "dense",
        allowed_answer_fields: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar vectors in Qdrant collection supporting dense, sparse hybrid, or image vector searches."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("search") as span:
            span.set_attribute(
                SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.RETRIEVER.value
            )
            input_val = query_text if query_text else str(query_vector)
            span.set_attribute(SpanAttributes.INPUT_VALUE, input_val)
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)

            uses_named = False
            try:
                coll_info = await self.client.get_collection(collection_name)
                uses_named = isinstance(coll_info.config.params.vectors, dict)
            except Exception:  # nosec B110
                pass

            q_filter = None
            if filter_dict:
                conditions: list[Any] = []
                for k, v in filter_dict.items():
                    conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
                q_filter = Filter(must=conditions)

            if uses_named:
                if search_type == "hybrid":
                    sparse_vec = generate_sparse_vector(query_text or "")
                    prefetch = [
                        Prefetch(query=query_vector, using="dense", limit=limit),
                        Prefetch(query=sparse_vec, using="sparse", limit=limit),
                    ]
                    res = await self.client.query_points(
                        collection_name=collection_name,
                        query=FusionQuery(fusion=Fusion.RRF),
                        prefetch=prefetch,
                        limit=limit,
                        query_filter=q_filter,
                    )
                elif search_type == "image":
                    res = await self.client.query_points(
                        collection_name=collection_name,
                        query=query_vector,
                        using="image",
                        limit=limit,
                        query_filter=q_filter,
                    )
                else:
                    res = await self.client.query_points(
                        collection_name=collection_name,
                        query=query_vector,
                        using="dense",
                        limit=limit,
                        query_filter=q_filter,
                    )
            else:
                res = await self.client.query_points(
                    collection_name=collection_name,
                    query=query_vector,
                    limit=limit,
                    query_filter=q_filter,
                )
            results = res.points

            hits = []
            for idx, hit in enumerate(results):
                payload = hit.payload or {}
                if allowed_answer_fields:
                    payload = {k: v for k, v in payload.items() if k in allowed_answer_fields}

                hits.append(
                    {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": payload,
                    }
                )

                span.set_attribute(f"retrieval.documents.{idx}.document.id", str(hit.id))
                content = payload.get("text") or payload.get("content") or ""
                span.set_attribute(f"retrieval.documents.{idx}.document.content", content)
                span.set_attribute(f"retrieval.documents.{idx}.document.score", float(hit.score))
                span.set_attribute(
                    f"retrieval.documents.{idx}.document.metadata", json.dumps(payload)
                )

            span.set_attribute(SpanAttributes.OUTPUT_VALUE, json.dumps(hits))
            return hits

    async def delete(
        self,
        collection_name: str,
        ids: list[str | int],
    ) -> None:
        """Delete vectors from collection by ID."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("delete") as span:
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)
            span.set_attribute("db.operation", "delete")

            await self.client.delete(
                collection_name=collection_name,
                points_selector=PointIdsList(points=cast(Any, ids)),
            )
            logger.info(f"Deleted points {ids} from collection '{collection_name}'.")
