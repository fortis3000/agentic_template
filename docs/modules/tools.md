# Unified Tooling Architecture & Tool Manager (`src/tools/`)

This document provides technical documentation for the Unified Tooling Subsystem, covering the `ToolManager` orchestrator, local tool factories (`src/tools/local/`), Model Context Protocol integrations (`src/tools/mcp/`), built-in tools (Qdrant, Text Extractor, Vector Search, Google Sheets), and a step-by-step maintainability guide for extending the tool suite.

---

## 1. Overview & Unified Architecture

Tools are independent, reusable functional units that can be bound to any agent framework (Pydantic AI, Ollama, OpenAI) or executed standalone. The tooling subsystem is organized into a modular, two-tier architecture unified under `ToolManager`:

```text
src/tools/
├── manager.py             <- Unified ToolManager facade (orchestrates local & MCP tools, retries, tracing)
├── contracts/             <- Zero-dependency leaf contracts, DTOs & protocols
│   ├── __init__.py        <- Public contract exports
│   ├── config.py          <- AgentToolConfigProtocol & ToolSettingsProtocol
│   ├── mcp.py             <- McpToolDefinition descriptor
│   └── tool.py            <- ToolCallable, ToolRegistry, BaseToolProtocol
├── local/                 <- In-process Python tool implementations & factories
│   ├── base.py            <- BaseTool ABC, ToolConfigType, ToolFactory registry
│   ├── qdrant_db.py       <- Qdrant vector database integration
│   ├── text_extractor.py  <- Document text extraction (PDF, TXT, Markdown, HTML)
│   ├── vectordb_base.py   <- BaseVectorDB interface & VectorDBFactory
│   ├── vectordb_search.py <- Vector DB semantic search tool
│   └── google_sheet/      <- Google Sheets read/write/vocab entry tools
├── mcp/                   <- Model Context Protocol (MCP) integrations & client sessions
│   ├── client.py          <- McpServerFactory & make_mcp_tool_callable wrapper
│   ├── manager.py         <- McpConnectionManager persistent connection pool
│   └── server.py          <- Stdio / HTTP server connection parameter parsers
└── __init__.py            <- Clean unified public exports
```

---

## 2. Unified Tool Manager (`ToolManager`)

`ToolManager` in `src/tools/manager.py` acts as the single point of contact for agent engines (such as `PydanticAIAgentGenerator`) and the API gateway:

- **Async Resolution (`resolve_tools`)**: Discovers external MCP tools in parallel and binds local Python tools without blocking the event loop.
- **Sync Resolution (`resolve_tools_sync`)**: Synchronous tool discovery for CLI scripts and worker threads.
- **Framework-Neutral Tool Descriptors (`McpToolDefinition`)**: Returns standard Python callables for local tools and structured `McpToolDefinition` descriptors for MCP tools, allowing any agent SDK to adapt them to its native tool interface.
- **Retry & Tracing Integration**: Automatically applies per-tool or global retry configurations (`wrap_tool_with_retry`) and OpenTelemetry span tracing (`trace_tool`).
- **Connection Cleanup (`close_all`)**: Gracefully closes persistent MCP sessions and background tasks on application shutdown.

### Usage Example
```python
from src.tools.manager import ToolManager

# Resolve all tools configured for an agent
tools = await ToolManager.resolve_tools(
    agent_config,
    tools_registry=custom_tools,
    tools_config_path="configs/tools_config.yaml",
)

# Shutdown persistent connections during app teardown
await ToolManager.close_all()
```

---

## 3. Local Tools Subsystem (`src/tools/local/`)

### 3.1 Interface Definition (`BaseTool`)

All custom local tools inherit from `BaseTool` and implement `get_callable()`:

```python
from abc import ABC, abstractmethod
from typing import Callable

class BaseTool(ABC):
    @abstractmethod
    def get_callable(self) -> Callable:
        """Return the callable function or method that executes the tool."""
        pass
```

### 3.2 Tool Registration (`ToolFactory`)

`ToolFactory` manages dynamic registration and instantiation:

- `@ToolFactory.register(name: str)`: Decorator to register tool implementations under a unique string key.
- `ToolFactory.create(name: str, config: Dict[str, Any]) -> BaseTool`: Instantiates a registered tool with specified parameters.
- `ToolFactory.load_from_yaml(filepath: str, strict: bool = True) -> Dict[str, Callable]`: Parses YAML configuration files and returns instantiated tool callables ready for agent binding.

### 3.3 Built-in Local Tools
- **Qdrant Vector DB (`qdrant_db.py`)**: High-performance vector database client with dense, sparse hybrid, and image embeddings support.
- **Text Extractor (`text_extractor.py`)**: Extracts text from PDF (PyMuPDF), HTML, Markdown, and TXT files.
- **Vector Search Tool (`vectordb_search.py`)**: Provides agent-facing semantic document search.
- **Google Sheets Tools (`google_sheet/`)**: Reads, writes, and appends structured rows to Google Sheets with automatic rollback on validation mismatch.

---

## 4. Model Context Protocol Subsystem (`src/tools/mcp/`)

Enables agents to interact with external tools running as independent MCP servers via stdio or HTTP/SSE:

- **`McpConnectionManager` (`manager.py`)**: Maintains persistent client sessions across invocations, avoiding subprocess recreation overhead.
- **`McpServerFactory` (`client.py`)**: Connects to MCP servers, filters tools based on whitelist/blacklist (`enabled_tools` / `disabled_tools`), and caches tool discovery metadata.
- **`make_mcp_tool_callable`**: Wraps remote MCP tool calls into asynchronous Python callables with OpenTelemetry tracing and retry support.
- **`McpToolDefinition`**: Standard dataclass providing tool name, callable, description, and input schema.

---

## 5. How to Create and Register a New Local Tool (Extension Guide)

To create a new tool in a clean, maintainable, and standardized manner:

### Step 1: Create Tool Implementation
Add a new file in `src/tools/local/` (e.g., `src/tools/local/weather_tool.py`):

```python
from typing import Callable

# Relative import ensures single registration across `tools` and `src.tools` namespaces (see pyproject.toml:99-106)
from .base import BaseTool, ToolFactory


@ToolFactory.register("weather_tool")
class WeatherTool(BaseTool):
    """Tool for fetching weather forecasts for a given city."""

    def __init__(self, api_key: str = "", default_unit: str = "celsius"):
        self.api_key = api_key
        self.default_unit = default_unit

    def get_weather(self, city: str, unit: str = "celsius") -> str:
        """Fetch current weather for a city."""
        return f"Weather in {city}: 22° {unit}"

    def get_callable(self) -> Callable:
        return self.get_weather
```

### Step 2: Configure in `configs/tools_config.yaml` or `configs/agent_config.yaml`
```yaml
tools:
  weather_service:
    type: "weather_tool"
    config:
      default_unit: "celsius"
```

### Step 3: Add Unit Tests
Add a test file under `tests/` verifying registration and execution:

```python
import pytest
from src.tools.local.base import ToolFactory


def test_weather_tool_registration():
    tool_instance = ToolFactory.create("weather_tool", {"default_unit": "celsius"})
    callable_fn = tool_instance.get_callable()
    assert "Berlin" in callable_fn("Berlin")
```
