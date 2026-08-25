"""Deprecated client module. Use src.tools.mcp.client instead."""

import warnings

from src.tools.mcp.client import McpServerFactory, make_mcp_tool_callable

warnings.warn(
    "src.mcp_integration.client is deprecated; use src.tools.mcp.client instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["McpServerFactory", "make_mcp_tool_callable"]
