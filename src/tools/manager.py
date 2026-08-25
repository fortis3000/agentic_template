"""Unified Tool and MCP Manager subsystem.

Provides a single entry point for managing, resolving, wrapping, and executing
both local Python tools and external MCP server integrations.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar, Type

from pydantic_ai.tools import Tool

from src.agents.tracing import trace_tool
from src.tools.local.base import ToolFactory
from src.tools.local.vectordb_base import VectorDBFactory
from src.tools.mcp.client import McpServerFactory, make_mcp_tool_callable
from src.tools.mcp.manager import McpConnectionManager
from src.utils.logger import get_logger
from src.utils.retry import RetryConfig, wrap_tool_with_retry

if TYPE_CHECKING:
    from src.agents.config import AgentConfigSchema

logger = get_logger(__name__)


class ToolManager:
    """Unified manager and orchestrator for local tools and external MCP server integrations."""

    tool_factory: ClassVar[Type[ToolFactory]] = ToolFactory
    mcp_factory: ClassVar[Type[McpServerFactory]] = McpServerFactory
    mcp_manager: ClassVar[Type[McpConnectionManager]] = McpConnectionManager
    vectordb_factory: ClassVar[Type[VectorDBFactory]] = VectorDBFactory

    @classmethod
    def load_local_tools(cls, filepath: str, strict: bool = True) -> dict[str, Callable[..., Any]]:
        """Load local tools from a YAML configuration file."""
        return cls.tool_factory.load_from_yaml(filepath, strict=strict)

    @classmethod
    async def fetch_mcp_tools(cls, config: Any) -> list[dict[str, Any]]:
        """Asynchronously fetch tools from an external MCP server configuration."""
        return await cls.mcp_factory.fetch_tools(config)

    @classmethod
    def fetch_mcp_tools_sync(cls, config: Any) -> list[dict[str, Any]]:
        """Synchronously fetch tools from an external MCP server configuration."""
        return cls.mcp_factory.fetch_tools_sync(config)

    @classmethod
    def build_mcp_tool(
        cls, config: Any, tool_name: str, description: str | None = None
    ) -> Callable[..., Any]:
        """Create a callable function that invokes an MCP tool on an active session."""
        return make_mcp_tool_callable(config, tool_name, description=description)

    @classmethod
    async def resolve_tools(
        cls,
        config: "AgentConfigSchema | None" = None,
        *,
        tool_names: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        tool_settings: dict[str, Any] | None = None,
        retry_config: RetryConfig | None = None,
        tools_registry: dict[str, Callable[..., Any]] | None = None,
        tools_config_path: str | None = None,
    ) -> list[Any]:
        """Asynchronously resolve, wrap, and instantiate all local and MCP tools for an agent.

        Discovers MCP tools asynchronously without blocking the event loop.
        """
        tools_list, resolved_registry, names, servers, settings, global_retry = cls._extract_params(
            config=config,
            tool_names=tool_names,
            mcp_servers=mcp_servers,
            tool_settings=tool_settings,
            retry_config=retry_config,
            tools_registry=tools_registry,
            tools_config_path=tools_config_path,
        )

        # 1. Resolve local tools
        cls._resolve_local_tools(tools_list, names, resolved_registry, settings, global_retry)

        # 2. Resolve MCP tools asynchronously
        mcp_tools_by_server = {
            server_name: await cls.mcp_factory.fetch_tools(server_cfg)
            for server_name, server_cfg in servers.items()
        }
        cls._append_mcp_tools(tools_list, servers, mcp_tools_by_server, settings, global_retry)

        return tools_list

    @classmethod
    def resolve_tools_sync(
        cls,
        config: "AgentConfigSchema | None" = None,
        *,
        tool_names: list[str] | None = None,
        mcp_servers: dict[str, Any] | None = None,
        tool_settings: dict[str, Any] | None = None,
        retry_config: RetryConfig | None = None,
        tools_registry: dict[str, Callable[..., Any]] | None = None,
        tools_config_path: str | None = None,
    ) -> list[Any]:
        """Synchronously resolve, wrap, and instantiate all local and MCP tools for an agent.

        Discovers MCP tools using worker threads. Callers on an event loop should use `resolve_tools`.
        """
        tools_list, resolved_registry, names, servers, settings, global_retry = cls._extract_params(
            config=config,
            tool_names=tool_names,
            mcp_servers=mcp_servers,
            tool_settings=tool_settings,
            retry_config=retry_config,
            tools_registry=tools_registry,
            tools_config_path=tools_config_path,
        )

        # 1. Resolve local tools
        cls._resolve_local_tools(tools_list, names, resolved_registry, settings, global_retry)

        # 2. Resolve MCP tools synchronously
        mcp_tools_by_server = {
            server_name: cls.mcp_factory.fetch_tools_sync(server_cfg)
            for server_name, server_cfg in servers.items()
        }
        cls._append_mcp_tools(tools_list, servers, mcp_tools_by_server, settings, global_retry)

        return tools_list

    @classmethod
    def _extract_params(
        cls,
        config: "AgentConfigSchema | None",
        tool_names: list[str] | None,
        mcp_servers: dict[str, Any] | None,
        tool_settings: dict[str, Any] | None,
        retry_config: RetryConfig | None,
        tools_registry: dict[str, Callable[..., Any]] | None,
        tools_config_path: str | None,
    ) -> tuple[
        list[Any],
        dict[str, Callable[..., Any]],
        list[str],
        dict[str, Any],
        dict[str, Any],
        RetryConfig | None,
    ]:
        resolved_names = tool_names if tool_names is not None else (config.tools if config else [])
        resolved_servers = (
            mcp_servers if mcp_servers is not None else (config.mcp_servers if config else {})
        )
        resolved_settings = (
            tool_settings if tool_settings is not None else (config.tool_settings if config else {})
        )
        resolved_retry = (
            retry_config if retry_config is not None else (config.retry if config else None)
        )

        resolved_registry = {**(tools_registry or {})}
        if tools_config_path:
            resolved_registry.update(cls.tool_factory.load_from_yaml(tools_config_path))

        tools_list: list[Any] = []
        return (
            tools_list,
            resolved_registry,
            resolved_names,
            resolved_servers,
            resolved_settings,
            resolved_retry,
        )

    @classmethod
    def _resolve_local_tools(
        cls,
        tools_list: list[Any],
        names: list[str],
        registry: dict[str, Callable[..., Any]],
        settings: dict[str, Any],
        global_retry: RetryConfig | None,
    ) -> None:
        effective_retry = global_retry or RetryConfig()
        for tool_name in names:
            if tool_name not in registry:
                raise ValueError(
                    f"Tool '{tool_name}' listed in config but not provided in tools_registry."
                )

            tool_setting = settings.get(tool_name)
            tool_retry = (
                getattr(tool_setting, "retry", None)
                if not isinstance(tool_setting, dict)
                else tool_setting.get("retry")
            )

            wrapped_tool = wrap_tool_with_retry(registry[tool_name], effective_retry, tool_retry)
            tools_list.append(trace_tool(wrapped_tool))

    @classmethod
    def _append_mcp_tools(
        cls,
        tools_list: list[Any],
        servers: dict[str, Any],
        mcp_tools_by_server: dict[str, list[dict[str, Any]]],
        settings: dict[str, Any],
        global_retry: RetryConfig | None,
    ) -> None:
        effective_retry = global_retry or RetryConfig()
        for mcp_name, mcp_tools in mcp_tools_by_server.items():
            mcp_cfg = servers[mcp_name]
            for tool_info in mcp_tools:
                tool_name = tool_info["name"]

                tool_setting = settings.get(tool_name)
                tool_retry = (
                    getattr(tool_setting, "retry", None)
                    if not isinstance(tool_setting, dict)
                    else tool_setting.get("retry")
                )

                # Create wrapper callable and wrap it with retry
                mcp_callable = make_mcp_tool_callable(
                    mcp_cfg, tool_name, tool_info.get("description")
                )
                wrapped_mcp_callable = wrap_tool_with_retry(
                    mcp_callable, effective_retry, tool_retry
                )

                # Trace tool
                traced_mcp_callable = trace_tool(wrapped_mcp_callable)

                # Wrap in Pydantic AI Tool using schema
                schema = tool_info.get("input_schema") or {}
                pydantic_tool = Tool.from_schema(
                    function=traced_mcp_callable,
                    name=tool_name,
                    description=tool_info.get("description"),
                    json_schema=schema,
                )
                tools_list.append(pydantic_tool)

    @classmethod
    async def close_all(cls) -> None:
        """Clean up and close all persistent MCP sessions and connections."""
        await cls.mcp_manager.close_all()
