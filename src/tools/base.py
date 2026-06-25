import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Type

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ToolConfigType:
    """Structure defining a tool configuration."""

    type: str
    config: Dict[str, Any] = field(default_factory=dict)


class BaseTool(ABC):
    """Abstract base class for all tools."""

    @abstractmethod
    def get_callable(self) -> Callable:
        """Return the function or method that executes the tool.

        The returned callable should have proper type hints and docstrings
        for agent frameworks to use.
        """
        pass


class ToolFactory:
    """Registry pattern factory for dynamically instantiating tools."""

    _registry: Dict[str, Type[BaseTool]] = {}

    @classmethod
    def register(cls, name: str) -> Callable:
        """Decorator to register a tool class under a given name.

        Args:
            name: The string identifier for the tool type.
        """

        def inner_wrapper(wrapped_class: Type[BaseTool]) -> Type[BaseTool]:
            if name in cls._registry:
                logger.warning(f"Tool '{name}' is already registered. Overwriting.")
            cls._registry[name] = wrapped_class
            return wrapped_class

        return inner_wrapper

    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> BaseTool:
        """Instantiate a tool using its registered name and configuration.

        Args:
            name: The registered name of the tool.
            config: A dictionary of arguments to pass to the tool's __init__.
        """
        if name not in cls._registry:
            raise ValueError(f"Tool type '{name}' is not registered.")

        tool_class = cls._registry[name]
        return tool_class(**config)

    @classmethod
    def load_from_yaml(cls, filepath: str) -> Dict[str, Callable]:
        """Load tools from a YAML configuration file.

        Args:
            filepath: Path to the YAML file.

        Returns:
            A dictionary mapping tool names to their executing callables.
        """
        try:
            with open(filepath, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            logger.error(f"Tools configuration file not found at {filepath}")
            return {}

        tools_registry = {}
        tools_config = data.get("tools", {})

        for tool_name, tool_data in tools_config.items():
            try:
                # Ensure it conforms to ToolConfigType
                parsed_config = ToolConfigType(
                    type=tool_data.get("type"), config=tool_data.get("config", {})
                )
            except Exception as e:
                logger.error(f"Invalid tool configuration structure for '{tool_name}': {e}")
                continue

            if not parsed_config.type:
                logger.error(f"Tool '{tool_name}' missing 'type' in config. Skipping.")
                continue

            try:
                tool_instance = cls.create(parsed_config.type, parsed_config.config)
                tools_registry[tool_name] = tool_instance.get_callable()
            except Exception as e:
                logger.error(f"Failed to instantiate tool '{tool_name}': {e}")

        return tools_registry
