# Arize Phoenix Observability & Visual UI Guide

This document provides a guide for understanding, accessing, and visually navigating
**Arize Phoenix** OpenTelemetry tracing within this repository.

---

## 1. Phoenix Overview & Architecture

Arize Phoenix is an open-source AI observability platform that captures OpenTelemetry
trace spans from agent executions, LLM calls, tool interactions, and vector retrievals.

* **Container Service**: Defined in [`docker-compose.yml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/feat/implement-issue-37/docker-compose.yml)
  under service `phoenix`.
* **Ports**:
  * `6060:6006`: Host port 6060 maps to container port 6006 (Web UI & OTLP HTTP).
  * `4317:4317`: OTLP gRPC collector port.
* **Collector Endpoint**: Configured as `PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006/v1/traces`.

---

## 2. Navigating the Arize Phoenix Visual Interface

### Accessing the Web UI

Open your browser and navigate to: **`http://localhost:6060`**

### Step-by-Step Visual Navigation

1. **Select the Project**:
   * Arize Phoenix defaults to showing project `"default"`.
   * Click the **Project Selector** dropdown in the top-left corner.
   * Select **`agentic-template`** (or open direct link:
     [http://localhost:6060/projects/agentic-template](http://localhost:6060/projects/agentic-template)).

2. **Exploring Spans & Traces**:
   * Click the **Spans** tab to view all recorded execution spans.
   * Spans are categorized by OpenInference span kinds:
     * **`CHAIN` / `AGENT`**: Agent invocation lifecycle.
     * **`TOOL`**: Registered tool executions (e.g. `VectorDBSearchTool`).
     * **`RETRIEVER`**: Qdrant vector database similarity searches.

3. **Inspecting Retriever Spans**:
   * Click on a `RETRIEVER` span to view search queries, top-$k$ scores,
     retrieved document chunk contents, and metadata.

---

## 3. Programmatic & GraphQL Verification

Verify active projects and trace spans programmatically:

```bash
curl -s -X POST http://localhost:6060/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query { projects { edges { node { id name } } } }"}'
```
