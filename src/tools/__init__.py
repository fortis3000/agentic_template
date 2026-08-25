"""Unified Tools subsystem providing local tools, MCP integrations, and unified ToolManager."""

from src.tools.local.base import BaseTool, ToolConfigType, ToolFactory
from src.tools.local.google_sheet import (
    GoogleSheetsAddVocabEntryTool,
    GoogleSheetsReadTool,
    GoogleSheetsWriteTool,
)
from src.tools.local.google_sheet import write_german_words as google_sheet_tool  # noqa: F401
from src.tools.local.qdrant_db import QdrantVectorDB, generate_sparse_vector
from src.tools.local.text_extractor import (
    MIME_HTML,
    MIME_MARKDOWN,
    MIME_PDF,
    MIME_TEXT,
    SUPPORTED_MIME_TYPES,
    extract_text,
)
from src.tools.local.vectordb_base import BaseVectorDB, VectorDBFactory
from src.tools.local.vectordb_search import VectorDBSearchTool
from src.tools.manager import ToolManager
from src.tools.mcp.client import (
    McpServerFactory,
    McpToolDefinition,
    make_mcp_tool_callable,
)
from src.tools.mcp.manager import SHUTDOWN_TIMEOUT, McpConnectionManager, build_session_key
from src.tools.mcp.server import parse_http_server_kwargs, parse_stdio_server_parameters

__all__ = [
    "BaseTool",
    "BaseVectorDB",
    "GoogleSheetsAddVocabEntryTool",
    "GoogleSheetsReadTool",
    "GoogleSheetsWriteTool",
    "MIME_HTML",
    "MIME_MARKDOWN",
    "MIME_PDF",
    "MIME_TEXT",
    "McpConnectionManager",
    "McpServerFactory",
    "McpToolDefinition",
    "QdrantVectorDB",
    "SHUTDOWN_TIMEOUT",
    "SUPPORTED_MIME_TYPES",
    "ToolConfigType",
    "ToolFactory",
    "ToolManager",
    "VectorDBFactory",
    "VectorDBSearchTool",
    "build_session_key",
    "extract_text",
    "generate_sparse_vector",
    "make_mcp_tool_callable",
    "parse_http_server_kwargs",
    "parse_stdio_server_parameters",
]
