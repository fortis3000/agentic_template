# Standardized Agentic Project Template

## 📚 Documentation & Reference Hub

The codebase documentation is organized into clear architectural specs, subsystem module deep-dives, and operational runbooks under the [`docs/`](docs/README.md) folder:

- **[Documentation Hub Index](docs/README.md)**: Main sitemap and index for system specs, modules, and runbooks.
- **[Architecture Specs](docs/architecture/system_overview.md)**: [System Overview](docs/architecture/system_overview.md) | [Architecture Diagrams](docs/architecture/diagrams.md) | [Design Decisions (ADRs)](docs/architecture/design_decisions.md)
- **[Architectural Module Deep-Dives](docs/modules/tools.md)**:
  - 🛠️ [Tooling Architecture & Tool Factory](docs/modules/tools.md) (ToolFactory, Qdrant tool, Text Extractor, Custom Tool Extension Guide)
  - 🤖 [Agent Framework & SDK Abstractions](docs/modules/agents.md) (BaseAgent, Pydantic AI, Agent Extension Guide)
  - 📊 [Arize Phoenix Observability & Evals](docs/modules/evals_observability.md) (OpenTelemetry spans, token metrics, Phoenix UI)
  - 🎨 [User Frontend UI Subsystem](docs/modules/frontend.md) (Svelte 5 + Vite + TypeScript, reactive state controller)
  - ⚡ [API Gateway & Web Server](docs/modules/api.md) (FastAPI main.py, REST endpoints, streaming SSE, file processing)
  - 📄 [Ingestion Pipeline Subsystem](docs/modules/ingestion.md) (Fixed, Markdown, and Semantic chunkers, Qdrant indexing)
  - 🔌 [Model Context Protocol (MCP) Subsystem](docs/modules/mcp_integration.md) (Stdio client, connection pool, tool discovery)
  - ⚙️ [Shared Utilities Subsystem](docs/modules/utils.md) (Logger, exponential backoff retry, PR validator)
- **[Developer Guides & Runbooks](docs/guides/quickstart.md)**:
  - 🚀 [Developer Quickstart](docs/guides/quickstart.md) | 💻 [Execution Runbook & How-To Runs](docs/guides/how_to_runs.md)
  - 🐳 [Docker & Qdrant Operations](docs/guides/docker_and_qdrant.md) | 🔍 [RAG & Document Ingestion Guide](docs/guides/rag_and_ingestion.md)
  - 🧪 [Testing, Linting & Quality Control](docs/guides/testing_and_validation.md)

---

## Project Organization

```text
├── Makefile           <- Makefile with targets like `make precommit`, `make docker-up`
├── README.md          <- Top-level README for developers using this project
├── pyproject.toml     <- Project configuration for dependencies, linting, formatting
├── uv.lock            <- Lock file for reproducing virtual environment
├── .env.example       <- Template for environment variables and API keys
├── configs            <- Agent and Arize Phoenix YAML configuration files
├── data               <- Workspace data storage (raw, interim, processed, uploads, sessions)
├── docker             <- Dockerfiles and Docker Compose configuration
├── docker-compose.yml <- Multi-container setup for API, UI, Qdrant, and Phoenix
├── docs               <- Structured documentation (architecture, modules, guides)
├── frontend           <- Web User Interface (Svelte 5, TypeScript, Vite, Tailwind CSS)
├── notebooks          <- Jupyter notebooks for experimentation
├── references         <- Explanatory materials, reference guides, and manuals
└── src                <- Main Python source code
    ├── agents         <- SDK-agnostic agent implementations (Pydantic AI)
    ├── api            <- FastAPI web server, REST endpoints, and SSE streaming
    ├── evals          <- Observability frameworks (Arize Phoenix, OTel tracing)
    ├── ingestion      <- Document chunkers (Fixed, Markdown, Semantic) & Qdrant pipeline
    ├── mcp_integration<- Model Context Protocol (MCP) stdio client & connection pool
    ├── prompts        <- System and user prompt templates
    ├── tools          <- Tool Factory, Qdrant DB tool, TextExtractor, Google Sheets
    └── utils          <- Shared utilities (logger, retry framework, PR validator)
```

---

## Logging

This project provides a structured, JSON-friendly logger utility in `src/utils/logger.py`.

**Usage Example:**

```python
from src.utils.logger import get_logger

logger = get_logger(__name__)
logger.info("Initializing agent session", extra={"session_id": "demo-123"})
logger.error("Failed to execute tool", extra={"tool": "qdrant_search"})
```

---

## Agentic Framework Architecture

The template provides a framework-agnostic agent interface (`BaseAgent`) supporting multiple LLM backends and orchestration frameworks:
- **Pydantic AI (`PydanticAIAgent`)**: High-performance agent engine with native OpenTelemetry tracing, schema validation, and tool execution.
- **Local Models (Ollama)**: Out-of-the-box support for local open-weights models (`qwen2.5-coder:7b`).
- **Model Context Protocol (MCP)**: Dynamically connects agents to third-party stdio and SSE tools.

### Spawning and Invocations (Code Example)

