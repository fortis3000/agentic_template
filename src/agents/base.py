from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Union

import nest_asyncio
from pydantic import BaseModel, FilePath, model_validator

if TYPE_CHECKING:
    from src.agents.config import AgentYamlConfig


class TextPart(BaseModel):
    """Represents a text input part for the agent."""

    text: str


class ImagePart(BaseModel):
    """Represents an image input part for the agent, supporting raw bytes or file paths."""

    data: bytes | None = None
    path: FilePath | None = None
    mime_type: str | None = None

    @model_validator(mode="after")
    def validate_has_data_or_path(self) -> "ImagePart":
        if self.data is None and self.path is None:
            raise ValueError("ImagePart must have either data or path defined.")
        return self

    @classmethod
    def from_file(cls, path: str, mime_type: str | None = None) -> "ImagePart":
        return cls(path=Path(path), mime_type=mime_type)

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str) -> "ImagePart":
        return cls(data=data, mime_type=mime_type)


class FilePart(BaseModel):
    """Represents a text file input part for the agent."""

    data: bytes | None = None
    path: FilePath | None = None
    mime_type: str
    filename: str

    @model_validator(mode="after")
    def validate_has_data_or_path(self) -> "FilePart":
        if self.data is None and self.path is None:
            raise ValueError("FilePart must have either data or path defined.")
        return self

    @classmethod
    def from_file(cls, path: str, mime_type: str, filename: str | None = None) -> "FilePart":
        p = Path(path)
        return cls(path=p, mime_type=mime_type, filename=filename or p.name)

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str, filename: str) -> "FilePart":
        return cls(data=data, mime_type=mime_type, filename=filename)


# Union type representing any valid input part to an agent.
AgentInputPart = Union[TextPart, ImagePart, FilePart, str]


@dataclass
class ToolConfig:
    """Placeholder configuration structure for tools."""

    name: str
    description: str | None = None
    parameters: dict | None = None


@dataclass
class McpServerConfig:
    """Placeholder configuration structure for MCP servers."""

    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None


class BaseAgent(ABC):
    """Abstract base class representing an SDK-agnostic agent."""

    @abstractmethod
    async def call(self, inputs: list[AgentInputPart]) -> str:
        """Asynchronously call the agent with multimodal inputs and return the final response string.

        Args:
            inputs: A list of input parts (text or images).

        Returns:
            The final text response from the agent.
        """
        pass

    def call_sync(self, inputs: list[AgentInputPart]) -> str:
        """Synchronously call the agent with multimodal inputs.

        Args:
            inputs: A list of input parts (text or images).

        Returns:
            The final text response from the agent.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # If an event loop is already running, use run_coroutine_threadsafe or a wrapper
            # But in typical script environment, we can run it.
            # Let's run it using a clean runner or standard run.
            nest_asyncio.apply()
        return asyncio.run(self.call(inputs))

    @abstractmethod
    async def call_stream(self, inputs: list[AgentInputPart]) -> AsyncIterator[str]:
        """Asynchronously call the agent and stream the text response.

        Args:
            inputs: A list of input parts (text or images).

        Yields:
            Chunks of the text response as they are generated.
        """
        if False:
            yield ""


class BaseAgentGenerator(ABC):
    """Abstract base class representing an agent factory/generator that spawns agents from configs."""

    @abstractmethod
    def create_agent(
        self,
        config: Union[str, "AgentYamlConfig"],
        system_variables: dict[str, Any] | None = None,
        tools_registry: dict[str, Any] | None = None,
        tools_config_path: str | None = None,
        **kwargs: Any,
    ) -> BaseAgent:
        """Create and configure an agent from a configuration file or pre-loaded config.

        Args:
            config: Path to the agent configuration file (e.g. YAML) or pre-loaded AgentYamlConfig.
            system_variables: Optional variables to format the system prompt template.
            tools_registry: Optional mapping of tool names to Python callables.
            tools_config_path: Optional path to a YAML file to load tools via ToolFactory.
            **kwargs: Extra parameters to override configuration fields dynamically.

        Returns:
            An instance of BaseAgent.
        """
        pass
