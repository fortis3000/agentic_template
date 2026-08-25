"""Vector database base abstractions and factory.

Re-exports vector database interfaces from src.tools.local.vectordb_base.
"""

from src.tools.local.vectordb_base import BaseVectorDB, VectorDBFactory

__all__ = ["BaseVectorDB", "VectorDBFactory"]
