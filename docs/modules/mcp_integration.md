# Model Context Protocol (MCP) Subsystem (`src/tools/mcp/`)

> [!NOTE]
> As part of the Unified Tool Architecture (ADR 6), MCP integrations are organized under `src/tools/mcp/` with leaf contracts in `src/tools/contracts/` and managed centrally by `ToolManager` (`src/tools/manager.py`).

---

## 1. Overview & Architecture

The MCP subsystem enables agents to interact with external Model Context Protocol servers running over local stdio subprocesses or remote HTTP/SSE endpoints. It provides parallel discovery, persistent session caching, tool namespacing, resilient error handling, and multimodal content extraction.

Key modules:
- `src/tools/contracts/mcp.py`: Zero-dependency leaf contract defining `McpToolDefinition` (`name`, `callable`, `description`, `input_schema`, `original_name`).
- `src/tools/mcp/client.py`: MCP client interface (`McpServerFactory`, `make_mcp_tool_callable`, metadata caching).
- `src/tools/mcp/manager.py`: Persistent session connection pool (`McpConnectionManager`).
- `src/tools/mcp/server.py`: Configuration schemas (`McpServerConfigSchema`) and parameter parsers for stdio and HTTP/SSE transports.
- `src/tools/manager.py`: Central `ToolManager` unifying local tools and external MCP discovery into a single facade.

---

## 2. MCP Session Manager (`McpConnectionManager`)

`McpConnectionManager` maintains persistent client sessions across invocations, eliminating subprocess recreation latency:

- **Session Caching**: `get_session(config: McpServerConfigSchema) -> ClientSession` retrieves or initializes a cached `ClientSession` guarded by `asyncio.Lock`.
- **Concurrency & Re-use**: Multiple tool executions reuse active sessions without AnyIO cancel-scope affinity errors.
- **Teardown**: `close_all()` gracefully terminates all open client sessions, subprocesses, and background reader tasks during application shutdown.

### 2.1 HTTP/SSE Transport & `httpx2` Convention
All remote HTTP/SSE connections in the MCP subsystem are standardized on `httpx2` (`httpcore2`):
- `create_mcp_http_client` configures `httpx2.AsyncClient(follow_redirects=True)`.
- When upstream `mcp.client.sse` passes external `httpx.Timeout` instances, `create_mcp_http_client` automatically adapts them into native `httpx2.Timeout` structures to prevent AnyIO timing errors.
- Application code across the repository must strictly use `httpx2` directly (`import httpx2`) and avoid importing `httpx`.

---

## 3. Tool Discovery, Caching & Namespacing

### 3.1 Parallel Tool Discovery
`McpServerFactory.fetch_tools(config)` queries available tool definitions from a configured server. In `ToolManager.resolve_tools`, multiple configured MCP servers are queried concurrently via `asyncio.gather`, dramatically reducing agent initialization time.

### 3.2 Metadata Caching
Discovered tool metadata is cached in-memory by server configuration key to avoid repetitive JSON-RPC schema roundtrips during dynamic agent instantiations.

### 3.3 Tool Name Prefixing (`tool_prefix`)
Configuring `tool_prefix` on an MCP server (e.g. `tool_prefix: "github"`) automatically namespaces advertised tool names (e.g. `github_search_issues`), preventing collisions when combining multiple servers that expose identical tool names. The raw upstream name is preserved in `McpToolDefinition.original_name` for remote RPC invocation.

---

## 4. Resilience & Multimodal Extraction

### 4.1 Server Error Handling (`CallToolResult.isError`)
`make_mcp_tool_callable` inspects `result.isError` returned by remote MCP servers:
- **Telemetry**: Records `StatusCode.ERROR` and sets `tool.is_error = True` on the active OpenTelemetry span.
- **Self-Healing LLM Prompting**: When `raise_on_error: false` (default), formats error messages into structured diagnostics (`MCP Tool Error: ...`), allowing models to self-correct arguments or recover.
- **Fail-Fast Policy**: When `raise_on_error: true` is configured in `tool_settings`, immediately raises `RuntimeError`.

### 4.2 Multimodal Content Extraction
When an MCP tool response contains `ImageContent` blocks, the client extracts base64 data and MIME types into structured dictionaries. Agent backends (such as `PydanticAIAgentGenerator`) automatically map these dictionaries to native `BinaryContent` parts for multimodal models.

### 4.3 Native Pydantic AI Toolsets (`native_pydantic_toolset`)
When `native_pydantic_toolset: true` is set in the server configuration, `PydanticAIAgentGenerator` bypasses generic wrapping and mounts a native `pydantic_ai.mcp.MCPToolset` directly, providing access to MCP sampling and deferred tool loading.

---

## 5. FastMCP Server Microservices (`src/tools/mcp/servers/`)

In addition to consuming external MCP servers, the repository provides first-party, containerized MCP servers built with `FastMCP`:

- **VectorDB MCP Server (`src/tools/mcp/servers/vectordb.py`)**:
  - Exposes `vectordb_search` (dense, hybrid sparse, multimodal image search) and `vectordb_store` (dual-vector indexing with deterministic UUIDv5 hashing).
  - Employs self-contained embedding models (`EmbeddingModelFactory`) to decouple agents from embedding models.
  - Serves as a Starlette ASGI app over HTTP/SSE via `uvicorn src.tools.mcp.servers.vectordb:app --host 0.0.0.0 --port 8000`.
  - Integrates `/healthz` health checking and Arize Phoenix retriever spans.
  - For configuration and run guides, see [VectorDB MCP Microservice Guide](../guides/vectordb_mcp_service.md).

