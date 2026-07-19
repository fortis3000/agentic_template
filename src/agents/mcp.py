import asyncio
from collections.abc import Callable
from typing import Any

import nest_asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.agents.config import McpServerConfigSchema
from src.utils.logger import get_logger

logger = get_logger(__name__)


def make_mcp_tool_callable(config: McpServerConfigSchema, tool_name: str) -> Callable[..., Any]:
    """Generates an async function that connects to the MCP server and invokes the tool."""

    async def call_mcp_tool(**kwargs: Any) -> str:
        logger.info(f"Invoking MCP tool '{tool_name}' (type: {config.type})...")
        if config.type == "stdio":
            if not config.command:
                raise ValueError("command must be specified for stdio MCP server connection")
            params = StdioServerParameters(
                command=config.command,
                args=config.args or [],
                env=config.env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, kwargs)
                    text_parts = [
                        part.text
                        for part in result.content
                        if hasattr(part, "text") and isinstance(part.text, str)
                    ]
                    return "\n".join(text_parts)
        elif config.type == "http":
            if not config.url:
                raise ValueError("url must be specified for http MCP server connection")
            async with sse_client(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, kwargs)
                    text_parts = [
                        part.text
                        for part in result.content
                        if hasattr(part, "text") and isinstance(part.text, str)
                    ]
                    return "\n".join(text_parts)
        else:
            raise ValueError(f"Unsupported MCP server type: {config.type}")

    # Set name of the function to the tool name for docstrings and mapping
    call_mcp_tool.__name__ = tool_name
    return call_mcp_tool


class McpServerFactory:
    """Factory to manage fetching tools from external MCP servers and wrapping them for agents."""

    @staticmethod
    async def fetch_tools(config: McpServerConfigSchema) -> list[dict[str, Any]]:
        """Asynchronously connect to an MCP server, list its tools, apply filters, and return metadata."""
        if config.type == "stdio":
            if not config.command:
                logger.warning("No command specified for stdio MCP server configuration. Skipping.")
                return []
            params = StdioServerParameters(
                command=config.command,
                args=config.args or [],
                env=config.env,
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return McpServerFactory._filter_and_parse_tools(result.tools, config)
        elif config.type == "http":
            if not config.url:
                logger.warning("No URL specified for HTTP/SSE MCP server configuration. Skipping.")
                return []
            async with sse_client(
                url=config.url,
                headers=config.headers,
                timeout=config.timeout,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    return McpServerFactory._filter_and_parse_tools(result.tools, config)
        else:
            logger.warning(f"Unsupported MCP server connection type: {config.type}")
            return []

    @staticmethod
    def _filter_and_parse_tools(
        tools: list[Any], config: McpServerConfigSchema
    ) -> list[dict[str, Any]]:
        """Filters and formats list of raw MCP tools into metadata schemas."""
        parsed_tools = []
        for tool in tools:
            name = tool.name
            # Apply enabled/disabled filters
            if config.enabled_tools is not None and name not in config.enabled_tools:
                continue
            if config.disabled_tools is not None and name in config.disabled_tools:
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
    def fetch_tools_sync(cls, config: McpServerConfigSchema) -> list[dict[str, Any]]:
        """Synchronously fetch tools from an MCP server configuration."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            nest_asyncio.apply()
            return asyncio.run(cls.fetch_tools(config))
        else:
            return asyncio.run(cls.fetch_tools(config))
