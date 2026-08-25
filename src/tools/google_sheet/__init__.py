"""Google Sheet tools package.

.. deprecated::
    Use :mod:`src.tools.local.google_sheet` instead.
"""

import warnings

from src.tools.local.google_sheet import (
    GoogleSheetsAddVocabEntryTool,
    GoogleSheetsReadTool,
    GoogleSheetsWriteTool,
)

warnings.warn(
    "src.tools.google_sheet is deprecated; use src.tools.local.google_sheet instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "GoogleSheetsAddVocabEntryTool",
    "GoogleSheetsReadTool",
    "GoogleSheetsWriteTool",
]
