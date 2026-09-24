# Research Evaluation: qdrant/mcp-server-qdrant vs Custom FastMCP Architecture

**Ticket**: [#86](https://github.com/fortis3000/agentic_template/issues/86)  
**Parent Map**: [#79](https://github.com/fortis3000/agentic_template/issues/79)  
**Date**: September 2026  

---

## Executive Summary & Decision

We evaluated the official upstream repository [qdrant/mcp-server-qdrant](https://github.com/qdrant/mcp-server-qdrant) against our template's vector search architecture (`src/tools/local/vectordb_search.py`, `src/tools/local/qdrant_db.py`, `src/agents/embeddings.py`) and MCP client subsystem (`src/tools/mcp/`).

**Decision: Reject direct deployment of `qdrant/mcp-server-qdrant`. Instead, build an in-house custom FastMCP/ASGI container wrapping our existing `QdrantVectorDB` and `EmbeddingModelFactory`.**

### Key Rationale
1. **Embedding Disconnect**: Upstream forces CPU-bound `fastembed` (`sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions). Our template uses Gemini API embeddings (`text-embedding-004`, 768 dims) or Ollama. Upstream cannot query collections ingested via our embedding pipeline.
2. **Missing Multimodal & Hybrid Retrieval**: Upstream only supports plain text query/store. Our architecture requires multimodal image vector search, sparse bag-of-words vectors, and Reciprocal Rank Fusion (`FusionQuery(fusion=Fusion.RRF)`).
3. **Missing OpenTelemetry / Arize Phoenix Telemetry**: Upstream lacks tracing instrumentation. Wrapping `QdrantVectorDB` ensures every search emits standard OpenInference `RETRIEVER` spans to Phoenix.
4. **Clean Decoupling with FastMCP**: FastMCP provides high-level tool decorators (`@mcp.tool`) and ASGI/SSE serving capabilities that allow us to implement an in-house service with minimal boilerplate while keeping full parity with our local tools.

---

## 1. Upstream Architecture (`qdrant/mcp-server-qdrant`)

- **Core Primitives**:
  - `qdrant-store`: Takes `information: str`, optional `metadata: dict`, `collection_name: str | None`. Embeds text via FastEmbed and upserts.
  - `qdrant-find`: Takes `query: str`, `collection_name: str | None`. Performs nearest-neighbor search.
- **Transports**:
  - Stdio (for local desktop CLI clients).
  - SSE/HTTP (via Starlette/Uvicorn ASGI runner on `FASTMCP_SERVER_HOST` / `FASTMCP_SERVER_PORT`).
- **Reusable Patterns**:
  - Pydantic `BaseSettings` modularization (`QdrantSettings`, `EmbeddingProviderSettings`, `ToolSettings`).
  - Configurable tool docstrings via environment variables (`TOOL_STORE_DESCRIPTION`, `TOOL_FIND_DESCRIPTION`).

---

## 2. In-House Containerized FastMCP Architecture

### Container Service Setup
A dedicated service in `docker-compose.yml`:
```yaml
  vectordb-mcp:
    build:
      context: .
      dockerfile: docker/Dockerfile.vectordb_mcp
    ports:
      - "8001:8000"
    environment:
      - QDRANT_HOST=qdrant
      - QDRANT_PORT=6333
      - PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006/v1/traces
      - GEMINI_API_KEY=${GEMINI_API_KEY:-}
    depends_on:
      - qdrant
      - phoenix
```

### Microservice Tool Definition
Leveraging FastMCP with our existing `QdrantVectorDB`:
```python
# src/mcp_servers/vectordb/server.py
from fastmcp import FastMCP
from src.tools.local.qdrant_db import QdrantVectorDB
from src.agents.embeddings import EmbeddingModelFactory

mcp = FastMCP("VectorDB MCP Server")

@mcp.tool(description="Search vector database supporting dense text, hybrid, and image retrieval.")
async def vectordb_search(query_text: str, filter_dict: dict | None = None, search_type: str = "dense", limit: int = 5) -> str:
    ...

@mcp.tool(description="Store information and metadata into vector database.")
async def vectordb_store(text: str, metadata: dict | None = None, collection_name: str | None = None) -> str:
    ...
```

### Agent Client Integration
The `agent-api` backend connects via `McpConnectionManager` using Pydantic's `httpx2` client to `http://vectordb-mcp:8000/sse`.

---

## Primary Sources
- Qdrant Team, *`qdrant/mcp-server-qdrant` Repository*, [GitHub](https://github.com/qdrant/mcp-server-qdrant).
- Model Context Protocol Python SDK & FastMCP Documentation, [Model Context Protocol](https://modelcontextprotocol.io).

