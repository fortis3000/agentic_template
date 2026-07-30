import asyncio
from contextlib import AsyncExitStack, suppress
from typing import TYPE_CHECKING, Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client

from src.mcp_integration.server import parse_http_server_kwargs, parse_stdio_server_parameters
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Seconds to wait for owner tasks to unwind their connections before cancelling them.
SHUTDOWN_TIMEOUT = 10.0


def build_session_key(config: Any) -> str:
    """Build the cache key identifying a unique MCP server connection."""
    cfg_type = getattr(config, "type", "stdio")
    cfg_command = getattr(config, "command", "") or ""
    cfg_args = getattr(config, "args", []) or []
    cfg_url = getattr(config, "url", "") or ""
    return f"{cfg_type}:{cfg_command}:{cfg_args}:{cfg_url}"


class McpConnectionManager:
    """Manages persistent connections and sessions for MCP servers to prevent spawning subprocesses on every tool call.

    ``stdio_client`` and ``sse_client`` are anyio task-group based context managers: exiting one
    from a different task than the one that entered it raises
    ``RuntimeError: Attempted to exit cancel scope in a different task``. Each connection is
    therefore owned by its own long-lived task which enters the context, hands the initialized
    session back to the caller, and holds the context open until shutdown — so entry and exit
    always happen in the same task.
    """

    _sessions: dict[str, ClientSession] = {}
    _owner_tasks: dict[str, asyncio.Task] = {}
    _stop_events: dict[str, asyncio.Event] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def _run_session(
        cls,
        config: Any,
        key: str,
        ready: asyncio.Future,
        stop: asyncio.Event,
    ) -> None:
        """Own an MCP connection for its whole lifetime.

        Opens the transport and session inside a single :class:`AsyncExitStack`, publishes the
        initialized session via ``ready``, then blocks on ``stop`` so the stack unwinds in this
        same task when :meth:`close_all` signals shutdown.
        """
        cfg_type = getattr(config, "type", "stdio")
        try:
            async with AsyncExitStack() as stack:
                if cfg_type == "stdio":
                    params = parse_stdio_server_parameters(config)
                    read, write = await stack.enter_async_context(stdio_client(params))
                elif cfg_type == "http":
                    kwargs = parse_http_server_kwargs(config)
                    read, write = await stack.enter_async_context(sse_client(**kwargs))
                else:
                    raise ValueError(f"Unsupported MCP server type: {cfg_type}")

                sess = await stack.enter_async_context(ClientSession(read, write))
                await sess.initialize()

                if ready.done():
                    # The requester gave up (cancelled) before the connection was ready.
                    return
                ready.set_result(sess)

                await stop.wait()
        except asyncio.CancelledError:
            if not ready.done():
                ready.cancel()
            raise
        except Exception as e:
            if not ready.done():
                ready.set_exception(e)
            else:
                logger.error(f"MCP connection for {key} terminated with an error: {e}")

    @classmethod
    async def get_session(cls, config: Any) -> ClientSession:
        """Return a live session for the configured MCP server, connecting on first use."""
        key = build_session_key(config)

        async with cls._lock:
            session = cls._sessions.get(key)
            if session is not None:
                return session

            cfg_type = getattr(config, "type", "stdio")
            if cfg_type not in ("stdio", "http"):
                raise ValueError(f"Unsupported MCP server type: {cfg_type}")

            logger.info(f"Initializing persistent connection for MCP server: {cfg_type}")
            loop = asyncio.get_running_loop()
            ready: asyncio.Future = loop.create_future()
            stop = asyncio.Event()

            task = asyncio.create_task(cls._run_session(config, key, ready, stop))
            # A crashed server must not leave a dead session cached for the next request.
            task.add_done_callback(lambda _t, k=key: cls._sessions.pop(k, None))

            try:
                session = await ready
            except BaseException:
                stop.set()
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
                raise

            cls._owner_tasks[key] = task
            cls._stop_events[key] = stop
            cls._sessions[key] = session
            return session

    @classmethod
    async def close_all(cls) -> None:
        """Clean up and close all persistent sessions and connections."""
        async with cls._lock:
            for stop in cls._stop_events.values():
                stop.set()

            tasks = list(cls._owner_tasks.values())
            if tasks:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks, return_exceptions=True),
                        timeout=SHUTDOWN_TIMEOUT,
                    )
                except (asyncio.TimeoutError, TimeoutError):
                    logger.error(
                        f"MCP connections did not close within {SHUTDOWN_TIMEOUT}s. Cancelling."
                    )
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)

            cls._sessions.clear()
            cls._owner_tasks.clear()
            cls._stop_events.clear()
