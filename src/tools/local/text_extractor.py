"""Text extraction utilities for uploaded files.

Supports PDF, TXT, Markdown, and HTML file types.
PDF extraction uses PyMuPDF (pymupdf), which is licensed under AGPL-3.0.
See https://pymupdf.readthedocs.io/en/latest/about.html#license
"""

import re
from html.parser import HTMLParser

from src.utils.logger import get_logger

logger = get_logger(__name__)

# MIME type constants
MIME_PDF = "application/pdf"
MIME_TEXT = "text/plain"
MIME_MARKDOWN = "text/markdown"
MIME_HTML = "text/html"

SUPPORTED_MIME_TYPES = {MIME_PDF, MIME_TEXT, MIME_MARKDOWN, MIME_HTML}


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.text_parts = []

    def handle_data(self, data):
        self.text_parts.append(data)


def _sanitize_text(text: str) -> str:
    text = text.replace("\x00", "")
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text.strip()


def _extract_from_pdf(data: bytes) -> str:
    try:
        import pymupdf  # noqa: PLC0415 — lazy import for optional AGPL dependency
    except ImportError:
        logger.warning("pymupdf not installed, cannot extract PDF text.")
        return ""

    text_parts = []
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            for i in range(len(doc)):
                page = doc.load_page(i)
                text_parts.append(page.get_text())
    except Exception as e:
        logger.warning(f"Error extracting text from PDF: {e}")
        return ""

    text = "\n".join(text_parts)
    if not text.strip():
        logger.warning("No text extracted from PDF.")
    return text


def _extract_from_txt(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed for txt, falling back to Latin-1")
        return data.decode("latin-1")


def _extract_from_markdown(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed for markdown, falling back to Latin-1")
        return data.decode("latin-1")


def _extract_from_html(data: bytes) -> str:
    try:
        html_str = data.decode("utf-8")
    except UnicodeDecodeError:
        logger.warning("UTF-8 decoding failed for HTML, falling back to Latin-1")
        html_str = data.decode("latin-1")

    # Strip script and style blocks
    html_str = re.sub(
        r"<(script|style)[^>]*>.*?</\1>", "", html_str, flags=re.DOTALL | re.IGNORECASE
    )

    # Replace img tags with [Image: <alt>] or [Image]
    def img_repl(match):
        img_tag = match.group(0)
        alt_match = re.search(r'alt=["\'](.*?)["\']', img_tag, re.IGNORECASE)
        if alt_match:
            return f"[Image: {alt_match.group(1)}]"
        return "[Image]"

    html_str = re.sub(r"<img[^>]*>", img_repl, html_str, flags=re.IGNORECASE)

    parser = _HTMLTextExtractor()
    parser.feed(html_str)

    text = "".join(parser.text_parts)
    # Collapse excessive whitespace
    text = re.sub(r"\s+", " ", text)
    return text


def extract_text(data: bytes, mime_type: str) -> str:
    if mime_type not in SUPPORTED_MIME_TYPES:
        raise ValueError(f"Unsupported MIME type for text extraction: {mime_type}")

    if mime_type == MIME_PDF:
        text = _extract_from_pdf(data)
    elif mime_type == MIME_TEXT:
        text = _extract_from_txt(data)
    elif mime_type == MIME_MARKDOWN:
        text = _extract_from_markdown(data)
    elif mime_type == MIME_HTML:
        text = _extract_from_html(data)
    else:
        # Fallback
        text = _extract_from_txt(data)

    return _sanitize_text(text)
