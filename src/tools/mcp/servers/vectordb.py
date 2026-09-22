"""VectorDB Model Context Protocol (MCP) Server implementation.

Provides a containerized or standalone FastMCP service exposing vector similarity search
and document/episodic memory ingestion over HTTP/SSE.
"""

import asyncio
import base64
import json
import os
import uuid
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import trace
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.agents.config import EmbeddingModelConfigSchema, VectorDBConfigSchema
from src.agents.embeddings import BaseEmbeddingClient, EmbeddingModelFactory
from src.tools.contracts.vectordb_mcp import (
    VectorDBSearchType,
    VectorStoreResponse,
)
from src.tools.local.qdrant_db import generate_sparse_vector
from src.tools.local.vectordb_base import BaseVectorDB, VectorDBFactory
from src.utils.logger import get_logger

try:
    from phoenix.otel import register as phoenix_register
except ImportError:
    phoenix_register = None

logger = get_logger(__name__)

MIN_DECODED_IMAGE_BYTES = 10


def _init_phoenix_tracing() -> None:
    """Initialize OpenTelemetry tracer provider targeting Arize Phoenix if configured."""
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    if endpoint and phoenix_register is not None:
        try:
            project_name = os.getenv("PHOENIX_PROJECT_NAME", "vectordb-mcp")
            phoenix_register(project_name=project_name, endpoint=endpoint)
            logger.info(f"Registered Phoenix tracer for endpoint: {endpoint}")
        except Exception as e:
            logger.warning(f"Could not register Phoenix tracer: {e}")


async def _extract_image_bytes_and_mime(image_input: str) -> tuple[bytes, str]:
    """Parse image input: data URL, raw Base64, or local file inside allowed directory.

    Sandboxes local file paths against ALLOWED_IMAGE_DIR to prevent arbitrary file disclosure.
    Uses asyncio.to_thread for non-blocking file reads.
    """
    # 1. Check for data URL: data:image/<type>;base64,<data>
    if image_input.startswith("data:image/"):
        comma_idx = image_input.find(",")
        if comma_idx != -1:
            header = image_input[:comma_idx]
            raw_b64 = image_input[comma_idx + 1 :]
            mime_part = header[5:].split(";")[0]
            try:
                decoded = base64.b64decode(raw_b64)
                return decoded, mime_part or "image/png"
            except Exception as e:
                raise ValueError(f"Failed to decode base64 image data URL: {e}") from e

    # 2. Check for local file path inside allowed sandbox directory
    allowed_dir_str = os.getenv("ALLOWED_IMAGE_DIR", "data")
    allowed_dir = Path(allowed_dir_str).resolve()

    is_path_candidate = any(char in image_input for char in ("/\\")) or any(
        image_input.lower().endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".gif", ".webp")
    )

    if is_path_candidate:
        target_path = Path(image_input).resolve()
        # Security check: must reside inside allowed directory
        if not target_path.is_relative_to(allowed_dir):
            raise ValueError(
                f"Access to file '{image_input}' outside allowed directory '{allowed_dir}' is prohibited."
            )
        if target_path.is_file():
            ext = target_path.suffix.lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            mime = mime_map.get(ext, "image/png")
            content = await asyncio.to_thread(target_path.read_bytes)
            return content, mime

    # 3. Try decoding raw base64 string directly
    try:
        decoded = base64.b64decode(image_input, validate=True)
        if len(decoded) > MIN_DECODED_IMAGE_BYTES:
            return decoded, "image/png"
    except Exception:  # nosec B110
        pass

    raise ValueError(
        f"Invalid image input: '{image_input[:100]}...' is neither an accessible file in "
        f"'{allowed_dir}' nor a valid Base64 data URL."
    )


