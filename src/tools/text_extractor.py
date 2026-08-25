"""Text extraction utilities for uploaded files.

.. deprecated::
    Use :mod:`src.tools.local.text_extractor` instead.
"""

import warnings

from src.tools.local.text_extractor import (
    MIME_HTML,
    MIME_MARKDOWN,
    MIME_PDF,
    MIME_TEXT,
    SUPPORTED_MIME_TYPES,
    extract_text,
)

warnings.warn(
    "src.tools.text_extractor is deprecated; use src.tools.local.text_extractor instead.",
    DeprecationWarning,
    stacklevel=2,
)

__all__ = [
    "MIME_HTML",
    "MIME_MARKDOWN",
    "MIME_PDF",
    "MIME_TEXT",
    "SUPPORTED_MIME_TYPES",
    "extract_text",
]
