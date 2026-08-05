# Tooling Architecture & Tool Factory Module (`src/tools/`)

This document provides explicit documentation for the Tooling Subsystem, covering the Tool Factory design pattern, built-in tools (Qdrant, Text Extractor, Vector Search, Google Sheets), and a step-by-step maintainability guide for extending the tool suite.

---

## 1. Overview & Tooling Architecture

The tool engine is designed around a **Factory Pattern** and **Interface Segregation**. Tools are independent, reusable functional units that can be bound to any agent framework (Pydantic AI, Google Antigravity SDK, Ollama).

Key files:
- [`src/tools/base.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/tools/base.py): Base class `BaseTool` and `ToolFactory` registry.
- [`src/tools/qdrant_db.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/tools/qdrant_db.py): Qdrant vector database integration tool.
- [`src/tools/text_extractor.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/tools/text_extractor.py): Document and text file extraction tool (PDF, TXT, MD, HTML).
- [`src/tools/vectordb_search.py`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/tools/vectordb_search.py): Vector DB ingestion and semantic retrieval tool.
- [`src/tools/google_sheet/`](file:///Users/user/Documents/projects/agentic_template/agentic_template/src/tools/google_sheet/): Google Sheets tool.

---

## 2. Tool Factory (`src/tools/base.py`)

### 2.1 Interface Definition (`BaseTool`)

All custom tools inherit from `BaseTool` and implement `get_callable()`:

```python
from abc import ABC, abstractmethod
from typing import Callable

class BaseTool(ABC):
    @abstractmethod
    def get_callable(self) -> Callable:
        """Return the callable function or method that executes the tool."""
        pass
```

### 2.2 Tool Registration (`ToolFactory`)

`ToolFactory` manages dynamic registration and instantiation:

- `@ToolFactory.register(name: str)`: Decorator to register tool implementations under a unique string key.
- `ToolFactory.create(name: str, config: Dict[str, Any]) -> BaseTool`: Instantiates a registered tool with specified parameters.
- `ToolFactory.load_from_yaml(filepath: str, strict: bool = True) -> Dict[str, Callable]`: Parses YAML configuration files (e.g. `configs/agent_config.yaml`) and returns instantiated tool callables ready for agent binding.

---

## 3. Built-In Tools

### 3.1 Qdrant Vector Database Tool (`qdrant_db.py`)
- **Purpose**: Connects to Qdrant vector search database (either in-memory `:memory:` or remote/Docker host `http://localhost:6333`).
- **Key Methods**:
  - `search_vectors(query: str, limit: int = 5)`: Executes dense vector similarity search and returns matching text chunks.
  - `upsert_documents(documents: List[Dict])`: Embeds text chunks and indexes them into specified Qdrant collections.

### 3.2 Text Extractor Tool (`text_extractor.py`)
- **Purpose**: Extracts raw text content from uploaded files for context augmentation.
- **Supported Formats**:
  - `PDF`: Parsed via `pypdf` / `pdfplumber`.
  - `HTML`: Parsed via `BeautifulSoup4`.
  - `TXT` & `Markdown`: Directly read with UTF-8 encoding.
- **Error Handling**: Graceful fallback returning structured error payloads on corrupt files.

### 3.3 Vector Search Tool (`vectordb_search.py` & `vectordb_base.py`)
- **Purpose**: Provides a standardized agent-facing tool signature (`search_knowledge_base(query: str)`) that abstracts vector DB connection logic.

### 3.4 Google Sheets Integration (`google_sheet/`)
- **Purpose**: Interacts with Google Sheets API to write agent outputs or update spreadsheets programmatically.

---

## 4. How to Create and Register a New Custom Tool (Extension Guide)

To create a new tool in a clean, maintainable, and standardized manner, follow these steps:

### Step 1: Create Tool Implementation
Add a new Python file in `src/tools/` (e.g., `src/tools/weather_tool.py`):

```python
from typing import Callable
from src.tools.base import BaseTool, ToolFactory

@ToolFactory.register("weather_tool")
class WeatherTool(BaseTool):
    """Tool for fetching weather forecasts for a given city."""

    def __init__(self, api_key: str = "", default_unit: str = "celsius"):
        self.api_key = api_key
        self.default_unit = default_unit

    def get_weather(self, city: str, unit: str = "celsius") -> str:
        """Fetch current weather for a city.
        
        Args:
            city: The target city name (e.g. 'Berlin', 'Tokyo').
            unit: Temperature unit ('celsius' or 'fahrenheit').
        """
        # Implementation logic...
        return f"Weather in {city}: 22° {unit}"

    def get_callable(self) -> Callable:
        return self.get_weather
```

### Step 2: Configure in `agent_config.yaml`
Register the tool in your YAML configuration:

```yaml
tools:
  weather_service:
    type: "weather_tool"
    config:
      default_unit: "celsius"
```

### Step 3: Add Unit Tests
Add a test file under `tests/test_tools/test_weather_tool.py`:

```python
import pytest
from src.tools.base import ToolFactory
from src.tools.weather_tool import WeatherTool

def test_weather_tool_registration():
    tool_instance = ToolFactory.create("weather_tool", {"default_unit": "celsius"})
    callable_fn = tool_instance.get_callable()
    result = callable_fn("Berlin")
    assert "Berlin" in result
```
