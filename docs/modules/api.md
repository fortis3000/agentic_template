# API Gateway & Web Server Module (`src/api/`)

This document provides explicit documentation for the FastAPI API server, route contracts, file upload processing, SSE streaming, and session persistence.

---

## 1. Overview & Service Architecture

The API module (`src/api/main.py`) acts as the entrypoint for the React frontend and external REST/SSE consumers. It manages session persistence, file/image validation & processing, backgrounds tasks, and OpenTelemetry lifespan registration.

Key files:
- [`src/api/main.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/api/main.py): FastAPI app initialization, routes, and SSE streaming handlers.
- [`src/agents/config.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/config.py): Pydantic request models and constraint specifications.

---

## 2. Server Lifespan & CORS

- **Lifespan Manager**: On startup, initializes Arize Phoenix OpenTelemetry tracing if enabled in `agent_config.yaml` or environment variables. On shutdown, cleanly closes persistent MCP stdio connections via `McpConnectionManager.close_all()`.
- **CORS Policy**: Configured to allow cross-origin requests from Vite development servers (`http://localhost:5173`).

---

## 3. Route Contracts & Endpoints

### 3.1 `POST /api/agent/chat`
- **Purpose**: Triggers agent execution for a given prompt and session.
- **Request Body (`ChatRequest`)**:
  ```json
  {
    "session_id": "optional-uuid-string",
    "config_path": "configs/agent_config.yaml",
    "query": "Explain quantum computing",
    "system_variables": {"role": "Senior Physicist"},
    "images": [{"data": "base64...", "mime_type": "image/png"}],
    "files": [{"data": "base64...", "mime_type": "text/markdown", "filename": "spec.md"}]
  }
  ```
- **Response**: `{"session_id": "...", "status": "processing"}`.

### 3.2 `GET /api/agent/stream/{session_id}`
- **Purpose**: Opens a Server-Sent Events (SSE) stream broadcasting token chunks, tool execution events (`tool_start`, `tool_complete`, `tool_error`), and completion status.

### 3.3 Image Upload Processing (`process_and_validate_image`)
- Validates MIME formats against acceptable image constraints.
- Inspects resolution dimensions (min width/height, max width/height).
- Resizes over-sized images automatically using Pillow (with support for animated multi-frame GIFs).

### 3.4 Document & Text File Processing (`process_and_validate_file`)
- Validates file size limits and MIME types.
- Extracts clean raw text using `TextExtractor` (PDF, TXT, Markdown, HTML).
- Persists raw uploaded files under `data/uploads/<session_id>/`.

### 3.5 Session Management Endpoints
- `GET /api/configs`: Lists available YAML configs.
- `GET /api/sessions`: Lists previous conversation sessions.
- `GET /api/sessions/{session_id}`: Retrieves full chat history for a session.
- `DELETE /api/sessions/{session_id}`: Cancels running tasks, deletes history file, and purges uploaded files.
- `GET /api/files`: Lists files under `data/` directory.

---

## 4. Error Handling & Validation Rules

1. **Path Traversal Protection**: Session IDs are strictly validated using regex `^[a-zA-Z0-9_-]+$` to prevent directory traversal attacks.
2. **Config Path Boundaries**: Config files must reside within the `configs/` directory.
3. **Structured HTTP Exceptions**: Returns HTTP 400 with detailed message bodies on file parsing failures or constraint violations.
