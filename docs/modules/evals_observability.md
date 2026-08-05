# Arize Phoenix Observability & Evals Module (`src/evals/`)

This document provides technical documentation for the Observability and Tracing Engine powered by Arize Phoenix and OpenTelemetry.

---

## 1. Overview & Telemetry Architecture

Every execution step in an agent workflow—including system prompt compilation, LLM API generation calls, tool invocations, retries, and data transformations—is automatically instrumented using **OpenTelemetry** and **OpenInference** semantic conventions.

Key files:
- [`src/evals/phoenix_service.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/evals/phoenix_service.py): Service initialization, exporter binding, and tracer setup.
- [`configs/agent_config.yaml`](file:///Users/user/Documents/projects/agentic_template/agentic_template/configs/agent_config.yaml): Telemetry project configuration.

---

## 2. Phoenix Service Setup (`src/evals/phoenix_service.py`)

### 2.1 Service Lifecycle & Initialization
`phoenix_service.py` manages initialization and shutdown of the OpenTelemetry trace provider:

```python
from src.evals.phoenix_service import register_phoenix_tracer

# Initializes OTLP HTTP/gRPC exporter stream to Arize Phoenix
register_phoenix_tracer(
    project_name="agentic-template",
    collector_endpoint="http://localhost:6006/v1/traces",
    enable_phoenix=True
)
```

### 2.2 Trace Span Hierarchy & OpenInference Kinds
Spans generated during agent execution are organized hierarchically:

1. **AGENT Span (`SpanKind.AGENT`)**: Root span representing the full duration of `agent.call()`. Captures input prompts, final model outputs, total latency, and cumulative token counts.
2. **LLM Span (`SpanKind.LLM`)**: Sub-span representing an individual call to an LLM provider (Ollama, Gemini, OpenAI). Captures temperature, top_p, model name, prompt tokens, completion tokens.
3. **TOOL Span (`SpanKind.TOOL`)**: Sub-span representing tool execution (e.g. Qdrant vector query, text extraction). Captures tool input arguments, execution result, and exception tracebacks if errors occur.

---

## 3. Configuration & Precedence

Tracing parameters can be configured via environment variables or YAML configuration files, with environment variables taking highest precedence:

| Parameter | Environment Variable | YAML Setting (`phoenix:`) | Default |
| :--- | :--- | :--- | :--- |
| **Enable Telemetry** | `ENABLE_PHOENIX` | `enable_phoenix` | `true` |
| **Project Name** | `PHOENIX_PROJECT_NAME` | `project_name` | `"agentic-template"` |
| **Collector Endpoint** | `PHOENIX_COLLECTOR_ENDPOINT` | `collector_endpoint` | `"http://localhost:6006/v1/traces"` |

---

## 4. Viewing & Navigating Arize Phoenix Dashboard

When running locally or via Docker Compose:
1. Open your browser and navigate to `http://localhost:6006`.
2. Select the `agentic-template` project from the dashboard project dropdown.
3. Inspect:
   - **Trace Execution Trees**: Click on any trace to inspect sub-spans for tool calls and LLM steps.
   - **Token Count & Latency Breakdown**: View exact input/output token usage per call.
   - **Error Logs**: Filter by status code `ERROR` to diagnose tool exceptions or API timeouts immediately.
