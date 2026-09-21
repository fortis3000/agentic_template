"""Contracts and protocols for tools."""

from abc import abstractmethod
from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

type ToolCallable = Callable[..., Any]
type ToolRegistry = dict[str, ToolCallable]


@runtime_checkable
class BaseToolProtocol(Protocol):
    """Protocol representing a tool providing an executable callable."""

    @abstractmethod
    def get_callable(self) -> ToolCallable:
        """Return the function or method that executes the tool."""
        ...
