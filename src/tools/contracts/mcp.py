"""Contracts and data models for Model Context Protocol (MCP) tools."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpToolDefinition:
    """Framework-neutral descriptor for an external MCP tool."""

    name: str
    callable: Callable[..., Any]
    description: str | None = None
    input_schema: dict[str, Any] = field(default_factory=dict)
