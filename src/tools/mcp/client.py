import asyncio
from collections.abc import Callable
from typing import Any, ClassVar

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.tools.contracts.mcp import McpToolDefinition
from src.tools.mcp.manager import McpConnectionManager, build_session_key
from src.tools.mcp.server import parse_http_server_kwargs, parse_stdio_server_parameters
from src.utils.logger import get_logger

__all__ = ["McpServerFactory", "McpToolDefinition", "make_mcp_tool_callable"]

logger = get_logger(__name__)


def make_mcp_tool_callable(
    config: Any, tool_name: str, description: str | None = None
) -> Callable[..., Any]:
    """Generates an async function that connects to the MCP server and invokes the tool."""

    async def call_mcp_tool(**kwargs: Any) -> str:
        cfg_type = getattr(config, "type", "stdio")
        logger.info(f"Invoking MCP tool '{tool_name}' (type: {cfg_type})...")
        session = await McpConnectionManager.get_session(config)
        result = await session.call_tool(tool_name, kwargs)
        text_parts = [
            part.text
            for part in result.content
            if hasattr(part, "text") and isinstance(part.text, str)
        ]
        return "\n".join(text_parts)

    # Set name and docstring to the MCP metadata: agent SDKs derive the advertised
    # tool name and description from these attributes.
    call_mcp_tool.__name__ = tool_name
    call_mcp_tool.__doc__ = description
    return call_mcp_tool


class McpServerFactory:
    """Factory to manage fetching tools from external MCP servers and wrapping them for agents."""

    _tool_cache: ClassVar[dict[str, list[dict[str, Any]]]] = {}

    @staticmethod
    def _config_key(config: Any) -> str:
        """Generate a cache key from MCP server configuration."""
        return build_session_key(config)

    @classmethod
    async def fetch_tools(cls, config: Any) -> list[dict[str, Any]]:
        """Asynchronously connect to an MCP server, list its tools, apply filters, and return metadata.

        Results are cached per config key to avoid redundant connections.
        """
        cache_key = cls._config_key(config)
        if cache_key in cls._tool_cache:
            logger.info(f"Using cached MCP tools for key: {cache_key}")
            return cls._tool_cache[cache_key]

        cfg_type = getattr(config, "type", "stdio")
        if cfg_type == "stdio":
            command = getattr(config, "command", None)
            if not command:
                logger.warning("No command specified for stdio MCP server configuration. Skipping.")
                return []
            params = parse_stdio_server_parameters(config)
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    parsed = cls._filter_and_parse_tools(result.tools, config)
                    cls._tool_cache[cache_key] = parsed
                    return parsed
        elif cfg_type == "http":
            url = getattr(config, "url", None)
            if not url:
                logger.warning("No URL specified for HTTP/SSE MCP server configuration. Skipping.")
                return []
            kwargs = parse_http_server_kwargs(config)
            async with sse_client(**kwargs) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    parsed = cls._filter_and_parse_tools(result.tools, config)
                    cls._tool_cache[cache_key] = parsed
                    return parsed
        else:
            logger.warning(f"Unsupported MCP server connection type: {cfg_type}")
            return []

    @staticmethod
    def _filter_and_parse_tools(tools: list[Any], config: Any) -> list[dict[str, Any]]:
        """Filters and formats list of raw MCP tools into metadata schemas."""
        parsed_tools = []
        enabled_tools = getattr(config, "enabled_tools", None)
        disabled_tools = getattr(config, "disabled_tools", None)

        for tool in tools:
            name = tool.name
            # Apply enabled/disabled filters
            if enabled_tools is not None and name not in enabled_tools:
                continue
            if disabled_tools is not None and name in disabled_tools:
                continue

            schema = getattr(tool, "inputSchema", None) or getattr(tool, "input_schema", None)
            if hasattr(schema, "model_dump"):
                schema = schema.model_dump()
            elif hasattr(schema, "dict"):
                schema = schema.dict()

            parsed_tools.append(
                {
                    "name": name,
                    "description": getattr(tool, "description", None),
                    "input_schema": schema,
                }
            )
        return parsed_tools

    @classmethod
    def fetch_tools_sync(cls, config: Any) -> list[dict[str, Any]]:
        """Synchronously fetch tools from an MCP server configuration.

        Intended for scripts and other synchronous entry points. Callers already running on an
        event loop must use the async :meth:`fetch_tools` instead — the thread hand-off below
        blocks the calling thread until the MCP server has started.
        """
        import concurrent.futures  # noqa: PLC0415

        cache_key = cls._config_key(config)
        if cache_key in cls._tool_cache:
            logger.info(f"Using cached MCP tools for key: {cache_key}")
            return cls._tool_cache[cache_key]

        def run_in_thread():
            return asyncio.run(cls.fetch_tools(config))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()
