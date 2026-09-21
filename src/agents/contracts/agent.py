"""Protocols for agent execution and runners."""

from abc import abstractmethod
from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AgentRunnerProtocol(Protocol):
    """Protocol for executing agent interactions asynchronously or synchronously."""

    @abstractmethod
    async def call(self, inputs: list[Any]) -> str:
        """Asynchronously call the agent."""
        ...

    @abstractmethod
    def call_sync(self, inputs: list[Any]) -> str:
        """Synchronously call the agent."""
        ...

    @abstractmethod
    async def call_stream(self, inputs: list[Any]) -> AsyncIterator[str]:
        """Asynchronously stream the agent response."""
        ...
