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
   - `src/tools/local/`: Local Python tool implementations (`BaseTool`, `ToolFactory`, vector databases, text extractors, Google Sheets).
   - `src/tools/mcp/`: External Model Context Protocol server integrations (`McpServerFactory`, `McpConnectionManager`, server parameter parsers).
   - `src/tools/manager.py`: Central `ToolManager` facade orchestrating both local tool resolution and external MCP discovery, retry wrapping, tracing, and session cleanup (`close_all()`).
2. Provide backwards compatibility in `src/mcp_integration/` and top-level `src/tools/` by re-exporting symbols and raising `DeprecationWarning` where appropriate.
3. Update agent generators (`PydanticAIAgentGenerator`) and API lifecycle handlers (`src/api/main.py`) to delegate tool resolution and cleanup directly to `ToolManager`.

### Consequences
- **Single Point of Control**: Agent engines only need to interact with `ToolManager` to resolve all tools (local and remote MCP).
- **Separation of Concerns**: Clear structural separation between in-process `local/` tools and subprocess/network `mcp/` transports.
- **Consistent Telemetry & Retries**: OpenTelemetry span wrapping and retry configurations are applied uniformly across both local tools and MCP tools.
- **Clean Lifecycle Management**: `ToolManager.close_all()` provides deterministic shutdown of persistent MCP server sessions and background tasks.
- **Backwards Compatible**: Existing imports from `src.mcp_integration` and `src.tools` continue functioning seamlessly.

