"""Base tool abstractions and registry factory.

.. deprecated::
    Use :mod:`src.tools.local.base` instead.
"""

import warnings

from src.tools.local.base import BaseTool, ToolConfigType, ToolFactory

warnings.warn(
    "src.tools.base is deprecated; use src.tools.local.base instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = ["BaseTool", "ToolConfigType", "ToolFactory"]
