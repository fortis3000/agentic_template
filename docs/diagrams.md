# Architecture & Flow Diagrams

This document contains Mermaid diagrams illustrating the repository architecture, runtime execution, and developer contribution flows.

---

## 1. High-Level System Architecture

This diagram shows the modular layers of the project template and their boundaries. It highlights the separation of client configuration from SDK execution, backend frameworks, tracing pipelines, and local static analysis.

```mermaid
graph TD
    subgraph Layer1["Layer 1: Configuration & Prompts"]
        A["configs/agent_config.yaml"]
        B["src/prompts/ (system/user template texts)"]
    end

    subgraph Layer2["Layer 2: SDK Abstraction"]
        C["BaseAgent & BaseAgentGenerator"]
        D["PromptManager"]
        E["TextPart & ImagePart (Multimodal)"]
    end

    subgraph Layer3["Layer 3: Agent Backends"]
        F["AntigravityAgent (Google Wrapper)"]
        G["PydanticAIAgent (Pydantic AI Wrapper)"]
        H["google-antigravity-sdk"]
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
    C --> F
    C --> G
    F --> H
    G --> I
    F -.->|OTel Trace Spans| J
    G -.->|OTel Trace Spans| J
    J --> K
    L --> F
    L --> G
    M --> L
    N --> L
```

---

## 2. Runtime Execution Flow

The sequence diagram below details the path a client call takes from the initial agent creation down to prompt template rendering, execution inside the model providers, custom tool invocation, automatic span generation, and reporting to the telemetry platform.

```mermaid
sequenceDiagram
    autonumber
    actor User as Consumer App
    participant Gen as BaseAgentGenerator
    participant PM as PromptManager
    participant Wrapper as Agent Wrapper (Antigravity/PydanticAI)
    participant SDK as Underlying SDK (Antigravity/PydanticAI)
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
    loop Tool Interaction
        SDK->>Wrapper: Execute registered tool (e.g. get_weather)
        Wrapper->>OTel: Start trace span (Kind: TOOL)
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

## 3. Developer Contribution Flow

This flowchart describes the secure software development lifecycle (SSDLC) workflow showing the sequential stages of the developer contribution process:

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
