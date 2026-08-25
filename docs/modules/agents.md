# Agent Framework & SDK Abstractions (`src/agents/`)

This document provides architectural and technical specifications for the core Agent Engine, covering `BaseAgent`, framework wrappers (`PydanticAIAgent`), prompt management, embedding generation, tracing, and model configuration.

---

## 1. Overview & Framework-Agnostic Design

The Agent engine decouples business application code from specific LLM framework implementations. Applications interact strictly with `BaseAgent` and input parts (`TextPart`, `ImagePart`, `FilePart`), enabling seamless switching between model providers and SDKs.

Key files:
- [`src/agents/base.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/base.py): Abstract base classes (`BaseAgent`, `BaseAgentGenerator`) and multimodal input models (`TextPart`, `ImagePart`, `FilePart`).
- [`src/agents/pydantic_ai.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/pydantic_ai.py): Pydantic AI framework integration (`PydanticAIAgent`).
- [`src/agents/tracing.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/tracing.py): Tool tracing decorator (`trace_tool`).
- [`src/agents/config.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/config.py): Configuration parser (`AgentYamlConfig`).
- [`src/agents/embeddings.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/embeddings.py): Embedding model factory (`EmbeddingModelFactory`).
- [`src/agents/prompt_manager.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/agents/prompt_manager.py): System & user prompt template engine.

---

## 2. Core Class Specifications

### 2.1 Multimodal Input Parts (`src/agents/base.py`)
- `TextPart(text: str)`: Represents plain text prompts or query strings.
- `ImagePart(data: bytes | None, path: Path | None, mime_type: str)`: Supports inline binary images or local file paths with format validation.
- `FilePart(data: bytes | None, path: Path | None, mime_type: str, filename: str)`: Represents uploaded documents or text files.

### 2.2 Base Agent Contract (`BaseAgent`)
- `async def call(self, inputs: list[AgentInputPart]) -> str`: Primary asynchronous entrypoint returning full text responses.
- `def call_sync(self, inputs: list[AgentInputPart]) -> str`: Synchronous helper executing `call()` inside an event loop.
- `async def call_stream(self, inputs: list[AgentInputPart]) -> AsyncIterator[str]`: Async generator yielding token chunks as they arrive.

### 2.3 Pydantic AI Agent Wrapper (`src/agents/pydantic_ai.py`)
- **Key Features**: Strictly-typed Pydantic response models, native tool calling, OpenTelemetry tracing instrumentation.
- **Provider Support**: Ollama (`ollama:qwen2.5-coder:7b`), Gemini (`google-gla:gemini-2.5-flash`), OpenAI (`openai:gpt-4o`).

---

## 3. Configuration & Prompt Templating

### 3.1 YAML Configuration Loader (`src/agents/config.py`)
Parses `configs/agent_config.yaml` to specify:
- `model`: Provider, model name, temperature, top_p, max_tokens.
- `system_prompt`: Path to system prompt text file or raw template string.
- `tools`: Configured tool list and settings.
- `phoenix`: Arize Phoenix telemetry project name and collector endpoint.

### 3.2 Prompt Manager (`src/agents/prompt_manager.py`)
- Loads text templates from `src/prompts/system_prompt.txt` and `src/prompts/user_prompt.txt`.
- Renders variable placeholders (e.g. `{current_date}`, `{user_name}`, `{domain_context}`) dynamically before passing to LLMs.

---

## 4. How to Add a New Model Provider or Agent Backend (Extension Guide)

To introduce a new agent framework (e.g. LangChain or custom OpenAI client) in a clean, maintainable way:

### Step 1: Subclass `BaseAgent`
Create a new file `src/agents/custom_framework.py`:

```python
from collections.abc import AsyncIterator
from src.agents.base import BaseAgent, AgentInputPart

class CustomFrameworkAgent(BaseAgent):
    def __init__(self, model_name: str, system_prompt: str, tools: list):
        self.model_name = model_name
        self.system_prompt = system_prompt
        self.tools = tools

    async def call(self, inputs: list[AgentInputPart]) -> str:
        # 1. Format inputs (TextPart, ImagePart)
        # 2. Invoke underlying framework API
        # 3. Return response text
        return "Response from custom framework"

    async def call_stream(self, inputs: list[AgentInputPart]) -> AsyncIterator[str]:
        yield "Chunk 1"
        yield "Chunk 2"
```

### Step 2: Implement Generator (`BaseAgentGenerator`)
Add `CustomAgentGenerator` in the same file to parse `AgentYamlConfig` and instantiate `CustomFrameworkAgent`.

### Step 3: Register in Agent Factory & Add Tests
Add unit tests in `tests/test_agents/test_custom_framework.py` verifying synchronous, asynchronous, and streaming invocations.
