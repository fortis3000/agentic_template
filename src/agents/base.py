import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Union

import nest_asyncio


@dataclass
class TextPart:
    """Represents a text input part for the agent."""

    text: str


@dataclass
class ImagePart:
    """Represents an image input part for the agent, supporting raw bytes or file paths."""

    data: bytes | None = None
    path: str | None = None
    mime_type: str | None = None

    @classmethod
    def from_file(cls, path: str, mime_type: str | None = None) -> "ImagePart":
        return cls(path=path, mime_type=mime_type)

    @classmethod
    def from_bytes(cls, data: bytes, mime_type: str) -> "ImagePart":
        return cls(data=data, mime_type=mime_type)


# Union type representing any valid input part to an agent.
AgentInputPart = Union[TextPart, ImagePart, str]


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
    def create_agent(self, config_path: str) -> BaseAgent:
        """Create and configure an agent from a configuration file.

        Args:
            config_path: Path to the agent configuration file (e.g. YAML).

        Returns:
            An instance of BaseAgent.
        """
        pass
