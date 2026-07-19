import pytest

from src.agents.mcp import McpServerFactory


@pytest.fixture(autouse=True)
def mock_mcp_fetching(monkeypatch):
    """Automatically mock MCP tool fetching to avoid spinning up external subprocesses/processes in tests."""
    monkeypatch.setattr(McpServerFactory, "fetch_tools_sync", lambda config: [])

    async def mock_fetch_tools(config):
        return []

    monkeypatch.setattr(McpServerFactory, "fetch_tools", mock_fetch_tools)
