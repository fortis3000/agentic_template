"""Leaf contracts package for tools with zero internal dependencies."""

from src.tools.contracts.config import AgentToolConfigProtocol, ToolSettingsProtocol
from src.tools.contracts.mcp import McpToolDefinition
from src.tools.contracts.tool import BaseToolProtocol, ToolCallable, ToolRegistry

__all__ = [
    "AgentToolConfigProtocol",
    "BaseToolProtocol",
    "McpToolDefinition",
    "ToolCallable",
    "ToolRegistry",
    "ToolSettingsProtocol",
]
