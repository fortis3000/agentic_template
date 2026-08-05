# Model Context Protocol (MCP) Subsystem (`src/mcp_integration/`)

This document provides technical specifications for the Model Context Protocol (MCP) integration layer, allowing agents to dynamically discover and execute tools hosted on external MCP stdio or SSE servers.

---

## 1. Overview & Architecture

The MCP module enables seamless client/server communication between the agent engine and third-party MCP servers (e.g., git, context7, filesystem, developer knowledge servers).

Key files:
- [`src/mcp_integration/client.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/mcp_integration/client.py): MCP Stdio client wrapper.
- [`src/mcp_integration/manager.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/mcp_integration/manager.py): Session connection pool manager (`McpConnectionManager`).
- [`src/mcp_integration/server.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/mcp_integration/server.py): McpServerFactory and tool schema converter.

---

## 2. MCP Session Manager (`McpConnectionManager`)

`McpConnectionManager` maintains persistent client sessions to prevent subprocess spawning overhead on every tool invocation:

- `get_session(config: McpServerConfig) -> ClientSession`: Retrieves or initializes a cached MCP client session.
- `close_all()`: Gracefully closes all open subprocesses and stdio streams during application shutdown.

---

## 3. Tool Discovery & Conversion

1. **Discovery**: `McpServerFactory.fetch_tools_sync(config)` connects to the specified MCP server command and queries available tool definitions.
2. **Schema Conversion**: Converts MCP tool JSON schemas into Pydantic / Python callable signatures compatible with `PydanticAIAgent` and `AntigravityAgent`.
3. **Execution Interception**: Tool calls invoked by the model are forwarded through `session.call_tool(name, arguments)` and returned to the agent context.
