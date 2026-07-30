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
