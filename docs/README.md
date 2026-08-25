# Standardized Agentic Project Template — Documentation Hub

Welcome to the documentation for the Standardized Agentic Project Template. This repository provides a framework-agnostic foundation for building autonomous AI agents, multi-agent systems, RAG pipelines, and web interfaces with built-in OpenTelemetry observability.

---

## Documentation Architecture & Sitemap

The documentation is organized into three main sections:

### 🏛️ Architecture Specs (`docs/architecture/`)
- **[System Overview](architecture/system_overview.md)**: Layered topology, component design goals, and system principles.
- **[Architecture & Flow Diagrams](architecture/diagrams.md)**: Visual Mermaid diagrams covering system architecture, runtime execution, frontend communication, and MCP tool discovery.
- **[Architectural Decision Records (ADRs)](architecture/design_decisions.md)**: ADRs on Python 3.13 + `uv`, framework-agnostic agents, Tool Factory, Arize Phoenix telemetry, and PR quality gates.

### 🧩 Subsystem & Module Deep-Dives (`docs/modules/`)
- **[Tooling Architecture & Tool Manager](modules/tools.md)**: `ToolManager`, `ToolFactory`, `src/tools/local/`, `src/tools/mcp/`, built-in tools (Qdrant, Text Extractor, Sheets), and Custom Tool Extension Guide.
- **[Agent Framework & SDK Abstractions](modules/agents.md)**: `BaseAgent`, `BaseAgentGenerator`, Pydantic AI wrapper, prompt manager, tracing, embeddings factory, and Agent Extension Guide.
- **[Arize Phoenix Observability & Evals](modules/evals_observability.md)**: `phoenix_service.py`, OpenTelemetry spans, trace hierarchy, token metrics, and Phoenix dashboard setup.
- **[User Frontend UI Subsystem](modules/frontend.md)**: Svelte 5 + TypeScript + Vite + Tailwind UI, reactive `$state` controller (`agent.svelte.ts`), component taxonomy, and API hooks.
- **[API Gateway & Web Server](modules/api.md)**: FastAPI main server, CORS, endpoints (`/api/chat`, `/api/upload/image`, `/api/upload/document`, `/health`), file validation & image resizing.
- **[Ingestion Pipeline Subsystem](modules/ingestion.md)**: Fixed-size, Markdown, and Semantic chunking algorithms, document text extraction, and Qdrant indexing pipeline.
- **[Model Context Protocol (MCP) Subsystem](modules/mcp_integration.md)**: MCP stdio/SSE client, `McpConnectionManager` pool, tool discovery, and server lifecycle.
- **[Shared Utilities Subsystem](modules/utils.md)**: Structured logger, exponential backoff retry handler (`retry_async`), PR & semantic commit validator.

### 📚 Developer Runbooks & Guides (`docs/guides/`)
- **[Developer Quickstart](guides/quickstart.md)**: Prerequisites, `uv` environment sync, `.env` setup, and pre-commit hooks.
- **[Execution Runbook & How-To Runs](guides/how_to_runs.md)**: Command guide for running Pydantic AI agent, Ollama agent, FastAPI backend, and Svelte frontend.
- **[Docker & Qdrant Operations](guides/docker_and_qdrant.md)**: `docker-compose.yml` multi-container orchestration (App, Qdrant, Arize Phoenix).
- **[RAG Operations & Document Ingestion](guides/rag_and_ingestion.md)**: End-to-end RAG guide for document parsing, chunking configuration, vector indexing, and search queries.
- **[Testing, Linting & Quality Control](guides/testing_and_validation.md)**: Matrix of quality tools, running `pytest`, Ruff formatting/linting, pre-commit hooks, and PR validation.
- **[Mutation Testing Guide](mutation_testing.md)**: `mutmut` setup, target modules, execution command (`make mutate`), TUI browser, and mutant handling.

