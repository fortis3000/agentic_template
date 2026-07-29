import uuid
from typing import Any

from src.ingestion.chunkers import fixed_chunker, markdown_chunker, semantic_chunker
from src.tools.text_extractor import extract_text
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def ingest_document(
    filepath: str,
    file_bytes: bytes,
    mime_type: str,
    config: Any,
    vectordb: Any,
    embed_client: Any,
) -> list[str]:
    """Extracts, chunks, embeds, and uploads a single file to the vector database.

    Returns the list of generated chunk IDs.
    """
    # 1. Extract text from bytes
    text = extract_text(file_bytes, mime_type)
    if not text:
        logger.warning(f"No text extracted from {filepath}.")
        return []

    # 2. Chunk text based on config strategy
    strategy = getattr(config, "chunking_strategy", "fixed")
    size = getattr(config, "chunk_size", 500)
    overlap = getattr(config, "chunk_overlap", 50)
    threshold = getattr(config, "semantic_threshold", 0.5)

    if strategy == "markdown":
        chunks = markdown_chunker(text, max_chunk_size=size, chunk_overlap=overlap)
    elif strategy == "semantic":
        chunks = await semantic_chunker(
            text,
            embedding_client=embed_client,
            semantic_threshold=threshold,
            max_chunk_size=size,
            chunk_overlap=overlap,
        )
    else:
        chunks = fixed_chunker(text, chunk_size=size, chunk_overlap=overlap)

    if not chunks:
        return []

    # 3. Batch embed the chunks
    batch_res = await embed_client.embed_batch(chunks)
    vectors = batch_res.embeddings

    # 4. Generate unique deterministic chunk IDs (UUIDv5)
    namespace = uuid.UUID("37000000-0000-0000-0000-000000000037")
    chunk_ids = [str(uuid.uuid5(namespace, f"{filepath}_{idx}")) for idx in range(len(chunks))]

    payloads = [
        {"text": chunk, "filepath": filepath, "chunk_index": idx}
        for idx, chunk in enumerate(chunks)
    ]

    # 5. Insert into Vector DB
    collection_name = getattr(config, "collection_name", "default_collection")
    await vectordb.insert(
        collection_name,
        ids=chunk_ids,
        vectors=vectors,
        payloads=payloads,
    )

    logger.info(
        f"Ingested {len(chunks)} chunks for '{filepath}' into collection '{collection_name}'."
    )
    return chunk_ids


async def prepare_and_enqueue_ingestion(
    file_contexts: list[dict[str, Any]],
    agent_cfg: Any,
    ingestion_queue: Any,
    workspace_root: Any,
) -> None:
    """Configures vector database client, initializes the collection and enqueues files for background ingestion."""
    from pathlib import Path  # noqa: PLC0415

    import yaml  # noqa: PLC0415

    from src.agents.config import EmbeddingModelConfigSchema  # noqa: PLC0415
    from src.agents.embeddings import EmbeddingModelFactory  # noqa: PLC0415
    from src.tools.vectordb_base import VectorDBFactory  # noqa: PLC0415

    # Load tools_config.yaml to get vectordb_search settings
    tools_cfg = {}
    tools_config_path = Path(workspace_root) / "configs" / "tools_config.yaml"
    if tools_config_path.exists():
        try:
            with open(tools_config_path, "r", encoding="utf-8") as f:
                tools_data = yaml.safe_load(f) or {}
                tools_cfg = tools_data.get("tools", {}).get("search_vectordb", {}).get("config", {})
        except Exception as e:
            logger.error(f"Failed to load tools config for ingestion: {e}")

    collection_name = tools_cfg.get("collection_name", "default_collection")
    vectordb_cfg = tools_cfg.get("vectordb", {"type": "qdrant", "location": ":memory:"})
    embedding_cfg = tools_cfg.get("embedding_model")

    target_coll = collection_name

    class SimpleIngestConfig:
        collection_name: str = target_coll
        chunking_strategy: str = "fixed"
        chunk_size: int = 500
        chunk_overlap: int = 50
        semantic_threshold: float = 0.5

    if embedding_cfg:
        emb_schema = EmbeddingModelConfigSchema.model_validate(embedding_cfg)
        embed_client = EmbeddingModelFactory.create(emb_schema)
        dimensions = emb_schema.dimensions or 768
    else:
        embed_client = EmbeddingModelFactory.create(agent_cfg.embedding_model)
        dimensions = agent_cfg.embedding_model.dimensions or 768

    db_type = vectordb_cfg.get("type", "qdrant")
    db_params = {k: v for k, v in vectordb_cfg.items() if k != "type"}
    vectordb = VectorDBFactory.create(db_type, **db_params)

    await vectordb.create_collection(
        SimpleIngestConfig.collection_name,
        dimensions,
    )

    for ctx in file_contexts:
        f_path = Path(ctx["path"])
        if f_path.exists():
            f_bytes = f_path.read_bytes()
            await ingestion_queue.put(
                {
                    "filepath": ctx["path"],
                    "file_bytes": f_bytes,
                    "mime_type": ctx["mime_type"],
                    "config": SimpleIngestConfig,
                    "vectordb": vectordb,
                    "embed_client": embed_client,
                }
            )
