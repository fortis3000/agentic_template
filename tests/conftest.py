import pytest

from src.mcp_integration.client import McpServerFactory
from src.mcp_integration.manager import McpConnectionManager


@pytest.fixture(autouse=True)
def mock_mcp_fetching(monkeypatch):
    """Automatically mock MCP tool fetching to avoid spinning up external subprocesses/processes in tests."""
    monkeypatch.setattr(McpServerFactory, "fetch_tools_sync", lambda config: [])

    async def mock_fetch_tools(config):
        return []

    monkeypatch.setattr(McpServerFactory, "fetch_tools", mock_fetch_tools)


@pytest.fixture(autouse=True)
def reset_mcp_state():
    """Clear MCP connection and tool caches so state never leaks between tests.

    Both are class-level dicts, and a session is bound to the event loop that created it — without
    this, a session cached by one test would be handed to the next test running on a different loop.
    """
    yield
    for owner_task in McpConnectionManager._owner_tasks.values():
        owner_task.cancel()
    McpConnectionManager._sessions.clear()
    McpConnectionManager._owner_tasks.clear()
    McpConnectionManager._stop_events.clear()
    McpServerFactory._tool_cache.clear()
