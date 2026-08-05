# Arize Phoenix Observability & Visual UI Guide

This document provides a guide for understanding, accessing, and visually navigating
**Arize Phoenix** OpenTelemetry tracing within this repository.

---

## 1. Phoenix Overview & Architecture

Arize Phoenix is an open-source AI observability platform that captures OpenTelemetry
trace spans from agent executions, LLM calls, tool interactions, and vector retrievals.

* **Container Service**: Defined in [`docker-compose.yml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/issue-34/docker-compose.yml)
  under service `phoenix`.
* **Ports**:
  * `6060:6006`: Host port 6060 maps to container port 6006 (Web UI & OTLP HTTP).
  * `4317:4317`: OTLP gRPC collector port.
* **Collector Endpoint**: Configured as `PHOENIX_COLLECTOR_ENDPOINT=http://phoenix:6006/v1/traces`.

---

## 2. YAML-Based Phoenix Configuration

Arize Phoenix parameters can be configured directly in the YAML agent configuration file (e.g., [`configs/agent_config.yaml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/issue-34/configs/agent_config.yaml)) under a dedicated `phoenix:` top-level chapter.

### YAML Schema Structure

```yaml
phoenix:
  enabled: true
  project_name: "agentic-template"
  collector_endpoint: "http://localhost:6006/v1/traces"
  host: "localhost"
  port: 6006
  auto_instrument: true
  api_key: null
```

### Pydantic Schema (`PhoenixConfigSchema`)

Defined in [`src/agents/config.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/.worktrees/issue-34/src/agents/config.py):

| Field | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `enabled` | `bool` | `True` | Enable or disable Arize Phoenix OpenTelemetry tracing. |
| `project_name` | `str` | `"agentic-template"` | Target project name in the Arize Phoenix UI dashboard. |
| `collector_endpoint` | `str \| None` | `None` | Custom OTLP collector HTTP endpoint URL. |
| `host` | `str \| None` | `None` | Local host address when launching Phoenix service locally. |
| `port` | `int \| None` | `None` | Local port number when launching Phoenix service locally. |
| `auto_instrument` | `bool` | `True` | Enable automatic OpenTelemetry framework instrumentation. |
| `api_key` | `str \| None` | `None` | Optional API key for authenticating with external Phoenix collectors. |

### Configuration Precedence Hierarchy

1. **Environment Variables**: `PHOENIX_COLLECTOR_ENDPOINT` and `ENABLE_PHOENIX` take highest precedence (allowing Docker Compose to route container traffic to `http://phoenix:6006/v1/traces`).
2. **YAML Configuration**: Parameters defined in the `phoenix:` chapter of `configs/agent_config.yaml` parsed via `AgentYamlConfig` / `PhoenixConfigSchema`.
3. **Default Fallbacks**: Default project name `agentic-template` and default OTLP collector endpoint `http://localhost:4317`.

---

## 3. Navigating the Arize Phoenix Visual Interface

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

## 4. Programmatic & GraphQL Verification

Verify active projects and trace spans programmatically:

```bash
curl -s -X POST http://localhost:6060/graphql \
  -H "Content-Type: application/json" \
  -d '{"query":"query { projects { edges { node { id name } } } }"}'
```

