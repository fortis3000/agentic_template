# High-Level System Architecture

This document presents the high-level architecture, design principles, and component topology of the Standardized Agentic Project Template.

---

## 1. System Vision & Design Goals

The primary goal of this project template is to provide a standardized, framework-agnostic, and production-ready foundation for building autonomous AI agents and Multi-Agent workflows. Key principles include:

1. **Framework Agnosticism**: Standardized abstraction interfaces (`BaseAgent`, `BaseTool`, `EmbeddingClient`) allow agents to be powered by different engines (Pydantic AI, Ollama, OpenAI) without refactoring downstream application code.
2. **Deep Module Design**: Components are structured with tight encapsulation and shallow interfaces, concealing complex internal state while exposing simple, intuitive API contracts.
3. **End-to-End Observability**: Built-in OpenTelemetry instrumentation routes execution traces, model calls, token counts, and tool spans to Arize Phoenix out-of-the-box.
4. **Production-Grade Quality Gates**: Enforces local development sandboxing, type-checking, automated linting via Ruff, and PR template validation via pre-commit git hooks.

---

## 2. Layered Architecture Topology

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Client Layer                                    │
│       React + Vite UI (frontend/)  |  CLI Tools  |  External HTTP/REST     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ REST / SSE
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                             Gateway & API Layer                             │
│                     FastAPI Server (src/api/main.py)                        │
│         Route Handlers  |  Multipart Extractor  |  SSE Publishers          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                           Agent Engine Layer                                │
│       PromptManager  |  Config Loader  |  BaseAgent Specification           │
│    ┌─────────────────────────────────────────────────────────────────┐      │
│    │                  PydanticAIAgent (OTel Traced)                  │      │
│    └─────────────────────────────────────────────────────────────────┘      │
└──────────────────┬───────────────────────────────────────┬──────────────────┘
                   │                                       │
┌──────────────────▼───────────────────┐ ┌─────────────────▼──────────────────┐
│             Tool Factory             │ │         Observability          │
│   Qdrant DB  |  Text Extractor       │ │  Arize Phoenix Telemetry       │
│   Vector Search  |  Google Sheets    │ │  OpenTelemetry Collector       │
│   MCP Stdio / SSE Integration        │ │  Trace Spans & Token Metrics   │
└──────────────────┬───────────────────┘ └────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────────────┐
│                            Storage & Vector DB                              │
│         Qdrant Vector Database  |  Local Workspace Disk (data/)             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Core Architectural Components

### 3.1 Agents Engine (`src/agents/`)
- **Base Interface (`base.py`)**: Abstract base class enforcing consistent `run()`, `stream()`, and prompt rendering behaviors.
- **Pydantic AI (`pydantic_ai.py`)**: Integration with Pydantic AI framework providing strict response schemas, tool calling, and OpenTelemetry trace hooks.
- **Tracing Module (`tracing.py`)**: Tool OpenTelemetry span instrumentation (`trace_tool`).
- **Prompt Manager (`prompt_manager.py`)**: Centralized system prompt and user template renderer supporting variable substitution.
- **Embeddings Subsystem (`embeddings.py`)**: Multi-provider embedding generator supporting FastEmbed, sentence-transformers, Google, and Ollama embeddings.

### 3.2 Tooling Engine & Tool Factory (`src/tools/`)
- **Tool Standard (`base.py`)**: Abstract tool interface enforcing function metadata, argument schemas, and synchronous/asynchronous execution contracts.
- **Qdrant DB Tool (`qdrant_db.py`)**: In-memory and server-mode vector search tool for retrieving relevant document chunks.
- **Text Extractor (`text_extractor.py`)**: Document parser supporting text extraction from PDF, TXT, Markdown, and HTML files.
- **Vector Search (`vectordb_search.py`)**: Standalone semantic search tool interacting with vector stores.
- **Google Sheets (`google_sheet/`)**: Integrations for external tabular read/write operations.

### 3.3 API Gateway (`src/api/`)
- Built on **FastAPI**, serving:
  - `/api/chat`: Primary agent execution route supporting synchronous responses and Server-Sent Events (SSE) streaming.
  - `/api/upload/image`: Image upload endpoint with format validation and dynamic resizing.
  - `/api/upload/document`: Document upload endpoint extracting text content directly for agent context injection.
  - `/health`: System health check and status API.

### 3.4 Ingestion Pipeline (`src/ingestion/`)
- **Chunking Engine (`chunkers.py`)**: Implements fixed-size, recursive character, and semantic text chunkers.
- **Pipeline Orchestrator (`pipeline.py`)**: Controls document reading, chunking, embedding generation, and Qdrant upsert operations.

### 3.5 Observability & Evals (`src/evals/`)
- **Arize Phoenix Service (`phoenix_service.py`)**: Launches or connects to Arize Phoenix instance over OTLP. Automatically records agent trace spans, tool calls, execution latencies, and token counts.

### 3.6 MCP Integration (`src/mcp_integration/`)
- **Stdio & SSE Client (`client.py`, `manager.py`, `server.py`)**: Connects agents to external Model Context Protocol servers to dynamically discover and execute third-party tools.

### 3.7 User Frontend (`frontend/`)
- React + Vite + TypeScript web interface providing chat UI, live tool execution panels, file upload preview, and direct links to Arize Phoenix traces.

---

## 4. Architectural Principles for Maintenance & Extension

1. **Adding New Tools**: Extend `BaseTool` in `src/tools/base.py`, register the tool in the Tool Factory, and add corresponding test coverage under `tests/test_tools/`.
2. **Adding New Agents**: Extend `BaseAgent` in `src/agents/base.py`, implement prompt rendering and tool dispatching, and add tests in `tests/test_agents/`.
3. **Observability**: Ensure all async tool executions wrap calls in `traced_tool` or active OpenTelemetry spans so Arize Phoenix visualizes execution trees seamlessly.
