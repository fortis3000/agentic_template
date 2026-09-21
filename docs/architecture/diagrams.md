# Architecture & Flow Diagrams

This document contains Mermaid diagrams illustrating the repository architecture, runtime execution, API + Frontend interactions, and observability telemetry flows.

---

## 1. High-Level System Architecture

```mermaid
graph TD
    subgraph Layer1["Layer 1: Configuration & Prompts"]
        A["configs/agent_config.yaml"]
        B["src/prompts/ (system/user template texts)"]
    end

    subgraph Layer2["Layer 2: SDK Abstraction"]
        C["BaseAgent & BaseAgentGenerator"]
        D["PromptManager"]
        E["TextPart, ImagePart & FilePart (Multimodal)"]
    end

    subgraph Layer3["Layer 3: Agent Backends"]
        G["PydanticAIAgent (Pydantic AI Wrapper)"]
        I["pydantic-ai"]
    end

    subgraph Layer4["Layer 4: Observability & Evals"]
        J["OpenTelemetry & OpenInference Spans"]
        K["Arize Phoenix Service (UI & OTLP Collector)"]
    end

    subgraph Layer5["Layer 5: Developer Guardrails"]
        L["pre-commit (ruff, bandit, ty, pytest)"]
        M["Semgrep Scan (Credential & Security Rule)"]
        N["pr_validator.py (PR Template Check)"]
    end

    %% Relations
    A --> C
    B --> D
    D --> C
    E --> C
    C --> G
    G --> I
    G -.->|OTel Trace Spans| J
    J --> K
    L --> G
    M --> L
    N --> L
```

---

## 2. Runtime Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Consumer App
    participant Gen as BaseAgentGenerator
    participant PM as PromptManager
    participant Wrapper as Agent Wrapper (PydanticAIAgent)
    participant SDK as Underlying SDK (PydanticAI)
    participant OTel as OpenTelemetry Tracing
    participant Phoenix as Arize Phoenix Dashboard

    User->>Gen: create_agent(config_path, system_variables)
    Gen->>Gen: Parse config YAML & validate schemas
    Gen->>Wrapper: Instantiate wrapper with configuration
    User->>Wrapper: call(inputs) or call_stream(inputs)
    Wrapper->>OTel: Start trace span (Kind: AGENT)
    Wrapper->>PM: Resolve and render prompt templates
    PM-->>Wrapper: Compiled system & user prompts
    Wrapper->>SDK: Initialize client session (chat/run)
    loop Tool Interaction (with Retry wrapper)
        SDK->>Wrapper: Execute registered tool (e.g. qdrant_search)
        Wrapper->>OTel: Start trace span (Kind: TOOL)
        note over Wrapper: retry_async/retry_sync if transient error
        Wrapper->>Wrapper: Execute tool function
        Wrapper->>OTel: Close tool span & set output
        Wrapper-->>SDK: Tool result
    end
    SDK-->>Wrapper: Model completion text
    Wrapper->>OTel: Close agent span & set output
    OTel->>Phoenix: Export traces (gRPC / HTTP OTLP)
    Wrapper-->>User: Final response string
```

---

## 3. Frontend & FastAPI Service Communication

```mermaid
graph TD
    subgraph ClientBrowser["Client Web Browser (React + Vite UI)"]
        ChatUI["Chat Interface Component"]
        Uploader["Document & Image Uploader"]
        TraceViewer["Arize Phoenix Link & Trace Viewer"]
    end

    subgraph Network["REST / SSE Protocol"]
        POST_Chat["POST /api/chat"]
        POST_Image["POST /api/upload/image"]
        POST_Doc["POST /api/upload/document"]
        GET_Health["GET /health"]
    end

    subgraph BackendAPI["Backend API Gateway (FastAPI main.py)"]
        API["FastAPI Routes"]
        ImageHandler["Pillow Image Resizer & Converter"]
        TextParser["TextExtractor (PDF, TXT, MD, HTML)"]
    end

    subgraph AgentSystem["Agent System"]
        Agent["PydanticAIAgent"]
        Tools["Tool Factory (Qdrant, Sheets, Extractor)"]
    end

    ChatUI --> POST_Chat
    Uploader --> POST_Image
    Uploader --> POST_Doc
    TraceViewer --> GET_Health

    POST_Chat --> API
    POST_Image --> ImageHandler
    POST_Doc --> TextParser

    API --> Agent
    Agent --> Tools
```

---

## 4. Developer Contribution Flow

```mermaid
flowchart TD
    Start([Start Task]) --> Step1["1. Create Worktree<br/>(bash start_issue.sh)"]
    Step1 --> Step2["2. Implement the Task<br/>(Write code under src/)"]
    Step2 --> Step3["3. Write Tests<br/>(Add test cases under tests/)"]
    Step3 --> Step4["4. Run Tests & Validation<br/>(make precommit / pytest)"]
    Step4 --> Step5["5. Update Docs<br/>(Update documentation in docs/)"]
    Step5 --> Step6["6. Commit<br/>(git commit with semantic commit message)"]
    Step6 --> Step7["7. Push<br/>(git push branch to origin)"]
    Step7 --> Step8["8. Create a PR & Fill Template<br/>(gh pr create --body-file ... or submit_pr.sh)"]
    Step8 --> Merge([PR Merged to Master])
```

---

## 5. Unified Tool & MCP Subsystem Architecture

```mermaid
graph TD
    subgraph Consumers["Agent & API Consumers"]
        AgentGen["PydanticAIAgentGenerator / Agent Backends"]
        APIGateway["FastAPI main.py (Lifespan & Dynamic Load)"]
    end

    subgraph ToolingSubsystem["Unified Tooling Layer (src/tools/)"]
        TM["ToolManager (src/tools/manager.py)"]
        RetryTracer["Retry Wrapping & OpenTelemetry Tracing<br/>(wrap_tool_with_retry, trace_tool)"]
        Desc["Framework-Neutral Descriptors<br/>(Callables & McpToolDefinition)"]
    end

    subgraph LocalTools["Local Tools (src/tools/local/)"]
        TF["ToolFactory & BaseTool (local/base.py)"]
        Qdrant["QdrantVectorDB (local/qdrant_db.py)"]
        Extractor["TextExtractor (local/text_extractor.py)"]
        Search["VectorDBSearchTool (local/vectordb_search.py)"]
        Sheets["Google Sheets Tools (local/google_sheet/)"]
    end

    subgraph MCPTools["Model Context Protocol (src/tools/mcp/)"]
        McpFactory["McpServerFactory (mcp/client.py)"]
        McpManager["McpConnectionManager (mcp/manager.py)"]
        StdioServers["External Stdio MCP Servers<br/>(filesystem, context7, etc.)"]
        SseServers["External HTTP/SSE MCP Servers"]
    end

    AgentGen -->|resolve_tools / resolve_tools_sync| TM
    APIGateway -->|close_all / load_local_tools| TM

    TM -->|Load YAML & Instantiate| TF
    TF --> Qdrant
    TF --> Extractor
    TF --> Search
    TF --> Sheets

    TM -->|Async Parallel Discovery| McpFactory
    TM -->|Persistent Session Pool| McpManager

    McpManager -->|Stdio IPC Protocol| StdioServers
    McpManager -->|SSE Protocol| SseServers

    TM --> RetryTracer
    RetryTracer --> Desc
    Desc -->|Return Callables & Descriptors| AgentGen
```
