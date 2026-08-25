"""Vector database search tool.

.. deprecated::
    Use :mod:`src.tools.local.vectordb_search` instead.
"""

import warnings

from src.tools.local.vectordb_search import VectorDBSearchTool

warnings.warn(
    "src.tools.vectordb_search is deprecated; use src.tools.local.vectordb_search instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["VectorDBSearchTool"]
