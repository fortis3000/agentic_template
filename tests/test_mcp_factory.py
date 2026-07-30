from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.config import McpServerConfigSchema
from src.mcp_integration import McpServerFactory, make_mcp_tool_callable


@pytest.mark.asyncio
async def test_mcp_server_factory_filtering():
    """Verify that McpServerFactory filters tools correctly based on enabled/disabled lists."""
    mock_tool_1 = MagicMock()
    mock_tool_1.name = "allowed_tool"
    mock_tool_1.description = "Allowed"
    mock_tool_1.inputSchema = {"type": "object"}

    mock_tool_2 = MagicMock()
    mock_tool_2.name = "blocked_tool"
    mock_tool_2.description = "Blocked"
    mock_tool_2.inputSchema = {"type": "object"}

    raw_tools = [mock_tool_1, mock_tool_2]

    # Test enabled_tools whitelist
    cfg_whitelist = McpServerConfigSchema(
        type="stdio",
        command="node",
        enabled_tools=["allowed_tool"],
    )
    res = McpServerFactory._filter_and_parse_tools(raw_tools, cfg_whitelist)
    assert len(res) == 1
    assert res[0]["name"] == "allowed_tool"

    # Test disabled_tools blacklist
    cfg_blacklist = McpServerConfigSchema(
        type="stdio",
        command="node",
        disabled_tools=["blocked_tool"],
    )
    res2 = McpServerFactory._filter_and_parse_tools(raw_tools, cfg_blacklist)
    assert len(res2) == 1
    assert res2[0]["name"] == "allowed_tool"


@pytest.mark.asyncio
async def test_make_mcp_tool_callable_stdio():
    """Test that stdio MCP tool wrapper invokes client sessions correctly."""
    cfg = McpServerConfigSchema(
        type="stdio",
        command="node",
        args=["index.js"],
    )

    mock_result = MagicMock()
    mock_part = MagicMock()
    mock_part.text = "mcp tool call result text"
    mock_result.content = [mock_part]

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=mock_result)

    # Patch client connection and session
    with (
        patch("src.mcp_integration.manager.stdio_client") as mock_stdio,
        patch("src.mcp_integration.manager.ClientSession") as mock_client_session,
    ):
        mock_stdio.return_value.__aenter__.return_value = ("read", "write")
        mock_client_session.return_value = mock_session

        mcp_tool = make_mcp_tool_callable(cfg, "my_mcp_tool")
        res = await mcp_tool(arg1="value1")

        assert res == "mcp tool call result text"
        mock_session.initialize.assert_awaited_once()
        mock_session.call_tool.assert_awaited_once_with("my_mcp_tool", {"arg1": "value1"})
