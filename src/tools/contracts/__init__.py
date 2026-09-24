"""Leaf contracts package for tools with zero internal dependencies."""

from src.tools.contracts.config import AgentToolConfigProtocol, ToolSettingsProtocol
from src.tools.contracts.mcp import McpToolDefinition
from src.tools.contracts.tool import BaseToolProtocol, ToolCallable, ToolRegistry
from src.tools.contracts.vectordb_mcp import (
    HealthCheckResponse,
    VectorDBSearchType,
    VectorSearchRequest,
    VectorSearchResultItem,
    VectorStoreRequest,
    VectorStoreResponse,
)

__all__ = [
    "AgentToolConfigProtocol",
    "BaseToolProtocol",
    "HealthCheckResponse",
    "McpToolDefinition",
    "ToolCallable",
    "ToolRegistry",
    "ToolSettingsProtocol",
    "VectorDBSearchType",
    "VectorSearchRequest",
    "VectorSearchResultItem",
    "VectorStoreRequest",
    "VectorStoreResponse",
]
