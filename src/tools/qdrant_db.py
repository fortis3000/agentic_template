import json
from typing import Any, cast

from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
)

from src.tools.vectordb_base import BaseVectorDB, VectorDBFactory
from src.utils.logger import get_logger

logger = get_logger(__name__)


@VectorDBFactory.register("qdrant")
class QdrantVectorDB(BaseVectorDB):
    """Qdrant Vector Database implementation with Arize Phoenix tracing support."""

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
        self.host = host
        self.port = port
        self.kwargs = kwargs

        if location:
            logger.info(f"Initializing QdrantVectorDB in-memory (location: {location}).")
            self.client = AsyncQdrantClient(location=location, **kwargs)
        elif url:
            logger.info(f"Initializing QdrantVectorDB with URL: {url}.")
            self.client = AsyncQdrantClient(url=url, **kwargs)
        else:
            logger.info(f"Initializing QdrantVectorDB with host: {host}, port: {port}.")
            self.client = AsyncQdrantClient(host=host, port=port, **kwargs)

    async def create_collection(
        self,
        collection_name: str,
        vector_size: int,
        distance: str = "Cosine",
    ) -> None:
        """Create a Qdrant collection if it does not already exist."""
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
                    f"Creating collection '{collection_name}' (dim: {vector_size}, distance: {distance})."
                )
                await self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=dist),
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
        """Insert vectors and payloads into a collection."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("insert") as span:
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)
            span.set_attribute("db.operation", "insert")
            span.set_attribute("db.insert.count", len(ids))

            points = []
            for i, (p_id, vec) in enumerate(zip(ids, vectors)):
                payload = payloads[i] if payloads else {}
                points.append(PointStruct(id=p_id, vector=vec, payload=payload))

            await self.client.upsert(collection_name=collection_name, points=points)
            logger.info(f"Upserted {len(points)} points into collection '{collection_name}'.")

    async def search(
        self,
        collection_name: str,
        query_vector: list[float],
        limit: int = 5,
        filter_dict: dict[str, Any] | None = None,
        query_text: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search similar vectors in Qdrant collection, instrumented for Arize Phoenix."""
        tracer = trace.get_tracer("qdrant-db")
        with tracer.start_as_current_span("search") as span:
            # Set OpenInference retriever span kind
            span.set_attribute(
                SpanAttributes.OPENINFERENCE_SPAN_KIND, OpenInferenceSpanKindValues.RETRIEVER.value
            )
            # Log query vector or input text as input
            input_val = query_text if query_text else str(query_vector)
            span.set_attribute(SpanAttributes.INPUT_VALUE, input_val)
            span.set_attribute("db.system", "qdrant")
            span.set_attribute("db.name", collection_name)

            q_filter = None
            if filter_dict:
                conditions: list[Any] = []
                for k, v in filter_dict.items():
                    conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
                q_filter = Filter(must=conditions)

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
                hits.append(
                    {
                        "id": hit.id,
                        "score": hit.score,
                        "payload": payload,
                    }
                )

                # Trace document retrieval under OpenInference conventions
                span.set_attribute(f"retrieval.documents.{idx}.document.id", str(hit.id))
                content = payload.get("text") or payload.get("content") or ""
                span.set_attribute(f"retrieval.documents.{idx}.document.content", content)
                span.set_attribute(f"retrieval.documents.{idx}.document.score", float(hit.score))
                span.set_attribute(
                    f"retrieval.documents.{idx}.document.metadata", json.dumps(payload)
                )

            # Standard output values
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