def create_vectordb_mcp_server(  # noqa: PLR0915
    db: BaseVectorDB | None = None,
    embed_client: BaseEmbeddingClient | None = None,
    image_embed_client: BaseEmbeddingClient | None = None,
    default_collection: str | None = None,
    allowed_search_fields: list[str] | None = None,
    allowed_answer_fields: list[str] | None = None,
) -> FastMCP:
    """Factory creating and configuring the VectorDB FastMCP server."""
    _init_phoenix_tracing()

    # Resolve collection name
    default_coll = (
        default_collection or os.getenv("DEFAULT_COLLECTION_NAME") or "default_collection"
    )

    search_fields = allowed_search_fields or [
        f.strip()
        for f in os.getenv("ALLOWED_SEARCH_FIELDS", "filepath,chunk_index,source,category").split(
            ","
        )
        if f.strip()
    ]
    answer_fields = allowed_answer_fields or [
        f.strip()
        for f in os.getenv(
            "ALLOWED_ANSWER_FIELDS", "text,filepath,chunk_index,source,category"
        ).split(",")
        if f.strip()
    ]

    # Initialize Embedding Clients if not supplied
    emb_provider = os.getenv("EMBEDDING_PROVIDER", "google")
    emb_model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
    emb_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))
    emb_img_dims = int(os.getenv("EMBEDDING_IMAGE_DIMENSIONS", str(emb_dims)))

    if embed_client is None:
        emb_cfg = EmbeddingModelConfigSchema(
            provider=emb_provider,
            model=emb_model,
            dimensions=emb_dims,
            image_dimensions=emb_img_dims,
            api_key=os.getenv("GEMINI_API_KEY")
            if emb_provider == "google"
            else os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OLLAMA_BASE_URL"),
        )
        embed_client = EmbeddingModelFactory.create(emb_cfg)

    # Initialize dedicated image embedding client (ensuring multimodal capability)
    if image_embed_client is None:
        if embed_client is not None:
            image_embed_client = embed_client
        elif emb_provider == "google" and "multimodal" not in emb_model.lower():
            # Google multimodal requires a model containing 'multimodal'
            img_model = os.getenv("EMBEDDING_IMAGE_MODEL", "multimodal-embedding-001")
            img_cfg = EmbeddingModelConfigSchema(
                provider=emb_provider,
                model=img_model,
                dimensions=emb_img_dims,
                image_dimensions=emb_img_dims,
                api_key=os.getenv("GEMINI_API_KEY"),
            )
            image_embed_client = EmbeddingModelFactory.create(img_cfg)
        else:
            image_embed_client = embed_client

    # Initialize VectorDB instance if not supplied
    if db is None:
        db_cfg = VectorDBConfigSchema(
            type="qdrant",
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            url=os.getenv("QDRANT_URL"),
            location=os.getenv("QDRANT_LOCATION"),
        )
        db_params = db_cfg.model_dump(exclude={"type"}, exclude_none=True)
        db = VectorDBFactory.create("qdrant", **db_params)

    mcp = FastMCP("VectorDB MCP Server")

    # Custom healthcheck endpoint with live Qdrant connectivity test
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        health = await db.health_check()
        if health.get("status") == "connected":
            return JSONResponse(
                {
                    "status": "healthy",
                    "service": "vectordb-mcp",
                    "qdrant": health,
                    "collection": default_coll,
                },
                status_code=200,
            )
        return JSONResponse(
            {
                "status": "unhealthy",
                "service": "vectordb-mcp",
                "error": health.get("error", "Qdrant connection error"),
            },
            status_code=503,
        )

    @mcp.tool(
        name="vectordb_search",
        description=(
            "Search the document vector database for relevant information. "
            "Supports dense text, hybrid (dense + sparse RRF), and multimodal image queries."
        ),
    )
    async def vectordb_search(
        query_text: str,
        filter_dict: dict[str, Any] | None = None,
        search_type: str = "dense",
        limit: int = 5,
        collection_name: str | None = None,
    ) -> str:
        """Search the document vector database.

        Args:
            query_text: Text query or image data (file path or data:image/...;base64 string).
            filter_dict: Optional metadata payload key-value filters.
            search_type: Search modality: 'dense', 'hybrid' (dense+sparse RRF), or 'image'.
            limit: Maximum number of ranked results to return (1-100).
            collection_name: Optional collection override (defaults to server default).
        """
        target_collection = collection_name or default_coll

        # Validate search_type against enum values
        valid_search_types = {t.value for t in VectorDBSearchType}
        if search_type not in valid_search_types:
            raise ValueError(
                f"Invalid search_type '{search_type}'. Allowed values: {sorted(valid_search_types)}."
            )

        # Filter metadata keys against allowed_search_fields
        filtered_filter: dict[str, Any] = {}
        if filter_dict:
            for k, v in filter_dict.items():
                if not search_fields or k in search_fields:
                    filtered_filter[k] = v
                else:
                    logger.warning(f"Filter field '{k}' not in allowed search fields. Skipping.")

        tracer = trace.get_tracer("vectordb-mcp")
        with tracer.start_as_current_span(
            name="vectordb_search",
            attributes={
                SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.RETRIEVER.value,
                "db.system": "qdrant",
                "db.collection": target_collection,
                "search.type": search_type,
                "search.limit": limit,
            },
        ) as span:
            # Generate query embedding
            if search_type == VectorDBSearchType.IMAGE.value:
                image_bytes, mime = await _extract_image_bytes_and_mime(query_text)
                emb_res = await image_embed_client.embed_image(image_bytes, mime)
            else:
                emb_res = await embed_client.embed_text(query_text)

            query_vector = emb_res.embedding

            # Encapsulated collection check
            if not await db.collection_exists(target_collection):
                logger.warning(f"Collection '{target_collection}' does not exist.")
                return json.dumps([], indent=2)

            # Execute search
            hits = await db.search(
                collection_name=target_collection,
                query_vector=query_vector,
                limit=limit,
                filter_dict=filtered_filter if filtered_filter else None,
                query_text=query_text if search_type == VectorDBSearchType.HYBRID.value else None,
                search_type=search_type,
                allowed_answer_fields=answer_fields,
            )

            span.set_attribute(SpanAttributes.OUTPUT_VALUE, json.dumps(hits))
            return json.dumps(hits, indent=2)

    @mcp.tool(
        name="vectordb_store",
        description=(
            "Store text information and metadata into the vector database. "
            "Automatically generates dense embeddings and sparse vectors for hybrid retrieval."
        ),
    )
    async def vectordb_store(
        text: str,
        metadata: dict[str, Any] | None = None,
        id: str | int | None = None,
        collection_name: str | None = None,
    ) -> str:
        """Store text information into the vector database with dual-vector indexing.

        Args:
            text: The text content to store and embed.
            metadata: Optional dictionary of metadata attributes.
            id: Optional point ID. If omitted, a deterministic UUIDv5 is generated from content.
            collection_name: Optional custom collection name.
        """
        if not text or not text.strip():
            raise ValueError("Argument 'text' must not be empty.")

        target_collection = collection_name or default_coll

        # Generate dense embedding
        emb_res = await embed_client.embed_text(text)
        dense_vec = emb_res.embedding

        # Auto-create collection if needed using encapsulated check
        if not await db.collection_exists(target_collection):
            logger.info(f"Auto-creating collection '{target_collection}' (dim: {len(dense_vec)}).")
            await db.create_collection(
                collection_name=target_collection,
                vector_size=len(dense_vec),
            )

        # Determine point ID (deterministic UUIDv5 for idempotency if omitted)
        if id is not None:
            point_id = id
        else:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{target_collection}:{text}"))

        # Generate sparse vector for dual-vector indexing and hybrid search contract
        sparse_vec = generate_sparse_vector(text)
        indices = (
            getattr(sparse_vec, "indices", [])
            if hasattr(sparse_vec, "indices")
            else sparse_vec.get("indices", [])
        )
        values = (
            getattr(sparse_vec, "values", [])
            if hasattr(sparse_vec, "values")
            else sparse_vec.get("values", [])
        )

        payload = {
            "text": text,
            "sparse_indices": list(indices),
            "sparse_values": list(values),
            **(metadata or {}),
        }

        await db.insert(
            collection_name=target_collection,
            ids=[point_id],
            vectors=[dense_vec],
            payloads=[payload],
        )

        resp = VectorStoreResponse(
            id=str(point_id),
            status="success",
            collection=target_collection,
            dimensions=len(dense_vec),
        )

        return json.dumps(
            {
                "status": resp.status,
                "id": resp.id,
                "collection": resp.collection,
                "dimensions": resp.dimensions,
            },
            indent=2,
        )

    return mcp


# Module-level instances for ASGI entrypoints (e.g. Uvicorn)
mcp = create_vectordb_mcp_server()
app = mcp.sse_app()
