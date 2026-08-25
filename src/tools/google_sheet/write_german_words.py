"""Google Sheet tools.

.. deprecated::
    Use :mod:`src.tools.local.google_sheet.write_german_words` instead.
"""

import warnings

from src.tools.local.google_sheet.write_german_words import (
    GoogleSheetsAddVocabEntryTool,
    GoogleSheetsReadTool,
    GoogleSheetsWriteTool,
)

warnings.warn(
    "src.tools.google_sheet.write_german_words is deprecated; use src.tools.local.google_sheet.write_german_words instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "GoogleSheetsAddVocabEntryTool",
    "GoogleSheetsReadTool",
    "GoogleSheetsWriteTool",
]
