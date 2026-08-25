"""Deprecated server module. Use src.tools.mcp.server instead."""

import warnings

from src.tools.mcp.server import (
    parse_http_server_kwargs,
    parse_stdio_server_parameters,
)

warnings.warn(
    "src.mcp_integration.server is deprecated; use src.tools.mcp.server instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["parse_http_server_kwargs", "parse_stdio_server_parameters"]
