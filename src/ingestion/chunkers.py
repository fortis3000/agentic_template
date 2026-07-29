import math
import re
from typing import Any

from src.utils.logger import get_logger

logger = get_logger(__name__)


def dot_product(u: list[float], v: list[float]) -> float:
    return sum(a * b for a, b in zip(u, v))


def norm(u: list[float]) -> float:
    return math.sqrt(sum(a * a for a in u))


def cosine_distance(u: list[float], v: list[float]) -> float:
    nu = norm(u)
    nv = norm(v)
    if nu == 0.0 or nv == 0.0:
        return 1.0
    similarity = dot_product(u, v) / (nu * nv)
    return 1.0 - similarity


def fixed_chunker(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """Split text into chunks of chunk_size characters with chunk_overlap overlap.

    Respects paragraph/sentence boundaries where possible.
    """
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:].strip())
            break

        # Search for separators in the overlap window
        search_range = text[max(start, end - chunk_overlap) : end]
        break_point = -1
        for sep in ("\n\n", "\n", ". ", " "):
            idx = search_range.rfind(sep)
            if idx != -1:
                break_point = max(start, end - chunk_overlap) + idx + len(sep)
                break

        if break_point != -1 and break_point > start:
            chunks.append(text[start:break_point].strip())
            start = break_point
        else:
            chunks.append(text[start:end].strip())
            start = end - chunk_overlap

    return [c for c in chunks if c]


def markdown_chunker(text: str, max_chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]:
    """Splits text along Markdown header boundaries, falling back to fixed chunker if sections are too large."""
    if not text:
        return []

    lines = text.split("\n")
    sections = []
    current_section = []

    for line in lines:
        if line.strip().startswith(("# ", "## ", "### ", "#### ", "##### ", "###### ")):
            if current_section:
                sections.append("\n".join(current_section).strip())
                current_section = []
        current_section.append(line)

    if current_section:
        sections.append("\n".join(current_section).strip())

    chunks = []
    for sec in sections:
        if len(sec) <= max_chunk_size:
            chunks.append(sec)
        else:
            sub_chunks = fixed_chunker(sec, max_chunk_size, chunk_overlap)
            chunks.extend(sub_chunks)

    return [c for c in chunks if c]


async def semantic_chunker(
    text: str,
    embedding_client: Any,
    semantic_threshold: float = 0.5,
    max_chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]:
    """Splits text into sentences, calculates cosine distance between adjacent sentences, and groups them."""
    if not text:
        return []

    # Split text into sentences using simple lookbehind pattern
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        return []
    if len(sentences) == 1:
        # Safeguard size
        if len(sentences[0]) > max_chunk_size:
            return fixed_chunker(sentences[0], max_chunk_size, chunk_overlap)
        return sentences

    # Generate embeddings in batch
    try:
        batch_resp = await embedding_client.embed_batch(sentences)
        embeddings = batch_resp.embeddings
    except Exception as e:
        logger.warning(
            f"Semantic chunking embedding generation failed: {e}. Falling back to fixed chunking."
        )
        return fixed_chunker(text, max_chunk_size, chunk_overlap)

    chunks = []
    current_sentences = [sentences[0]]

    for i in range(1, len(sentences)):
        dist = cosine_distance(embeddings[i - 1], embeddings[i])
        temp_chunk = " ".join(current_sentences)

        if dist > semantic_threshold or len(temp_chunk) + len(sentences[i]) + 1 > max_chunk_size:
            chunks.append(temp_chunk.strip())
            current_sentences = [sentences[i]]
        else:
            current_sentences.append(sentences[i])

    if current_sentences:
        chunks.append(" ".join(current_sentences).strip())

    # Safeguard all chunks against size constraints
    final_chunks = []
    for c in chunks:
        if len(c) <= max_chunk_size:
            final_chunks.append(c)
        else:
            final_chunks.extend(fixed_chunker(c, max_chunk_size, chunk_overlap))

    return [c for c in final_chunks if c]
