"""Regression tests for MCP connection ownership and non-blocking tool discovery.

Covers CODE_REVIEW findings 3 (sessions entered and exited from different tasks) and 4
(`fetch_tools_sync` blocking the event loop during agent creation).
"""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.config import McpServerConfigSchema
from src.agents.pydantic_ai import PydanticAIAgentGenerator
from src.tools.mcp.client import McpServerFactory
from src.tools.mcp.manager import McpConnectionManager

AGENT_CONFIG = """
agent:
  name: "test_agent"
  model: "gemini-3.5-flash"
  provider: "google"
  api_key: "test-key"
  system_prompt: "System prompt"
  mcp_servers:
    filesystem:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem"]
"""


class _TransportRecorder:
    """Fake MCP transport that fails if it is closed from a different task than it was opened in.

    This is what `stdio_client` does for real: it is an anyio task-group context manager, and
    exiting one from another task raises
    ``RuntimeError: Attempted to exit cancel scope in a different task than it was entered in``.
    """

    def __init__(self):
        self.opened_in = None
        self.closed = False

    @asynccontextmanager
    async def open(self, *args, **kwargs):
        self.opened_in = asyncio.current_task()
        try:
            yield ("read", "write")
        finally:
            if asyncio.current_task() is not self.opened_in:
                raise RuntimeError(
                    "Attempted to exit cancel scope in a different task than it was entered in"
                )
            self.closed = True


@asynccontextmanager
async def _fake_client_session(read, write):
    session = AsyncMock()
    session.initialize = AsyncMock()
    yield session


@pytest.fixture(autouse=True)
def mock_mcp_fetching():
    """Override the conftest mock so the real discovery and connection code is exercised here."""
    pass


@pytest.fixture
def mcp_config():
    return McpServerConfigSchema(type="stdio", command="npx", args=["-y", "some-server"])


@pytest.mark.asyncio
async def test_session_closed_from_different_task_than_it_was_opened_in(mcp_config):
    """Finding 3: a session opened inside a request task must still close cleanly at shutdown."""
    transport = _TransportRecorder()

    with (
        patch("src.tools.mcp.manager.stdio_client", transport.open),
        patch("src.tools.mcp.manager.ClientSession", _fake_client_session),
    ):
        # Open the connection from a short-lived "request" task, which then exits — mirroring
        # run_agent_in_background invoking an MCP tool.
        request_task = asyncio.create_task(McpConnectionManager.get_session(mcp_config))
        session = await request_task
        assert session is not None
        assert McpConnectionManager._sessions

        # The transport must be owned by a dedicated task, not by the requester.
        assert transport.opened_in is not request_task

        # Shut down from the lifespan task. Before the fix this raised inside close_all().
        await McpConnectionManager.close_all()

    assert transport.closed is True
    assert not McpConnectionManager._sessions
    assert not McpConnectionManager._owner_tasks
    assert not McpConnectionManager._stop_events


@pytest.mark.asyncio
async def test_session_is_reused_across_calls(mcp_config):
    """A second request reuses the live session instead of spawning another subprocess."""
    transport = _TransportRecorder()

    with (
        patch("src.tools.mcp.manager.stdio_client", transport.open),
        patch("src.tools.mcp.manager.ClientSession", _fake_client_session),
    ):
        first = await McpConnectionManager.get_session(mcp_config)
        second = await McpConnectionManager.get_session(mcp_config)
        assert first is second
        assert len(McpConnectionManager._owner_tasks) == 1

        await McpConnectionManager.close_all()


@pytest.mark.asyncio
async def test_failed_connection_is_not_cached(mcp_config):
    """A server that fails to start propagates the error and leaves nothing cached."""

    @asynccontextmanager
    async def failing_transport(*args, **kwargs):
        raise RuntimeError("server failed to start")
        yield  # pragma: no cover

    with patch("src.tools.mcp.manager.stdio_client", failing_transport):
        with pytest.raises(RuntimeError, match="server failed to start"):
            await McpConnectionManager.get_session(mcp_config)

    assert not McpConnectionManager._sessions
    assert not McpConnectionManager._owner_tasks


@pytest.mark.asyncio
async def test_create_agent_async_does_not_block_the_event_loop(tmp_path):
    """Finding 4: MCP discovery must not freeze other coroutines during agent creation."""
    config_file = tmp_path / "agent_config.yaml"
    config_file.write_text(AGENT_CONFIG, encoding="utf-8")

    discovery_time = 0.3
    # A blocked loop leaves the ticker at ~1; a free loop reaches ~30 in that window.
    min_expected_ticks = 10

    async def slow_fetch_tools(config):
        await asyncio.sleep(discovery_time)
        return []

    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    generator = PydanticAIAgentGenerator(prompt_base_dir=tmp_path)

    with patch.object(McpServerFactory, "fetch_tools", slow_fetch_tools):
        ticker_task = asyncio.create_task(ticker())
        try:
            agent = await generator.create_agent_async(str(config_file))
        finally:
            ticker_task.cancel()

    assert agent is not None
    assert ticks > min_expected_ticks, (
        f"event loop was starved during agent creation (only {ticks} ticks)"
    )


@pytest.mark.asyncio
async def test_fetch_tools_caches_discovery_per_server(mcp_config):
    """Finding 4: repeated agent creation must not re-spawn the MCP server."""
    tools = [{"name": "read_file", "description": "Read a file", "input_schema": {}}]
    transport = _TransportRecorder()

    with (
        patch("src.tools.mcp.client.stdio_client", transport.open),
        patch("src.tools.mcp.client.ClientSession", _fake_client_session),
        patch.object(McpServerFactory, "_filter_and_parse_tools", return_value=tools),
    ):
        first = await McpServerFactory.fetch_tools(mcp_config)
        opened_in = transport.opened_in
        second = await McpServerFactory.fetch_tools(mcp_config)

    assert first == tools
    assert second == tools
    # A second connection would have re-entered the transport and overwritten opened_in.
    assert transport.opened_in is opened_in
    # The synchronous entry point serves the same cache without starting a thread.
    assert McpServerFactory.fetch_tools_sync(mcp_config) == tools
