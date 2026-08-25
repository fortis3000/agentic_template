"""Deprecated manager module. Use src.tools.mcp.manager instead."""

import warnings

from src.tools.mcp.manager import (
    SHUTDOWN_TIMEOUT,
    McpConnectionManager,
    build_session_key,
)

warnings.warn(
    "src.mcp_integration.manager is deprecated; use src.tools.mcp.manager instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["McpConnectionManager", "SHUTDOWN_TIMEOUT", "build_session_key"]
