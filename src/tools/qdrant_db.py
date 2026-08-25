"""Qdrant vector database tool.

.. deprecated::
    Use :mod:`src.tools.local.qdrant_db` instead.
"""

import warnings

from src.tools.local.qdrant_db import QdrantVectorDB, generate_sparse_vector

warnings.warn(
    "src.tools.qdrant_db is deprecated; use src.tools.local.qdrant_db instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["QdrantVectorDB", "generate_sparse_vector"]
