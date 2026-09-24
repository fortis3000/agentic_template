"""VectorDB MCP client tool implementation.

Allows ToolManager and ToolFactory to register and invoke the remote
containerized VectorDB MCP microservice using httpx2.
"""

from collections.abc import Callable
from typing import Any

import httpx2

_ASYNC_CLIENT_CLS = httpx2.AsyncClient

from src.agents.config import McpServerConfigSchema
from src.tools.local.base import BaseTool, ToolFactory
from src.tools.mcp.manager import McpConnectionManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


@ToolFactory.register("vectordb_mcp")
@ToolFactory.register("vectordb_mcp_search")
class VectorDBMcpTool(BaseTool):
    """Tool that forwards search requests to the VectorDB MCP microservice using httpx2."""

    def __init__(
        self,
        url: str = "http://localhost:8001/sse",
        tool_name: str = "vectordb_search",
        collection_name: str = "default_collection",
        timeout: float = 30.0,
    ):
        self.url = url
        self.tool_name = tool_name
        self.collection_name = collection_name
        self.timeout = timeout

    async def check_health(self) -> dict[str, Any]:
        """Probe the remote MCP server's /healthz endpoint using httpx2."""
        health_url = self.url.replace("/sse", "/healthz")
        if not health_url.endswith("/healthz"):
            health_url = f"{self.url.rstrip('/')}/healthz"

        async with _ASYNC_CLIENT_CLS(timeout=self.timeout) as client:
            resp = await client.get(health_url)
            return resp.json()

    def get_callable(self) -> Callable:
        async def search_vectordb_mcp(
            query_text: str,
            filter_dict: dict[str, Any] | None = None,
            search_type: str = "dense",
            limit: int = 5,
            collection_name: str | None = None,
        ) -> str:
            """Search the document vector database via the VectorDB MCP microservice."""
            config = McpServerConfigSchema(
                type="http",
                url=self.url,
                timeout=self.timeout,
            )
            session = await McpConnectionManager.get_session(config)
            args = {
                "query_text": query_text,
                "filter_dict": filter_dict,
                "search_type": search_type,
                "limit": limit,
                "collection_name": collection_name or self.collection_name,
            }
            res = await session.call_tool(self.tool_name, arguments=args)
            if res.isError:
                raise RuntimeError(f"VectorDB MCP Error: {res.content}")
            if isinstance(res.content, list) and res.content:
                return getattr(res.content[0], "text", str(res.content[0]))
            return str(res.content)

        return search_vectordb_mcp
