# Execution Runbook & How-To Runs

This document provides step-by-step instructions for running standalone agents, starting backend servers, launching the frontend web UI, and executing background scripts.

---

## 1. Running Standalone Agent Scripts

### 1.1 Running Pydantic AI Agent (`run_pydantic_agent.py`)
Executes the Pydantic AI agent with OpenTelemetry tracing and tool calling:

```bash
uv run python run_pydantic_agent.py
```

### 1.2 Running Local Ollama Agent (`run_ollama_agent.py`)
Executes an agent backed by a local Ollama model (e.g. `qwen2.5-coder:7b`):

```bash
# Ensure Ollama daemon is running locally
ollama serve

# Run the agent script
uv run python run_ollama_agent.py
```

### 1.3 Running Configured Agent Script (`src/scripts/run_agent.py`)
Executes the general agent runner using settings from `configs/agent_config.yaml`:

```bash
uv run python src/scripts/run_agent.py --config configs/agent_config.yaml --query "Explain vector search"
```

---

## 2. Launching Backend & Frontend Web Application

### 2.1 Starting the FastAPI Backend Server
Launch the API gateway on `http://localhost:8000`:

```bash
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
```
- API Docs (Swagger): `http://localhost:8000/docs`
- Health Endpoint: `http://localhost:8000/health`

### 2.2 Starting the Vite Frontend
In a separate terminal, launch the web application interface:

```bash
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser to interact with the full web UI.

---

## 3. Running All Services via Docker Compose

To launch the full stack (FastAPI App, VectorDB MCP Service, Qdrant Vector DB, and Arize Phoenix UI) in unified containers:

```bash
docker compose up --build
```

Access points:
- **Web UI / App**: `http://localhost:5173` / `http://localhost:8000`
- **VectorDB MCP Service**: `http://localhost:8001/sse` (Health: `http://localhost:8001/healthz`)
- **Qdrant Dashboard**: `http://localhost:6333/dashboard`
- **Arize Phoenix UI**: `http://localhost:6006`

---

## 4. Running VectorDB FastMCP Microservice

### 4.1 Standalone Local Server
Run the FastMCP ASGI server directly using Uvicorn:

```bash
# Start local Qdrant first
docker compose up -d qdrant

# Run the FastMCP service
uv run uvicorn src.tools.mcp.servers.vectordb:app --host 0.0.0.0 --port 8000 --reload
```

### 4.2 Docker Compose Dedicated Target
```bash
docker compose up -d vectordb-mcp
curl http://localhost:8001/healthz
```

For tool parameters, contracts, and programmatic Python client examples, see [VectorDB MCP Microservice Guide](vectordb_mcp_service.md).

