# Docker Container Stack & Qdrant Operations Guide

This guide details containerized deployments using Docker Compose, Qdrant vector database storage, and Arize Phoenix container networking.

---

## 1. Container Stack Overview (`docker-compose.yml`)

The multi-container stack includes:
1. `app`: FastAPI backend application and agent execution engine.
2. `qdrant`: Qdrant vector database container storing document embeddings.
3. `phoenix`: Arize Phoenix OpenTelemetry tracing server and dashboard.
4. `vectordb-mcp`: Containerized FastMCP microservice exposing `vectordb_search` and `vectordb_store` over HTTP/SSE.

---

## 2. Docker Compose Commands

### Start Container Stack
```bash
docker compose up -d
```

### View Service Logs
```bash
docker compose logs -f app
docker compose logs -f qdrant
docker compose logs -f phoenix
docker compose logs -f vectordb-mcp
```

### Stop Service Stack
```bash
docker compose down
```

---

## 3. Qdrant Vector Database Operations

- **HTTP API & UI Dashboard**: `http://localhost:6333` / `http://localhost:6333/dashboard`
- **gRPC Port**: `6334`
- **Data Persistence**: Mapped to Docker volume `qdrant_storage`.

### Checking Qdrant Collection Status
```bash
curl http://localhost:6333/collections
```

---

## 4. Arize Phoenix Container Setup

- **Web Dashboard**: `http://localhost:6006`
- **OTLP gRPC Port**: `4317`
- **OTLP HTTP Port**: `4318`
- **Tracing Target**: Set `PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:4317` inside Docker network.

---

## 5. VectorDB MCP Microservice Container (`vectordb-mcp`)

- **Host Port**: `8001` (mapped to container port `8000`)
- **Transport**: HTTP Server-Sent Events (SSE) at `http://localhost:8001/sse`
- **Healthcheck**: `curl http://localhost:8001/healthz`
- **Container Dependencies**: Depends on `qdrant: service_started` and `phoenix: service_healthy`.
- **Complete Runbook**: See [VectorDB MCP Microservice Guide](vectordb_mcp_service.md).

