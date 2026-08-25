import importlib
import warnings
from unittest.mock import AsyncMock, patch

import pytest
from pydantic_ai.tools import Tool

import src.mcp_integration
from src.agents.config import AgentConfigSchema, McpServerConfigSchema, ToolSettingsSchema
from src.tools.local.base import BaseTool, ToolFactory
from src.tools.local.vectordb_base import VectorDBFactory
from src.tools.manager import ToolManager
from src.tools.mcp.client import McpServerFactory
from src.tools.mcp.manager import McpConnectionManager
from src.utils.retry import RetryConfig

EXPECTED_ASYNC_RESOLVED_COUNT = 3
EXPECTED_SYNC_RESOLVED_COUNT = 2


@pytest.fixture(autouse=True)
def clear_tool_factory_registry():
    saved = dict(ToolFactory._registry)
    yield
    ToolFactory._registry = saved


def test_tool_manager_subcomponent_attributes():
    """Verify ToolManager exposes class references to all underlying factories and managers."""
    assert ToolManager.tool_factory is ToolFactory
    assert ToolManager.mcp_factory is McpServerFactory
    assert ToolManager.mcp_manager is McpConnectionManager
    assert ToolManager.vectordb_factory is VectorDBFactory


def test_tool_manager_load_local_tools(tmp_path):
    """Verify ToolManager.load_local_tools loads and instantiates tools from YAML."""

    @ToolFactory.register("manager_test_tool")
    class ManagerTestTool(BaseTool):
        def __init__(self, greeting: str):
            self.greeting = greeting

        def get_callable(self):
            def execute():
                return self.greeting

            return execute

    yaml_file = tmp_path / "tools.yaml"
    yaml_file.write_text(
        """
tools:
  greet_tool:
    type: "manager_test_tool"
    config:
      greeting: "hello from manager"
"""
    )

    loaded = ToolManager.load_local_tools(str(yaml_file))
    assert "greet_tool" in loaded
    assert callable(loaded["greet_tool"])
    assert loaded["greet_tool"]() == "hello from manager"


@pytest.mark.asyncio
async def test_tool_manager_resolve_tools_async_local_and_mcp(tmp_path):
    """Verify ToolManager.resolve_tools resolves both local tools and MCP tools asynchronously."""

    def mock_local_func(x: int) -> int:
        return x * 2

    # Prepare local tool config YAML
    @ToolFactory.register("multiplier_tool")
    class MultiplierTool(BaseTool):
        def __init__(self, factor: int = 3):
            self.factor = factor

        def get_callable(self):
            def multiply(val: int) -> int:
                return val * self.factor

            return multiply

    yaml_file = tmp_path / "extra_tools.yaml"
    yaml_file.write_text(
        """
tools:
  yaml_tool:
    type: "multiplier_tool"
    config:
      factor: 5
"""
    )

    mcp_cfg = McpServerConfigSchema(type="stdio", command="dummy_server")
    agent_config = AgentConfigSchema(
        name="test_agent",
        provider="google",
        tools=["local_tool", "yaml_tool"],
        mcp_servers={"server1": mcp_cfg},
        tool_settings={"local_tool": ToolSettingsSchema(retry=RetryConfig(attempts=2, delay=0.1))},
        retry=RetryConfig(attempts=1, delay=0.0),
    )

    discovered_mcp_tools = [
        {
            "name": "remote_echo",
            "description": "Echoes back text",
            "input_schema": {"type": "object", "properties": {"msg": {"type": "string"}}},
        }
    ]

    with patch.object(
        McpServerFactory, "fetch_tools", AsyncMock(return_value=discovered_mcp_tools)
    ):
        resolved = await ToolManager.resolve_tools(
            agent_config,
            tools_registry={"local_tool": mock_local_func},
            tools_config_path=str(yaml_file),
        )

    # We expect 2 local tools (callables/functions) + 1 MCP tool (Pydantic AI Tool instance)
    assert len(resolved) == EXPECTED_ASYNC_RESOLVED_COUNT

    # Local tools
    assert callable(resolved[0])
    assert callable(resolved[1])

    # MCP tool
    assert isinstance(resolved[2], Tool)
    assert resolved[2].name == "remote_echo"


def test_tool_manager_resolve_tools_sync(tmp_path):
    """Verify ToolManager.resolve_tools_sync resolves tools synchronously."""

    def mock_local(s: str) -> str:
        return f"Echo: {s}"

    agent_config = AgentConfigSchema(
        name="sync_agent",
        provider="google",
        tools=["local_sync_tool"],
        mcp_servers={"s1": McpServerConfigSchema(type="stdio", command="echo")},
    )

    mcp_tools = [
        {
            "name": "mcp_sync_tool",
            "description": "Sync MCP tool",
            "input_schema": {"type": "object"},
        }
    ]

    with patch.object(McpServerFactory, "fetch_tools_sync", return_value=mcp_tools):
        resolved = ToolManager.resolve_tools_sync(
            agent_config,
            tools_registry={"local_sync_tool": mock_local},
        )

    assert len(resolved) == EXPECTED_SYNC_RESOLVED_COUNT
    assert callable(resolved[0])
    assert isinstance(resolved[1], Tool)
    assert resolved[1].name == "mcp_sync_tool"


@pytest.mark.asyncio
async def test_tool_manager_resolve_tools_missing_tool_raises():
    """Verify ToolManager raises ValueError when a requested tool is missing from registry."""
    agent_config = AgentConfigSchema(
        name="missing_tool_agent",
        provider="google",
        tools=["non_existent_tool"],
    )

    with pytest.raises(
        ValueError, match="Tool 'non_existent_tool' listed in config but not provided"
    ):
        await ToolManager.resolve_tools(agent_config, tools_registry={})


@pytest.mark.asyncio
async def test_tool_manager_close_all():
    """Verify ToolManager.close_all delegates to McpConnectionManager.close_all."""
    with patch.object(McpConnectionManager, "close_all", AsyncMock()) as mock_close:
        await ToolManager.close_all()
        mock_close.assert_awaited_once()


def test_mcp_integration_backward_compatibility_deprecation():
    """Verify that importing from src.mcp_integration issues a DeprecationWarning and re-exports symbols."""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        importlib.reload(src.mcp_integration)

        assert len(recorded) >= 1
        assert any(
            issubclass(w.category, DeprecationWarning)
            and "src.mcp_integration is deprecated" in str(w.message)
            for w in recorded
        )
        assert src.mcp_integration.McpConnectionManager is McpConnectionManager
        assert src.mcp_integration.McpServerFactory is McpServerFactory
