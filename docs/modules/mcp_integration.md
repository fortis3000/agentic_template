# Model Context Protocol (MCP) Subsystem (`src/tools/mcp/`)

> [!NOTE]
> As part of the Unified Tool Architecture (ADR 6), MCP integrations are organized under `src/tools/mcp/` and managed centrally by `ToolManager` (`src/tools/manager.py`).

---

## 1. Overview & Architecture

The MCP module enables seamless client/server communication between the agent engine and third-party MCP servers (e.g., git, context7, filesystem, developer knowledge servers).

Key files:
- `src/tools/mcp/client.py`: MCP client wrapper (`McpServerFactory`, `McpToolDefinition`, `make_mcp_tool_callable`).
- `src/tools/mcp/manager.py`: Session connection pool manager (`McpConnectionManager`).
- `src/tools/mcp/server.py`: Stdio and HTTP/SSE parameter parsers.
- `src/tools/manager.py`: Unified `ToolManager` integrating MCP tools with agent configurations.

---

## 2. MCP Session Manager (`McpConnectionManager`)

`McpConnectionManager` maintains persistent client sessions to prevent subprocess spawning overhead on every tool invocation:

- `get_session(config: McpServerConfig) -> ClientSession`: Retrieves or initializes a cached MCP client session.
- `close_all()`: Gracefully closes all open subprocesses and stdio streams during application shutdown.

---

## 3. Tool Discovery & Conversion

1. **Discovery**: `McpServerFactory.fetch_tools(config)` (async) and `fetch_tools_sync(config)` connect to the specified MCP server and query available tool definitions.
2. **Framework-Neutral Descriptors**: Encapsulates remote tool metadata and executable callables into `McpToolDefinition` objects, which agent SDK generators (e.g., Pydantic AI `Tool.from_schema`) adapt for runtime invocation.
3. **Execution Interception**: Tool calls invoked by the model are forwarded through `session.call_tool(name, arguments)` and returned to the agent context with automatic OpenTelemetry tracing and retries.
