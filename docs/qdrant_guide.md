# Qdrant Vector Database & Visual Inspection Guide

This document provides a guide for understanding, inspecting, and troubleshooting
the **Qdrant Vector Database** integration within this repository.

---

## 1. Qdrant Overview & Architecture

Qdrant is a high-performance vector database used to store document embeddings and
perform similarity search.
Qdrant is a high-performance vector database used to store document embeddings
and perform similarity search.

* **Container Service**: Defined in [`docker-compose.yml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/docker-compose.yml)
  under service `qdrant`.
* **REST & gRPC Ports**:
  * `6333`: REST API endpoint.
  * `6334`: gRPC interface.
* **Host Resolution**:
  * **Local Python scripts**: Connect to `localhost:6333`.
  * **Docker container (`agent-api`)**: Connects to `qdrant:6333` via internal
    Docker network.
* **Data Persistence**: Point vectors and collection indexes persist across
  container reinstantiations via Docker named volume
  `qdrant_data:/qdrant/storage`.

---

## 2. Visual Web UI & Inspection Options

### Why `http://localhost:6333` returns JSON instead of a Web UI

By default, navigating to `http://localhost:6333` in a web browser returns a JSON
status response (`{"title":"qdrant - vector search engine"}`). Qdrant's core
container image serves a REST API on port 6333 rather than a full graphical web
interface.

### Option A: Accessing the Built-In Qdrant Web Dashboard

Qdrant includes a web dashboard built directly into the REST service:

1. Open your browser and navigate to: **`http://localhost:6333/dashboard`**
2. The interactive web dashboard allows you to:
   * Browse collections (`default_collection`).
   * View point counts, vector dimensions (3072 for model
     `gemini-embedding-001`), and payload fields.
   * Run visual similarity search queries directly from the browser.

### Option B: Using Official Qdrant Web UI (Cloud / Standalone)

You can also connect the official open-source Qdrant Web UI to your local instance:

1. Open [`https://ui.qdrant.tech`](https://ui.qdrant.tech) in your browser.
2. Set Server URL to: `http://localhost:6333`
3. Click **Connect** to visually inspect your local collections and vectors.

### Option C: REST API Inspection via cURL

Inspect collections and points directly via REST API calls:

```bash
# List all collections
curl -s http://localhost:6333/collections

# Inspect detailed info for default_collection
curl -s http://localhost:6333/collections/default_collection | jq .

# Count total points stored in default_collection
curl -s http://localhost:6333/collections/default_collection/points/count | jq .
```

---

## 3. Sparse Vector & Deduplication Technical Details

* **Unique Index Constraint**: Qdrant `SparseVector(indices=..., values=...)`
  requires `indices` to be strictly unique and sorted. Hashing words
  modulo 10000 produces index collisions if multiple words map.
* **Deduplication Fix**: In [`src/tools/qdrant_db.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/src/tools/qdrant_db.py),
  word counts are aggregated by hashed integer index (`index_counts[idx] += 1.0`)
  prior to generating `SparseVector`, preventing duplicate index errors (HTTP 422).
* **Collection Existence Fallback**: [`src/tools/vectordb_search.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/src/tools/vectordb_search.py)
  verifies collection existence before executing queries. If an invalid
  collection name is provided, it logs a debug message and falls back
  gracefully to `default_collection`.
