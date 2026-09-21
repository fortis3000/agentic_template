# Architectural Decision Records (ADRs)

This document records the foundational architectural decisions, rationale, and tradeoffs governing the codebase design.

---

## ADR 1: Python 3.13 & `uv` Package Management

### Status
Accepted

### Context
Python dependency resolution across agent SDKs, AI providers, and OpenTelemetry instrumentation can cause version conflicts and slow installation times. Traditional tools (`pip`, `poetry`) can take minutes to lock and install dependencies.

### Decision
Adopt **Python 3.13** as the runtime target and **`uv`** as the primary package and project manager.

### Consequences
- Lightning-fast environment sync via `uv sync --extra all`.
- Deterministic locking with `uv.lock`.
- Strict py313 linting and formatting enforced by Ruff.

---

## ADR 2: Framework-Agnostic Agent Abstraction Layer

### Status
Accepted

### Context
The AI agent ecosystem evolves rapidly. Binding the application tightly to a single agent framework (e.g. LangChain, CrewAI, or Pydantic AI) risks framework lock-in.

### Decision
Create a unified `BaseAgent` and `BaseAgentGenerator` interface in `src/agents/base.py`. Underneath, framework wrappers (e.g., `PydanticAIAgent` in `pydantic_ai.py`) implement the uniform API contract.

### Consequences
- Decouples client/UI applications from specific framework details.
- Allows switching or extending agent backend engines dynamically.
- Enforces standardized prompt templating via `PromptManager`.

---

## ADR 3: Tool Factory & Standardized Custom Tool Contract

### Status
Accepted

### Context
Agents need to interact with external tools (Qdrant, vector databases, file parsers, Google Sheets, MCP tools). Unstructured tool implementations lead to redundant error handling, inconsistent tracing, and difficult testing.

### Decision
Implement a central `BaseTool` class in `src/tools/base.py` enforcing name, description, schema definitions, sync/async entrypoints, and automatic OpenTelemetry span wrapping.

### Consequences
- Adding a new tool only requires inheriting from `BaseTool` and implementing `_run()` / `_arun()`.
- Every tool call automatically creates OpenTelemetry trace spans in Arize Phoenix.
- Standardized tool registration in `src/tools/` allows dynamic runtime injection into agents.

---

## ADR 4: Out-of-the-Box Telemetry with Arize Phoenix

### Status
Accepted

### Context
Debugging multi-step agent reasoning, tool calls, and LLM responses requires visibility into span execution trees, latency breakdowns, and prompt/response payloads.

### Decision
Integrate **Arize Phoenix** via OpenTelemetry and OpenInference standards as the default observability stack. `src/evals/phoenix_service.py` handles background registration and OTLP streaming.

### Consequences
- Every agent invocation and tool execution is captured and visualizable in Phoenix UI (`http://localhost:6006`).
- Docker Compose includes a ready-to-run Phoenix service container.
- Configurable via `configs/agent_config.yaml` or environment variables (`PHOENIX_COLLECTOR_ENDPOINT`).

---

## ADR 5: Automated Pre-Commit Quality Gates & Semantic Commits

### Status
Accepted

### Context
Maintaining high code quality, preventing security leaks (tokens/secrets), and keeping pull requests uniform requires automated checks before code is committed or merged.

### Decision
1. Enforce **Conventional Commits** (`<type>(<scope>): <description>`) via pre-commit hooks.
2. Require pre-commit checks: `ruff check`, `ruff format`, `pytest`, `pr_validator.py`.
3. Require all pull requests to adhere to the template in `.github/pull_request_template.md`.

### Consequences
- Consistent commit log history.
- Zero unchecked lint or type errors committed to master.
- PRs contain structured summaries, verification steps, and architectural discussion notes.

---

## ADR 6: Unified Tool and MCP Management Architecture

### Status
Accepted

### Context
Originally, tool implementations and MCP (Model Context Protocol) server integrations were split across separate top-level modules (`src/tools/` and `src/mcp_integration/`), and agent factories manually coordinated tool lookup, MCP discovery, retry wrapping, tracing, and session lifecycle cleanup. This created architectural fragmentation, made tool discovery error-prone across sync and async contexts, and complicated testing and extensibility.

### Decision
1. Unify all tool and MCP management under the `src/tools/` package:
   - `src/tools/contracts/`: Leaf contract subpackage defining `McpToolDefinition`, protocols, and type aliases with zero project-internal imports.
   - `src/tools/local/`: Local Python tool implementations (`BaseTool`, `ToolFactory`, vector databases, text extractors, Google Sheets).
   - `src/tools/mcp/`: External Model Context Protocol server integrations (`McpServerFactory`, `McpConnectionManager`, server parameter parsers).
   - `src/tools/manager.py`: Central `ToolManager` facade orchestrating both local tool resolution and external MCP discovery, retry wrapping, tracing, and session cleanup (`close_all()`).
2. Maintain framework agnosticism: `ToolManager` returns standard Python callables for local tools and `McpToolDefinition` descriptors for MCP tools, allowing any agent SDK (Pydantic AI, Ollama, OpenAI) to adapt them to its native tool binding.
3. Perform asynchronous parallel discovery of multiple MCP servers via `asyncio.gather`.
4. Perform a clean breaking refactoring without legacy backwards-compatibility shims or deprecation warnings. All consumers import directly from `src.tools`, `src.tools.local`, `src.tools.mcp`, or `src.tools.contracts`.
5. Update agent generators (`PydanticAIAgentGenerator`) and API lifecycle handlers (`src/api/main.py`) to delegate tool resolution and cleanup directly to `ToolManager`.
6. Add tool name prefixing (`tool_prefix`) to `McpServerConfigSchema` to namespace advertised tool names (`{prefix}_{tool_name}`), avoiding naming collisions when multiple MCP servers expose identically named tools while preserving original RPC names in `McpToolDefinition.original_name`.
7. Implement resilient remote server error handling: inspect `CallToolResult.isError`, annotate OpenTelemetry spans with error status, and return self-correcting error messages to the model (or raise `RuntimeError` when `raise_on_error: true`).
8. Extract multimodal image payloads (`ImageContent`) into structured dictionaries and adapt them into native SDK parts (`BinaryContent` in Pydantic AI).
9. Support opt-in native framework interoperability (`native_pydantic_toolset: true`) allowing agents to mount `pydantic_ai.mcp.MCPToolset` directly for sampling and deferred loading.

### Consequences
- **Single Point of Control**: Agent engines only need to interact with `ToolManager` to resolve all tools (local and remote MCP).
- **Framework Agnostic**: The tooling layer has zero dependencies on specific agent SDKs (e.g. `pydantic-ai`), returning neutral callables and descriptors.
- **Dependency Inversion**: Dedicated leaf contracts (`src/tools/contracts/` and `src/agents/contracts/`) eliminate circular import risks and decouple domain logic.
- **Collision Prevention**: `tool_prefix` eliminates name collisions between external MCP servers.
- **Error Resilience & Observability**: Remote MCP `isError` flags are reflected in OpenTelemetry spans and enable LLM self-healing.
- **Multimodal Support**: Agents can consume image outputs from external MCP servers.
- **Separation of Concerns**: Clear structural separation between in-process `local/` tools and subprocess/network `mcp/` transports.
- **Clean Lifecycle Management**: `ToolManager.close_all()` provides deterministic shutdown of persistent MCP server sessions and background tasks.
- **No Legacy Debt**: Deprecated shims and warning overhead are eliminated entirely in favor of a clean, direct namespace structure.

