# Standardized Agentic Project Template — Documentation Hub

Welcome to the documentation for the Standardized Agentic Project Template. This repository provides a framework-agnostic foundation for building autonomous AI agents, multi-agent systems, RAG pipelines, and web interfaces with built-in OpenTelemetry observability.

---

## 1. Documentation Architecture & Sitemap

The documentation is organized into four main sections:

### 🏛️ Architecture Specs (`docs/architecture/`)
- **[System Overview](architecture/system_overview.md)**: Layered topology, component design goals, and system principles.
- **[Architecture & Flow Diagrams](architecture/diagrams.md)**: Visual Mermaid diagrams covering system architecture, runtime execution, frontend communication, and MCP tool discovery.
- **[Architectural Decision Records (ADRs)](architecture/design_decisions.md)**: ADRs on Python 3.13 + `uv`, framework-agnostic agents, Tool Factory, Arize Phoenix telemetry, and PR quality gates.

### 🧩 Subsystem & Module Deep-Dives (`docs/modules/`)
- **[Tooling Architecture & Tool Factory](modules/tools.md)**: `BaseTool`, `ToolFactory`, Qdrant DB tool, Text Extractor tool, Vector search tool, Google Sheets tool, and Step-by-Step Custom Tool Extension Guide.
- **[Agent Framework & SDK Abstractions](modules/agents.md)**: `BaseAgent`, `BaseAgentGenerator`, Google Antigravity SDK wrapper, Pydantic AI wrapper, prompt manager, embeddings factory, and Agent Extension Guide.
- **[Arize Phoenix Observability & Evals](modules/evals_observability.md)**: `phoenix_service.py`, OpenTelemetry spans, trace hierarchy, token metrics, and Phoenix dashboard setup.
- **[User Frontend UI Subsystem](modules/frontend.md)**: Svelte 5 + TypeScript + Vite + Tailwind UI, reactive `$state` controller (`agent.svelte.ts`), component taxonomy, and API hooks.
- **[API Gateway & Web Server](modules/api.md)**: FastAPI main server, CORS, endpoints (`/api/chat`, `/api/upload/image`, `/api/upload/document`, `/health`), file validation & image resizing.
- **[Ingestion Pipeline Subsystem](modules/ingestion.md)**: Fixed-size, Markdown, and Semantic chunking algorithms, document text extraction, and Qdrant indexing pipeline.
- **[Model Context Protocol (MCP) Subsystem](modules/mcp_integration.md)**: MCP stdio/SSE client, `McpConnectionManager` pool, tool discovery, and server lifecycle.
- **[Shared Utilities Subsystem](modules/utils.md)**: Structured logger, exponential backoff retry handler (`retry_async`), PR & semantic commit validator.

### 📚 Developer Runbooks & Guides (`docs/guides/`)
- **[Developer Quickstart](guides/quickstart.md)**: Prerequisites, `uv` environment sync, and `.env` setup.
- **[Execution Runbook & How-To Runs](guides/how_to_runs.md)**: Command guide for running Pydantic AI agent, Ollama agent, FastAPI backend, and Svelte frontend.
- **[Docker & Qdrant Operations](guides/docker_and_qdrant.md)**: `docker-compose.yml` multi-container orchestration (App, Qdrant, Arize Phoenix).
- **[RAG Operations & Document Ingestion](guides/rag_and_ingestion.md)**: End-to-end RAG guide for document parsing, chunking configuration, vector indexing, and search queries.
- **[Testing, Linting & Quality Control](guides/testing_and_validation.md)**: Running `pytest`, Ruff formatting/linting, pre-commit hooks, and PR validation.

---

## 2. Change Inventory & Repository History

This section stockpiles major changes and feature milestones implemented across the repository (PRs `#1` through `#71`):

| Commit / PR | Module | Capability / Change Summary |
| :--- | :--- | :--- |
| `#1`, `e771a28` | **Core Framework** | Initial agentic framework structure, `BaseAgent` abstraction, and project dependencies. |
| `#4`, `857f938` | **Skills & Dev Tools** | Integrated initial developer skills, worktree scripts, and clean development workflows. |
| `#5`, `23afe96` | **Observability** | Integrated Arize Phoenix OpenTelemetry tracing, span collector, and telemetry service (`phoenix_service.py`). |
| `#7`, `d98cd4e` | **Linting & Quality** | Added pre-commit hooks, Ruff formatting rules, and strict Python type annotations. |
| `#9`, `7fed2bb` | **Tools** | Added `BaseTool` interface, `ToolFactory`, and initial Google Sheets / Docs tools. |
| `#10`, `#11` | **Git & PR Guardrails**| Added PR template (`.github/pull_request_template.md`), `pr_validator.py`, and semantic commit checks. |
| `#26`, `fd72427` | **Agents Engine** | Integrated `PydanticAIAgent` with native OpenTelemetry tracing spans and response schemas. |
| `#28`, `3aa3152` | **Documentation** | Added architecture flow diagrams, Mermaid charts, and developer runbooks. |
| `#29`, `dd7e372` | **Local LLM** | Added Ollama provider support (`run_ollama_agent.py`) for running local open-weights models. |
| `#33`, `4af5721` | **Frontend & API** | Added FastAPI backend server (`src/api/main.py`) and Svelte 5 + Vite web interface (`frontend/`). |
| `#43`, `0957eca` | **Tools / Sheets** | Restructured Google Sheets client and resolved API error handling. |
| `#45`, `6ed9ca2` | **Dev Environment** | Optimized pre-commit configuration and environment setup. |
| `#46`, `b3566f8` | **Utils & Resilience** | Added exponential backoff retry mechanism (`src/utils/retry.py`) for models, tools, and containers. |
| `#47`, `3f2562c` | **API & Media** | Added image upload, format validation, and automatic resolution resizing via Pillow in FastAPI. |
| `#49`, `f7a0e56` | **API & Documents** | Added document text file upload endpoint supporting PDF, TXT, MD, and HTML extraction. |
| `#56`, `fea23d0` | **RAG & Vector DB** | Implemented text chunking strategies (Fixed, Markdown, Semantic), Qdrant DB tool, and ingestion pipeline. |
| `#58`, `4be9db3` | **Dev Tools** | Added environment bootstrap task and GitHub PAT token loading. |
| `#71`, `43a4ef6` | **Observability** | Added Arize Phoenix YAML configuration schemas (`configs/agent_config.yaml`). |