```python
import asyncio
from src.agents import PydanticAIAgentGenerator, TextPart, ImagePart, FilePart

async def main():
    # 1. Initialize the agent generator
    generator = PydanticAIAgentGenerator(prompt_base_dir="src/prompts")

    # 2. Instantiate agent from YAML configuration
    agent = generator.create_agent(
        "configs/agent_config.yaml",
        system_variables={"role": "Senior AI Architect"}
    )

    # 3. Non-streaming call
    response = await agent.call(inputs=["Explain vector embeddings in one sentence."])
    print("--- Response ---")
    print(response)

    # 4. Streaming call
    print("\n--- Streaming ---")
    async for chunk in agent.call_stream(inputs=["Tell me a joke about Python."]):
        print(chunk, end="", flush=True)
    print()

    # 5. Multimodal file and image attachment
    # image = ImagePart.from_file("data/raw/diagram.png")
    # doc = FilePart.from_file("data/raw/report.pdf", mime_type="application/pdf")
    # response = await agent.call(inputs=["Analyze document and diagram", doc, image])

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Web Application & API Gateway

The template includes a production-ready Web UI and REST/SSE API gateway:

- **FastAPI Server (`src/api/main.py`)**: Exposes REST endpoints (`/api/chat`, `/api/upload/image`, `/api/upload/document`, `/health`) with background task runner and Server-Sent Events (SSE) token streaming.
- **Svelte 5 Web UI (`frontend/`)**: Modern responsive web application built with Svelte 5 (`$state` signals), TypeScript, Vite, and Tailwind CSS.

### Running Local Servers
```bash
# Start FastAPI backend (port 8000)
uv run uvicorn src.api.main:app --reload --port 8000

# Start Frontend UI (port 5173)
cd frontend && npm run dev
```

---

## Document Ingestion & RAG (Qdrant Vector DB)

The RAG subsystem handles unstructured document ingestion, text chunking, embedding generation, and semantic search:

- **Text Chunkers (`src/ingestion/chunkers.py`)**: Fixed-size chunking, Markdown header chunking, and semantic embedding chunking.
- **Qdrant DB Tool (`src/tools/qdrant_db.py`)**: In-memory and server-mode vector similarity search and collection management.
- **Ingestion Pipeline (`src/ingestion/pipeline.py`)**: End-to-end document parsing and vector indexing.

---

## Observability with Arize Phoenix

Integrated OpenTelemetry and OpenInference instrumentation automatically traces agent invocations, LLM calls, token usage, and tool executions.

### Running with Docker Compose (Recommended)

To launch the full container stack (API backend, Svelte UI, Qdrant vector DB, and Arize Phoenix UI):

```bash
make docker-up
```

Access endpoints:
- **Svelte Web UI**: [http://localhost:5173](http://localhost:5173)
- **FastAPI Gateway**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Arize Phoenix Dashboard**: [http://localhost:6060](http://localhost:6060) (Docker container) or [http://localhost:6006](http://localhost:6006) (Local python)
- **Qdrant Web Dashboard**: [http://localhost:6333/dashboard](http://localhost:6333/dashboard)

To stop services:
```bash
make docker-down
```

### Programmatic Setup (Local Python)

```bash
uv run python src/evals/phoenix_service.py
```
Spawns a local Arize Phoenix collector and runs a demo session to verify telemetry instrumentation.

---

## Goals & Technical Stack

- **Target Language**: **Python 3.13** (managed via `uv`).
- **Dependency Manager**: **`uv`** (`uv sync --extra all` to sync dependencies).
- **Code Style & Formatting**: **Ruff** (`uv run ruff check .` / `uv run ruff format .`).
- **Security Scanner**: **Semgrep** (`.semgrep/rules.yaml` rules for hardcoded secrets).
- **Test Suite**: **pytest** (`uv run pytest` / `make precommit`).

---

## Developer Workflow & Agent Skills

Developer workflows, worktree isolation scripts, pull request templates, and code validation runbooks are maintained directly as **Agent Skills** in the repository under `.agents/skills/`:

- **Worktree Management & Issue Tracking**: Managed via `.agents/skills/gh-cli/` and `.agents/skills/python-coder/` runbooks (using `start_issue.sh` and `submit_pr.sh`).
- **Code Review & Quality Validation**: Automated via `.agents/skills/code-review/` and `.agents/skills/precommit/` skills.
- **TDD & Domain Modeling**: Enforced via `.agents/skills/tdd/` and `.agents/skills/domain-modeling/`.

---

## Pre-Commit Hooks & Quality Control

Git pre-commit hooks are configured in `.pre-commit-config.yaml` to enforce standards prior to commit:

```bash
# Install pre-commit hooks locally
uv run pre-commit install

# Manually execute all pre-commit checks
make precommit
```

### Mutation Testing (`make mutate`)

To assess test suite quality and verify that your tests catch bugs, we use `mutmut`.

To run mutation testing on target modules:

```bash
make mutate
```

For details on configuration, TUI browsing, and interpreting/suppressing mutants, see the [Mutation Testing Documentation](docs/mutation_testing.md).

