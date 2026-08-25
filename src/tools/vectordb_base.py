"""Vector database base abstractions and factory.

.. deprecated::
    Use :mod:`src.tools.local.vectordb_base` instead.
"""

import warnings

from src.tools.local.vectordb_base import BaseVectorDB, VectorDBFactory

warnings.warn(
    "src.tools.vectordb_base is deprecated; use src.tools.local.vectordb_base instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["BaseVectorDB", "VectorDBFactory"]
