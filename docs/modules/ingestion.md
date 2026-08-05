# Ingestion Pipeline Subsystem (`src/ingestion/`)

This document provides explicit documentation for the Document Ingestion Engine, covering text chunking strategies, metadata extraction, and vector database pipeline orchestration.

---

## 1. Overview & Ingestion Flow

The ingestion pipeline converts raw unstructured documents (PDF, Markdown, HTML, TXT) into chunked, embedded vector representations indexed inside Qdrant.

Key files:
- [`src/ingestion/chunkers.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/ingestion/chunkers.py): Text chunking algorithms.
- [`src/ingestion/helper.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/ingestion/helper.py): Document metadata extraction and payload formatting.
- [`src/ingestion/pipeline.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/ingestion/pipeline.py): Pipeline execution orchestrator.

---

## 2. Text Chunking Strategies (`src/ingestion/chunkers.py`)

### 2.1 Fixed-Size Chunker (`fixed_chunker`)
Splits text into chunks of `chunk_size` characters with `chunk_overlap` overlap. Respects paragraph (`\n\n`), newline (`\n`), and sentence (`.`) breaks within the overlap window to avoid splitting mid-sentence.

```python
def fixed_chunker(text: str, chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]
```

### 2.2 Markdown Chunker (`markdown_chunker`)
Splits text along Markdown header boundaries (`#`, `##`, `###`). If an individual header section exceeds `max_chunk_size`, it recursively applies `fixed_chunker`.

```python
def markdown_chunker(text: str, max_chunk_size: int = 500, chunk_overlap: int = 50) -> list[str]
```

### 2.3 Semantic Chunker (`semantic_chunker`)
Splits text into sentences, calculates cosine distance between adjacent sentence embeddings using an `EmbeddingClient`, and groups sentences until distance exceeds `semantic_threshold` or size limits.

```python
async def semantic_chunker(
    text: str,
    embedding_client: Any,
    semantic_threshold: float = 0.5,
    max_chunk_size: int = 500,
    chunk_overlap: int = 50,
) -> list[str]
```

---

## 3. Ingestion Pipeline Execution (`src/ingestion/pipeline.py`)

The pipeline runs the end-to-end ingestion workflow:

1. **Document Loading**: Reads file content via `TextExtractor`.
2. **Chunking**: Selects and executes chunker based on configuration (`fixed`, `markdown`, or `semantic`).
3. **Embedding Generation**: Generates dense vector embeddings via `EmbeddingModelFactory`.
4. **Vector DB Upsert**: Indexes vector embeddings and metadata payloads into specified Qdrant collections.
