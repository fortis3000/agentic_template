# VectorDB MCP Server API Contracts & Tool Schemas

**Ticket**: [#87](https://github.com/fortis3000/agentic_template/issues/87)  
**Parent Map**: [#79](https://github.com/fortis3000/agentic_template/issues/79)  
**Date**: September 2026  

---

## 1. Overview

The VectorDB Model Context Protocol (MCP) server runs as an independent containerized microservice over HTTP/SSE. It exposes two high-level tools to agents:
1. `vectordb_search`: Multi-modal, hybrid, and dense vector similarity search.
2. `vectordb_store`: Idempotent document and episodic memory ingestion with dual-vector indexing.

---

## 2. Tool 1: `vectordb_search`

### Signature & JSON-RPC Schema
```python
async def vectordb_search(
    query_text: str,
    filter_dict: dict[str, Any] | None = None,
    search_type: str = "dense",
    limit: int = 5,
    collection_name: str | None = None,
) -> str:
    """Search the vector database for relevant information.

    Args:
        query_text: Text query or image data (file path or data:image/...;base64 string).
        filter_dict: Optional metadata payload key-value filters.
        search_type: Search modality: 'dense', 'hybrid' (dense+sparse RRF), or 'image'.
        limit: Maximum number of ranked results to return (1-100).
        collection_name: Optional collection override (defaults to server default).
    """
```

### Multimodal Input Handling
- When `search_type="dense"` or `"hybrid"`: `query_text` is treated as a natural language query string and embedded via the server's configured embedding model.
- When `search_type="image"`: `query_text` accepts either:
  - A local filesystem path (e.g. `/app/data/sample.png` or mounted volume path).
  - A Base64-encoded string or data URL (`data:image/png;base64,...`).
  The server automatically detects whether `query_text` represents a file path or base64 stream, extracts raw image bytes, and passes them to `embed_image()`.

### Return Value Contract
Returns a JSON-encoded array of ranked hit objects:
```json
[
  {
    "id": "a3b1c2d3-e4f5-5678-90ab-cdef12345678",
    "score": 0.892,
    "payload": {
      "text": "Retrieved passage text...",
      "source": "manual.pdf",
      "page": 12
    }
  }
]
```

---

## 3. Tool 2: `vectordb_store`

### Signature & JSON-RPC Schema
```python
async def vectordb_store(
    text: str,
    metadata: dict[str, Any] | None = None,
    id: str | int | None = None,
    collection_name: str | None = None,
) -> str:
    """Store text information and metadata into the vector database.

    Args:
        text: Text passage or episodic memory to embed and store.
        metadata: Optional dictionary of metadata attributes associated with the text.
        id: Optional point ID. If omitted, a deterministic UUIDv5 is generated from content.
        collection_name: Optional collection override.
    """
```

### Dual-Vector Indexing Behavior
1. Generates dense vector embedding for `text` using `EmbeddingModelFactory`.
2. Generates bag-of-words sparse vector using SHA256 hashed term frequencies (`generate_sparse_vector(text)`).
3. Constructs points with named vectors: `{"dense": dense_vector, "sparse": sparse_vector}`.
4. Stores point payload: `{"text": text, **(metadata or {})}`.

### Idempotent Point ID Generation
- If `id` is not provided, the server deterministically generates a UUIDv5:
  ```python
  point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{collection}:{text}"))
  ```
- Ensures multiple storage attempts of identical content update the existing point and metadata rather than creating duplicate vector records.

### Return Value Contract
Returns a JSON-encoded status confirmation:
```json
{
  "status": "success",
  "id": "a3b1c2d3-e4f5-5678-90ab-cdef12345678",
  "collection": "default_collection",
  "dimensions": 768
}
```

---

## 4. Error Handling & Observability

- **Error Contract**: Validation errors (`ValueError`) and operational errors (`RuntimeError`) are raised within tool handlers. FastMCP catches them, returns `CallToolResult(isError=True, content=[TextContent(text="Error details")])`.
- **Client Recovery**: `McpConnectionManager` records `tool.is_error = True` on the active OpenTelemetry span and provides structured self-healing prompt diagnostics to the LLM agent when `raise_on_error: false`.
- **Arize Phoenix Tracing**: All vector database searches inside the microservice emit OpenInference `RETRIEVER` spans to `PHOENIX_COLLECTOR_ENDPOINT`.
