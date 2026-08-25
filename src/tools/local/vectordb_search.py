import json
import os
from typing import Any, Callable

from src.agents.config import EmbeddingModelConfigSchema, VectorDBConfigSchema
from src.agents.embeddings import EmbeddingModelFactory
from src.utils.logger import get_logger

# Relative: this module registers itself below — see the note in src/tools/local/qdrant_db.py.
from .base import BaseTool, ToolFactory
from .qdrant_db import QdrantVectorDB

logger = get_logger(__name__)


@ToolFactory.register("vectordb_search")
class VectorDBSearchTool(BaseTool):
    """Tool to search a Qdrant vector database."""

    def __init__(
        self,
        collection_name: str,
        embedding_model: EmbeddingModelConfigSchema | dict[str, Any],
        vectordb: VectorDBConfigSchema | dict[str, Any],
        allowed_search_fields: list[str] | None = None,
        allowed_answer_fields: list[str] | None = None,
    ):
        self.collection_name = collection_name
        self.allowed_search_fields = allowed_search_fields or []
        self.allowed_answer_fields = allowed_answer_fields or []

        # Instantiate embedding client
        emb_cfg = (
            embedding_model
            if isinstance(embedding_model, EmbeddingModelConfigSchema)
            else EmbeddingModelConfigSchema.model_validate(embedding_model)
        )
        self.embed_client = EmbeddingModelFactory.create(emb_cfg)

        # Instantiate Qdrant client
        db_cfg = (
            vectordb
            if isinstance(vectordb, VectorDBConfigSchema)
            else VectorDBConfigSchema.model_validate(vectordb)
        )
        if db_cfg.type != "qdrant":
            raise ValueError(
                f"VectorDBSearchTool only supports Qdrant Vector DB, got {db_cfg.type}"
            )

        db_params = db_cfg.model_dump(exclude={"type"}, exclude_none=True)
        self.db = QdrantVectorDB(**db_params)

    def get_callable(self) -> Callable:
        async def search_vectordb(
            query_text: str,
            filter_dict: dict[str, Any] | None = None,
            search_type: str = "dense",
            limit: int = 5,
            collection_name: str | None = None,
        ) -> str:
            """Search the document vector database for relevant information.

            Args:
                query_text: The search query text or local path to query image.
                filter_dict: Optional metadata filters. Keys must be inside the defined search fields.
                search_type: The search type (either 'dense', 'image', or 'hybrid').
                limit: The maximum number of results to return.
                collection_name: Optional custom collection name to search.
            """
            # Filter filter_dict to only allowed_search_fields
            filtered_filter = {}
            if filter_dict:
                for k, v in filter_dict.items():
                    if not self.allowed_search_fields or k in self.allowed_search_fields:
                        filtered_filter[k] = v
                    else:
                        logger.warning(
                            f"Filter field '{k}' not in allowed_search_fields. Skipping."
                        )

            # Generate query embedding
            if search_type == "image":
                if not os.path.exists(query_text):
                    raise ValueError(
                        f"Image search requires a valid local path to query image, but '{query_text}' does not exist."
                    )
                with open(query_text, "rb") as f:
                    image_bytes = f.read()
                ext = os.path.splitext(query_text)[1].lower()
                mime = "image/png"
                if ext in (".jpg", ".jpeg"):
                    mime = "image/jpeg"
                elif ext == ".gif":
                    mime = "image/gif"
                emb_res = await self.embed_client.embed_image(image_bytes, mime)
            else:
                emb_res = await self.embed_client.embed_text(query_text)

            query_vector = emb_res.embedding

            target_collection = self.collection_name
            if collection_name:
                try:
                    if await self.db.client.collection_exists(collection_name):
                        target_collection = collection_name
                except Exception as e:
                    logger.debug(f"Collection check for '{collection_name}' failed: {e}")

            # Execute search
            hits = await self.db.search(
                collection_name=target_collection,
                query_vector=query_vector,
                limit=limit,
                filter_dict=filtered_filter,
                query_text=query_text,
                search_type=search_type,
                allowed_answer_fields=self.allowed_answer_fields,
            )

            return json.dumps(hits, indent=2)

        return search_vectordb
