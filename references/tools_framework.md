# Tools Framework

This document describes the generic Tools Framework for the agentic setup, built around the Factory and Registry patterns.

## Architecture

The framework is located in `src/tools/base.py` and provides a robust way to dynamically instantiate tools from a YAML configuration and register new custom tools.

It relies on two main components:
1. **`BaseTool`**: An abstract base class that all tools must inherit from. It enforces the implementation of a `get_callable()` method. This method must return the actual function that an agent will call, complete with properly typed arguments and descriptive docstrings.
2. **`ToolFactory`**: A registry and factory class that manages tool instantiation.

## How to Register a New Tool

To create a new tool, inherit from `BaseTool` and use the `@ToolFactory.register` decorator:

```python
from typing import Callable
from src.tools.base import BaseTool, ToolFactory

@ToolFactory.register("my_custom_tool")
class MyCustomTool(BaseTool):
    def __init__(self, some_parameter: str):
        self.some_parameter = some_parameter

    def get_callable(self) -> Callable:
        def execute_tool(input_string: str) -> str:
            """Does something custom.
            
            Args:
                input_string: The string to process.
                
            Returns:
                The processed string.
            """
            return f"{self.some_parameter}: {input_string}"
        
        return execute_tool
```

## Configuration

Tools are instantiated dynamically via a YAML configuration file (e.g., `configs/tools_config.yaml`).

```yaml
tools:
  agent_tool_name:
    type: "my_custom_tool"
    config:
      some_parameter: "Hello World"
```

## Agent Integration

You can load all tools defined in the YAML file and pass them as a registry to the `PydanticAIAgentGenerator` (or use them in any agent):

```python
from src.tools.base import ToolFactory

# Load the callables directly from the YAML config
tools_registry = ToolFactory.load_from_yaml("configs/tools_config.yaml")

# Pass to the agent generator
# generator.create_agent(config_path="...", tools_registry=tools_registry)
```
