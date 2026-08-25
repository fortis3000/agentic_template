"""Model Context Protocol (MCP) integration package providing client session management and server configuration helpers."""

from src.tools.mcp.client import McpServerFactory, make_mcp_tool_callable
from src.tools.mcp.manager import (
    SHUTDOWN_TIMEOUT,
    McpConnectionManager,
    build_session_key,
)
from src.tools.mcp.server import (
    parse_http_server_kwargs,
    parse_stdio_server_parameters,
)

__all__ = [
    "McpConnectionManager",
    "McpServerFactory",
    "SHUTDOWN_TIMEOUT",
    "build_session_key",
    "make_mcp_tool_callable",
    "parse_http_server_kwargs",
    "parse_stdio_server_parameters",
]
