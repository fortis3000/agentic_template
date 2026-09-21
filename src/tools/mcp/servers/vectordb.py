"""VectorDB Model Context Protocol (MCP) Server implementation.

Provides a containerized or standalone FastMCP service exposing vector similarity search
and document/episodic memory ingestion over HTTP/SSE.
"""

import base64
import json
import os
import re
import uuid
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.agents.config import EmbeddingModelConfigSchema, VectorDBConfigSchema
from src.agents.embeddings import BaseEmbeddingClient, EmbeddingModelFactory
from src.tools.local.qdrant_db import QdrantVectorDB
from src.utils.logger import get_logger

logger = get_logger(__name__)


MIN_DECODED_IMAGE_BYTES = 10


def _extract_image_bytes_and_mime(image_input: str) -> tuple[bytes, str]:
    """Parse image input which may be a data URL, raw base64, or local file path."""
    # 1. Check for data URL: data:image/<type>;base64,<data>
    data_url_match = re.match(
        r"^data:(image\/[a-zA-Z0-9\-\+\.]+);base64,(.+)$", image_input, re.DOTALL
    )
    if data_url_match:
        mime = data_url_match.group(1)
        raw_b64 = data_url_match.group(2)
        try:
            return base64.b64decode(raw_b64), mime
        except Exception as e:
            raise ValueError(f"Failed to decode base64 image data URL: {e}") from e

    # 2. Check for local file path
    if os.path.exists(image_input) and os.path.isfile(image_input):
        ext = os.path.splitext(image_input)[1].lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        mime = mime_map.get(ext, "image/png")
        with open(image_input, "rb") as f:
            return f.read(), mime

    # 3. Try decoding raw base64 string directly
    try:
        decoded = base64.b64decode(image_input, validate=True)
        if len(decoded) > MIN_DECODED_IMAGE_BYTES:
            return decoded, "image/png"
    except Exception:  # nosec B110
        pass

    raise ValueError(
        f"Invalid image input: '{image_input[:100]}...' is neither an existing file path "
        "nor a valid Base64 data URL."
    )


def create_vectordb_mcp_server(  # noqa: PLR0915
    db: QdrantVectorDB | None = None,
    embed_client: BaseEmbeddingClient | None = None,
    default_collection: str | None = None,
    allowed_search_fields: list[str] | None = None,
    allowed_answer_fields: list[str] | None = None,
) -> FastMCP:
    """Factory creating and configuring the VectorDB FastMCP server."""
    # Resolve collection name
    default_coll = (
        default_collection or os.getenv("DEFAULT_COLLECTION_NAME") or "default_collection"
    )

    # Resolve allowed fields
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

    # Initialize Embedding Client if not supplied
    if embed_client is None:
        emb_provider = os.getenv("EMBEDDING_PROVIDER", "google")
        emb_model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")
        emb_dims = int(os.getenv("EMBEDDING_DIMENSIONS", "3072"))
        emb_img_dims = int(os.getenv("EMBEDDING_IMAGE_DIMENSIONS", str(emb_dims)))

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

    # Initialize Qdrant Client if not supplied
    if db is None:
        db_cfg = VectorDBConfigSchema(
            type="qdrant",
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
            url=os.getenv("QDRANT_URL"),
            location=os.getenv("QDRANT_LOCATION"),
        )
        db_params = db_cfg.model_dump(exclude={"type"}, exclude_none=True)
        db = QdrantVectorDB(**db_params)

    mcp = FastMCP("VectorDB MCP Server")

    # Custom healthcheck endpoint for Docker / orchestration
    @mcp.custom_route("/healthz", methods=["GET"])
    async def healthz(request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "service": "vectordb-mcp"})

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

        # Validate search_type
        if search_type not in {"dense", "hybrid", "image"}:
            raise ValueError(
                f"Invalid search_type '{search_type}'. Allowed values: 'dense', 'hybrid', 'image'."
            )

        # Filter metadata keys against allowed_search_fields
        filtered_filter: dict[str, Any] = {}
        if filter_dict:
            for k, v in filter_dict.items():
                if not search_fields or k in search_fields:
                    filtered_filter[k] = v
                else:
                    logger.warning(f"Filter field '{k}' not in allowed search fields. Skipping.")

        # Generate query embedding
        if search_type == "image":
            image_bytes, mime = _extract_image_bytes_and_mime(query_text)
            emb_res = await embed_client.embed_image(image_bytes, mime)
        else:
            emb_res = await embed_client.embed_text(query_text)

        query_vector = emb_res.embedding

        # Verify collection existence if possible
        if hasattr(db.client, "collection_exists"):
            try:
                if not await db.client.collection_exists(target_collection):
                    logger.warning(f"Collection '{target_collection}' does not exist in Qdrant.")
                    return json.dumps([], indent=2)
            except Exception as e:
                logger.debug(f"Collection existence check failed: {e}")

        # Execute search
        hits = await db.search(
            collection_name=target_collection,
            query_vector=query_vector,
            limit=limit,
            filter_dict=filtered_filter if filtered_filter else None,
            query_text=query_text if search_type == "hybrid" else None,
            search_type=search_type,
            allowed_answer_fields=answer_fields,
        )

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
        """Store text information into the vector database.

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

        # Auto-create collection if needed
        if hasattr(db.client, "collection_exists"):
            try:
                exists = await db.client.collection_exists(target_collection)
                if not exists:
                    logger.info(
                        f"Auto-creating collection '{target_collection}' (dim: {len(dense_vec)})."
                    )
                    await db.create_collection(
                        collection_name=target_collection,
                        vector_size=len(dense_vec),
                    )
            except Exception as e:
                logger.warning(f"Collection check or creation failed: {e}")

        # Determine point ID (deterministic UUIDv5 for idempotency if omitted)
        if id is not None:
            point_id = id
        else:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{target_collection}:{text}"))

        payload = {"text": text, **(metadata or {})}

        await db.insert(
            collection_name=target_collection,
            ids=[point_id],
            vectors=[dense_vec],
            payloads=[payload],
        )

        return json.dumps(
            {
                "status": "success",
                "id": str(point_id),
                "collection": target_collection,
                "dimensions": len(dense_vec),
            },
            indent=2,
        )

    return mcp


# Module-level instances for ASGI entrypoints (e.g. Uvicorn)
mcp = create_vectordb_mcp_server()
app = mcp.sse_app()
