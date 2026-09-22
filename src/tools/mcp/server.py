"""MCP Server parameter parsing and schema definitions."""

from typing import TYPE_CHECKING, Any

from mcp import StdioServerParameters

try:
    import httpx2

    _ASYNC_HTTP_CLIENT_CLS = httpx2.AsyncClient
except ImportError:
    import httpx

    _ASYNC_HTTP_CLIENT_CLS = httpx.AsyncClient

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


def create_mcp_http_client(
    headers: dict[str, str] | None = None,
    timeout: Any = None,
    auth: Any = None,
) -> Any:
    """Create an async HTTP client for MCP SSE communication using httpx2 (with httpx fallback)."""
    kwargs: dict[str, Any] = {"follow_redirects": True}
    if headers is not None:
        kwargs["headers"] = headers
    if timeout is not None:
        kwargs["timeout"] = timeout
    if auth is not None:
        kwargs["auth"] = auth
    return _ASYNC_HTTP_CLIENT_CLS(**kwargs)


def parse_http_server_kwargs(config: Any) -> dict[str, Any]:
    """Extract HTTP / SSE client connection parameters using httpx2."""
    url = getattr(config, "url", None)
    headers = getattr(config, "headers", None)
    timeout = getattr(config, "timeout", None)
    sse_read_timeout = getattr(config, "sse_read_timeout", None)
    if not url:
        raise ValueError("url must be specified for http MCP server connection")
    res: dict[str, Any] = {
        "url": url,
        "headers": headers,
        "httpx_client_factory": create_mcp_http_client,
    }
    if timeout is not None:
        res["timeout"] = timeout
    if sse_read_timeout is not None:
        res["sse_read_timeout"] = sse_read_timeout
    return res
