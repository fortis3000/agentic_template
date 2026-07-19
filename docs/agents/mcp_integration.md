# Model Context Protocol (MCP) Integration Guide

This guide describes how the Model Context Protocol (MCP) is integrated into standard agents within the repository.

---

## 1. Overview & Setup

The Model Context Protocol (MCP) allows agents to connect to external servers (either over local standard input/output subprocesses or remote HTTP SSE connections) to fetch dynamic tool schemas and execute them.

```yaml
agent:
  name: "mcp_enabled_agent"
  mcp_servers:
    filesystem:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/workspace"]
      enabled_tools:
        - "read_file"
      disabled_tools:
        - "write_file"
```

### Whitelisting & Filtering Rules
* **`enabled_tools`**: If specified, only tool names matching this list are exposed to the agent.
* **`disabled_tools`**: If specified, tool names matching this list are filtered out and hidden from the agent.

---

## 2. Persistent Connection Caching

To prevent spawning expensive subprocesses on every tool call, we manage connection sessions via `McpConnectionManager`.
* **Caching**: Sessions (`ClientSession`) are cached by a unique configuration key.
* **Concurrency**: Connection creation is synchronized via `asyncio.Lock`.
* **Lifespan Clean-up**: All active sessions are terminated on application shutdown by calling `McpConnectionManager.close_all()` in the FastAPI lifespan.

---

## 3. Tool Resolution Sequence Flow

The sequence diagram below details how MCP servers are resolved, wrapped, and executed with granular retry policies:

```mermaid
sequenceDiagram
    autonumber
    actor Consumer as Consumer App / Agent
    participant Gen as Agent Generator (PydanticAI / Antigravity)
    participant Factory as McpServerFactory
    participant Cache as McpConnectionManager
    participant Subprocess as MCP Subprocess (Stdio/SSE)

    Gen->>Factory: fetch_tools_sync(config)
    Note over Factory: Spawns ThreadPoolExecutor & fresh event loop
    Factory->>Subprocess: Launch subprocess / HTTP session
    Subprocess-->>Factory: Returns all tool schemas
    Factory-->>Gen: Returns filtered list of tools (e.g. read_file)
    
    loop For each resolved MCP tool
        Gen->>Gen: Wrap tool with wrap_tool_with_retry(tool_settings)
        Gen->>Gen: Wrap tool with trace_tool (OTel instrument)
        Gen->>Consumer: Register tool in Agent runtime configuration
    end

    Consumer->>Gen: Invoke MCP Tool read_file(path)
    Gen->>Cache: get_session(config)
    alt Session not in cache
        Cache->>Subprocess: Launch client subprocess & initialize
        Subprocess-->>Cache: ClientSession active
        Cache->>Cache: Store ClientSession in _sessions registry
    end
    Cache-->>Gen: Returns cached ClientSession
    Gen->>Subprocess: call_tool(read_file, kwargs)
    Subprocess-->>Gen: Returns tool output string
    Gen-->>Consumer: Returns wrapped text output
```
