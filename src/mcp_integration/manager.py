import asyncio
from typing import TYPE_CHECKING, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.mcp_integration.server import parse_http_server_kwargs, parse_stdio_server_parameters
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class McpConnectionManager:
    """Manages persistent connections and sessions for MCP servers to prevent spawning subprocesses on every tool call."""

    _sessions: dict[str, ClientSession] = {}
    _contexts: dict[str, Any] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def get_session(cls, config: Any) -> ClientSession:
        cfg_type = getattr(config, "type", "stdio")
        cfg_command = getattr(config, "command", "") or ""
        cfg_args = getattr(config, "args", [])
        cfg_url = getattr(config, "url", "") or ""

        key = f"{cfg_type}:{cfg_command}:{cfg_args}:{cfg_url}"

        async with cls._lock:
            session = cls._sessions.get(key)
            if session is not None:
                return session

            logger.info(f"Initializing persistent connection for MCP server: {cfg_type}")
            if cfg_type == "stdio":
                params = parse_stdio_server_parameters(config)
                ctx = stdio_client(params)
                read, write = await ctx.__aenter__()
                cls._contexts[key] = ctx

                sess = ClientSession(read, write)
                await sess.__aenter__()
                await sess.initialize()
                cls._sessions[key] = sess
                return sess

            elif cfg_type == "http":
                kwargs = parse_http_server_kwargs(config)
                ctx = sse_client(**kwargs)
                read, write = await ctx.__aenter__()
                cls._contexts[key] = ctx

                sess = ClientSession(read, write)
                await sess.__aenter__()
                await sess.initialize()
                cls._sessions[key] = sess
                return sess
            else:
                raise ValueError(f"Unsupported MCP server type: {cfg_type}")

    @classmethod
    async def close_all(cls) -> None:
        """Clean up and close all persistent sessions and connections."""
        async with cls._lock:
            for key, session in list(cls._sessions.items()):
                try:
                    await session.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Error exiting MCP session for {key}: {e}")
            cls._sessions.clear()

            for key, ctx in list(cls._contexts.items()):
                try:
                    await ctx.__aexit__(None, None, None)
                except Exception as e:
                    logger.error(f"Error exiting MCP connection context for {key}: {e}")
            cls._contexts.clear()
