# Codebase Components & Architecture

This document provides a technical walkthrough of the core components in the Standardized Agentic Project Template.

---

## 1. Configuration & Prompts

### Agent Configuration (`configs/agent_config.yaml`)

- **Purpose**: Defines an agent's structural configuration declaratively, separating behavior from core application code.
- **Attributes**:
  - `provider`: Target LLM provider (e.g., `google`, `pydantic-ai`, `openai`).
  - `model`: The model identifier (e.g., `gemini-2.5-flash`).
  - `system_prompt_source`: Path to the system prompt template (relative or absolute).
  - `user_prompt_source`: Path to the default user prompt template.
  - `user_prompt_format`: Template format, supporting formats like `f-string`.
  - `tools`: A list of registered tool names that the agent can execute.

### Prompt Templates (`src/prompts/`)

- **`system_prompt.txt`**: System prompt base template. Supports dynamic formatting (e.g., embedding roles, rules, or instructions at runtime).
- **`user_prompt.txt`**: User input formatting template. Restructures incoming user queries consistently.

---

## 2. SDK Abstractions

### Core Abstractions (`src/agents/base.py`)

- **`BaseAgent`**: Abstract interface enforcing asynchronous call conventions (`call`, `call_stream`, and synchronous wrapper `call_sync`) for all agent implementations.
- **`BaseAgentGenerator`**: Abstract factory interface for parsing configurations and spawning appropriate `BaseAgent` instances.
- **`AgentInputPart`**: Support for multimodal payloads, supporting `TextPart` (text prompt wrappers) and `ImagePart` (raw bytes or absolute path references with mime-types).
- **`ToolConfig` & `McpServerConfig`**: Interfaces for registering local tool functions or Model Context Protocol (MCP) server endpoints.

### Configuration Parsing (`src/agents/config.py`)

- **`AgentConfigSchema`**: Pydantic schema representing raw YAML keys for strict parsing and input validation.
- **`AgentYamlConfig`**: Holds validated and fully resolved agent attributes used by concrete generators.

### Prompt Resolution (`src/agents/prompt_manager.py`)

- **`PromptManager`**: Locates, caches, and compiles raw text templates into active prompts. Implements f-string replacements to merge system variables or session constraints dynamically before calling the model.

---

## 3. Implementation Backends

### Google Antigravity Wrapper (`src/agents/google_antigravity.py`)

- **`AntigravityAgent`**: Envelops the `google-antigravity-sdk`. Spawns a `G_Agent` instance, converts generic inputs to Antigravity's payload types, and executes calls via the SDK's context manager chat interface.
- **`AntigravityAgentGenerator`**: Leverages YAML configuration and registered tools to build a `LocalAgentConfig` and yield a running agent.
- **`trace_tool`**: A custom python decorator wrapping agent tools with OpenTelemetry span properties adhering to the OpenInference semantic convention.

### Pydantic AI Wrapper (`src/agents/pydantic_ai.py`)

- **`PydanticAIAgent`**: Wraps the `pydantic-ai` orchestration framework. Integrates generic input wrappers into `pydantic_ai` model inputs.
- **`ModelFactory`**: Directs calls to the appropriate provider client wrapper (Google/Gemini, OpenAI, Anthropic, Ollama) and maps corresponding credentials (e.g. `GEMINI_API_KEY`, `OPENAI_API_KEY`).
- **`PydanticAIAgentGenerator`**: Reads configurations, builds corresponding Pydantic AI agent instances, registers python functions as model tools, and validates execution states.

---

## 4. Evals & Observability

### Arize Phoenix Collector (`src/evals/phoenix_service.py`)

- **`px.launch_app()`**: Spawns a local instance of Arize Phoenix hosting an OTLP collector endpoint and visualization dashboard.
- **`register(...)`**: Instruments the Python process by configuring global OpenTelemetry providers to emit OpenInference spans. Traces all agents and decorated tool calls automatically.
- **Demo Script**: Provides mock and live execution modes to verify tracing pathways by calling a dummy weather tool (`get_weather`) and monitoring span outputs.

---

## 5. Security & Quality Guardrails

### Git Pre-Commit Validation (`.pre-commit-config.yaml`)

Standardizes static inspection hooks and test execution before changes can be committed to Git:

- **`Ruff`**: Formats and checks for linting rules or import order violations.
- **`Ty` / `Pyright`**: Enforces strict static type verification.
- **`Bandit`**: Evaluates Python files against common security vulnerabilities.
- **`Pymarkdown`**: Ensures Markdown documentation files strictly follow style standards.
- **`Pytest Suite`**: Executes the entire testing catalog to guarantee zero regressions.
- **`Semgrep Scan`**: Executes a local policy scanner checking for hardcoded credentials.

### Secret Scanning Policies (`.semgrep/rules.yaml`)

- **Purpose**: Defines custom Semgrep rules that flag potential API keys, authorization tokens, or hardcoded sensitive credentials. Violations fail the pre-commit scan and prevent code from being committed.

### Pull Request Verifier (`src/utils/pr_validator.py`)

- **Purpose**: Ensures pull request descriptions match the required structure in `.github/pull_request_template.md`. Parses description bodies, verifies all required sections are present, checks that boilerplate questions are retained, and prevents raw template placeholder text from being committed.
