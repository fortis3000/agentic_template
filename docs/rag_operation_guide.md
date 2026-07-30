# End-to-End RAG Operation & Verification Guide

This guide describes how to operate, test, and verify the containerized
Retrieval-Augmented Generation (RAG) system end-to-end.

---

## 1. System Architecture & Prerequisites

The end-to-end RAG stack consists of four decoupled services defined in
[`docker-compose.yml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/docker-compose.yml):

* **`agent-ui`** (`http://localhost:5173`): Svelte-based frontend dashboard.
* **`agent-api`** (`http://localhost:8000`): FastAPI backend agent server.
* **`qdrant`** (`http://localhost:6333`): Persistent Qdrant vector database
  using named volume `qdrant_data:/qdrant/storage`.
* **`phoenix`** (`http://localhost:6060`): Arize Phoenix OpenTelemetry UI
  and OTLP collector (`http://phoenix:6006/v1/traces`).

---

## 2. End-to-End Verification Steps

### Step 1: Create Data Directory for Ingestion

Create a dedicated folder for raw text/markdown documents to be indexed:

```bash
mkdir -p data/rag_docs
```

### Step 2: Add Testing Documents

Copy markdown documents from the project into `data/rag_docs`:

```bash
cp docs/ingestion_pipeline.md data/rag_docs/
cp docs/diagrams.md data/rag_docs/
cp docs/components.md data/rag_docs/
```

### Step 3: Configure and Run Ingestion Pipeline

Ensure [`configs/ingestion_config.yaml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/configs/ingestion_config.yaml)
points to `source_directory: "data/rag_docs"` and model `gemini-embedding-001`.

Execute document ingestion using the standalone ingestion pipeline:

```bash
uv run python -m src.ingestion.pipeline
```

The pipeline extracts text, chunks documents, generates embeddings via Google GenAI,
and inserts point vectors into Qdrant using deterministic namespace UUIDs (`uuid.uuid5`).

### Step 4: Verify Vector Storage & Data Persistence

Check points stored in Qdrant via REST API:

```bash
curl -s http://localhost:6333/collections/default_collection | jq .
```

To verify persistent storage across container restarts, restart Qdrant:

```bash
docker-compose restart qdrant
curl -s http://localhost:6333/collections/default_collection | jq .result.points_count
```

### Step 5: Launch Containerized Services

Launch the full containerized stack via Docker Compose:

```bash
docker-compose up -d --build
```

Verify that all containers are active:

```bash
docker ps
```

### Step 6: Test RAG Chat Connection & Vector Retrieval

Send a natural language search query to the chatbot endpoint:

```bash
curl -X POST http://localhost:8000/api/agent/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What text chunking strategies are supported in document ingestion?"}'
```

Fetch the completed session response:

```bash
curl -s http://localhost:8000/api/sessions/<SESSION_ID> | jq .
```

The chatbot calls `VectorDBSearchTool`, retrieves matching document chunks from Qdrant,
and synthesizes a grounded answer.

---

## 3. Rate Limit & Attempt Limit Handling

If API rate limits are reached (HTTP 429 / Resource Exhausted):

* Retry logic attempts up to $N$ attempts (defined by `agent.retry.attempts` in
  [`configs/agent_config.yaml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/configs/agent_config.yaml)).
* Upon reaching $N$ attempts, execution stops cleanly and records a user-friendly
  assistant message in session history:

> Rate limit quota exceeded (HTTP 429: Too Many Requests). The configured
> maximum number of attempts (3) has been reached. Please wait before retrying.
