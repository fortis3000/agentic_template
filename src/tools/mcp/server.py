"""MCP Server parameter parsing and schema definitions."""

from typing import TYPE_CHECKING, Any

from mcp import StdioServerParameters

if TYPE_CHECKING:
    pass


def parse_stdio_server_parameters(config: Any) -> StdioServerParameters:
    """Convert McpServerConfigSchema into stdio StdioServerParameters."""
    command = getattr(config, "command", None)
    args = getattr(config, "args", None)
    env = getattr(config, "env", None)
    if not command:
        raise ValueError("command must be specified for stdio MCP server connection")
    return StdioServerParameters(
        command=command,
        args=args or [],
        env=env,
    )


def parse_http_server_kwargs(config: Any) -> dict[str, Any]:
    """Extract HTTP / SSE client connection parameters."""
    url = getattr(config, "url", None)
    headers = getattr(config, "headers", None)
    timeout = getattr(config, "timeout", None)
    if not url:
        raise ValueError("url must be specified for http MCP server connection")
    return {
        "url": url,
        "headers": headers,
        "timeout": timeout,
    }
