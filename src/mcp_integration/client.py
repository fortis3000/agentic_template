import asyncio
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.mcp_integration.manager import McpConnectionManager
from src.mcp_integration.server import parse_http_server_kwargs, parse_stdio_server_parameters
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


def make_mcp_tool_callable(config: Any, tool_name: str) -> Callable[..., Any]:
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

    # Set name of the function to the tool name for docstrings and mapping
    call_mcp_tool.__name__ = tool_name
    return call_mcp_tool


class McpServerFactory:
    """Factory to manage fetching tools from external MCP servers and wrapping them for agents."""

    @staticmethod
    async def fetch_tools(config: Any) -> list[dict[str, Any]]:
        """Asynchronously connect to an MCP server, list its tools, apply filters, and return metadata."""
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
                    return McpServerFactory._filter_and_parse_tools(result.tools, config)
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
                    return McpServerFactory._filter_and_parse_tools(result.tools, config)
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
        """Synchronously fetch tools from an MCP server configuration without blocking the main event loop."""
        import concurrent.futures  # noqa: PLC0415

        def run_in_thread():
            return asyncio.run(cls.fetch_tools(config))

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result()
