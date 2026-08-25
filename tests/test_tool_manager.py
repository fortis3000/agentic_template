import importlib
import warnings
from unittest.mock import AsyncMock, patch

import pytest

import src.mcp_integration
import src.tools.base
import src.tools.google_sheet
import src.tools.google_sheet.write_german_words
import src.tools.qdrant_db
import src.tools.text_extractor
import src.tools.vectordb_base
import src.tools.vectordb_search
from src.agents.config import AgentConfigSchema, McpServerConfigSchema, ToolSettingsSchema
from src.tools.local.base import BaseTool, ToolFactory
from src.tools.local.vectordb_base import VectorDBFactory
from src.tools.manager import ToolManager
from src.tools.mcp.client import McpServerFactory, McpToolDefinition
from src.tools.mcp.manager import McpConnectionManager
from src.utils.retry import RetryConfig

EXPECTED_ASYNC_RESOLVED_COUNT = 3
EXPECTED_SYNC_RESOLVED_COUNT = 2
EXPECTED_PARALLEL_RESOLVED_COUNT = 4


@pytest.fixture(autouse=True)
def restore_tool_factory_registry():
    saved = dict(ToolFactory._registry)
    yield
    ToolFactory._registry.clear()
    ToolFactory._registry.update(saved)


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
async def test_tool_manager_fetch_mcp_tools_and_build_tool():
    """Verify ToolManager.fetch_mcp_tools and build_mcp_tool delegate to McpServerFactory/wrapper."""
    cfg = McpServerConfigSchema(type="stdio", command="node", args=["server.js"])
    mock_tools = [{"name": "read_doc", "description": "Read documentation", "input_schema": {}}]

    with patch.object(McpServerFactory, "fetch_tools", AsyncMock(return_value=mock_tools)):
        fetched = await ToolManager.fetch_mcp_tools(cfg)
        assert fetched == mock_tools

    with patch.object(McpServerFactory, "fetch_tools_sync", return_value=mock_tools):
        fetched_sync = ToolManager.fetch_mcp_tools_sync(cfg)
        assert fetched_sync == mock_tools

    callable_tool = ToolManager.build_mcp_tool(cfg, "read_doc", description="Read documentation")
    assert callable(callable_tool)
    assert getattr(callable_tool, "__name__", None) == "read_doc"
    assert getattr(callable_tool, "__doc__", None) == "Read documentation"


@pytest.mark.asyncio
async def test_tool_manager_resolve_tools_async_local_and_mcp_parallel(tmp_path):
    """Verify ToolManager.resolve_tools resolves local tools and multiple MCP servers in parallel."""

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

    mcp_cfg1 = McpServerConfigSchema(type="stdio", command="dummy_server1")
    mcp_cfg2 = McpServerConfigSchema(type="stdio", command="dummy_server2")
    agent_config = AgentConfigSchema(
        name="test_agent",
        provider="google",
        tools=["local_tool", "yaml_tool"],
        mcp_servers={"server1": mcp_cfg1, "server2": mcp_cfg2},
        tool_settings={
            "local_tool": ToolSettingsSchema(retry=RetryConfig(attempts=2, delay=0.1)),
            "remote_echo": {"retry": RetryConfig(attempts=3, delay=0.2)},  # Test dict branch
        },
        retry=RetryConfig(attempts=1, delay=0.0),
    )

    discovered_mcp_tools1 = [
        {
            "name": "remote_echo",
            "description": "Echoes back text",
            "input_schema": {"type": "object", "properties": {"msg": {"type": "string"}}},
        }
    ]
    discovered_mcp_tools2 = [
        {
            "name": "remote_search",
            "description": "Searches remote database",
            "input_schema": {"type": "object"},
        }
    ]

    async def mock_fetch(cfg: McpServerConfigSchema):
        if cfg.command == "dummy_server1":
            return discovered_mcp_tools1
        return discovered_mcp_tools2

    with patch.object(McpServerFactory, "fetch_tools", side_effect=mock_fetch):
        resolved = await ToolManager.resolve_tools(
            agent_config,
            tools_registry={"local_tool": mock_local_func},
            tools_config_path=str(yaml_file),
        )

    # 2 local tools + 2 MCP tools (McpToolDefinition instances)
    assert len(resolved) == EXPECTED_PARALLEL_RESOLVED_COUNT

    # Local tools
    assert callable(resolved[0])
    assert callable(resolved[1])

    # MCP tools (framework-neutral McpToolDefinition)
    assert isinstance(resolved[2], McpToolDefinition)
    assert resolved[2].name == "remote_echo"
    assert callable(resolved[2].callable)

    assert isinstance(resolved[3], McpToolDefinition)
    assert resolved[3].name == "remote_search"


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
    assert isinstance(resolved[1], McpToolDefinition)
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


@pytest.mark.parametrize(
    "module,expected_attrs",
    [
        (src.tools.base, ["BaseTool", "ToolConfigType", "ToolFactory"]),
        (src.tools.qdrant_db, ["QdrantVectorDB", "generate_sparse_vector"]),
        (src.tools.text_extractor, ["extract_text", "SUPPORTED_MIME_TYPES", "MIME_PDF"]),
        (src.tools.vectordb_base, ["BaseVectorDB", "VectorDBFactory"]),
        (src.tools.vectordb_search, ["VectorDBSearchTool"]),
        (
            src.tools.google_sheet,
            ["GoogleSheetsAddVocabEntryTool", "GoogleSheetsReadTool", "GoogleSheetsWriteTool"],
        ),
        (
            src.tools.google_sheet.write_german_words,
            ["GoogleSheetsAddVocabEntryTool", "GoogleSheetsReadTool", "GoogleSheetsWriteTool"],
        ),
    ],
)
def test_tools_shims_backward_compatibility_deprecation(module, expected_attrs):
    """Verify that all src.tools.* backward-compatibility shims issue DeprecationWarnings and re-export."""
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        importlib.reload(module)

        assert len(recorded) >= 1
        assert any(
            issubclass(w.category, DeprecationWarning) and "is deprecated" in str(w.message)
            for w in recorded
        )
        for attr in expected_attrs:
            assert hasattr(module, attr)
