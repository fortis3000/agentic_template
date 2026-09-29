"""Hierarchical Markdown chunker with ancestor breadcrumbs and atomic block preservation.

Implements ADR-0003: Hierarchical Markdown Splitting with Option A (INLINE_PREFIX)
ancestor breadcrumbs prepended to chunk text for dense/sparse retrieval and
parent-child chunk linkages for multi-scale retrieval.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import StrEnum

DEFAULT_CHUNK_SIZE = 350
DEFAULT_CHUNK_OVERLAP = 50
DEFAULT_MAX_ATOMIC_SIZE = 500
MIN_TABLE_LINES_FOR_SPLIT = 3


class BreadcrumbMode(StrEnum):
    """Controls how hierarchical ancestor breadcrumbs are injected."""

    INLINE_PREFIX = "inline_prefix"  # Option A: Prepended to chunk text for BM25/Dense overlap
    METADATA_ONLY = "metadata_only"  # Stored in Qdrant payload only
    DISABLED = "disabled"  # No breadcrumbs computed


@dataclass
class RawSection:
    """Intermediate markdown section under a heading."""

    heading: str
    level: int
    breadcrumbs: list[str]
    content: str


@dataclass
class ParentChunk:
    """Coarse-grained parent structural chunk."""

    chunk_id: str
    heading: str
    level: int
    breadcrumbs: list[str]
    raw_text: str
    child_chunk_ids: list[str] = field(default_factory=list)


@dataclass
class LeafChunk:
    """Fine-grained leaf chunk indexed into vector search."""

    chunk_id: str
    parent_id: str
    breadcrumbs: list[str]
    breadcrumb_str: str
    raw_text: str
    search_text: str
    is_atomic_block: bool
    block_type: str
    character_count: int
    qdrant_payload: dict[str, str | int | float | bool | list[str] | None]


class HierarchicalMarkdownSplitter:
    """Splits Markdown documents into hierarchical chunks preserving structure and context."""

    def __init__(
        self,
        max_chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        max_atomic_size: int = DEFAULT_MAX_ATOMIC_SIZE,
        breadcrumb_mode: BreadcrumbMode = BreadcrumbMode.INLINE_PREFIX,
    ) -> None:
        self.max_chunk_size = max_chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_atomic_size = max_atomic_size
        self.breadcrumb_mode = breadcrumb_mode

    def _extract_atomic_blocks(self, text: str) -> tuple[str, dict[str, tuple[str, str]]]:
        """Replaces code blocks and markdown tables with unique tokens so they remain unsplit."""
        placeholders: dict[str, tuple[str, str]] = {}

        def replace_code(match: re.Match[str]) -> str:
            token = f"__ATOMIC_CODE_BLOCK_{uuid.uuid4().hex[:8]}__"
            placeholders[token] = ("code", match.group(0))
            return f"\n\n{token}\n\n"

        code_pattern = re.compile(r"```[\s\S]*?```|~~~[\s\S]*?~~~")
        masked_text = code_pattern.sub(replace_code, text)

        table_pattern = re.compile(r"(?:^[ \t]*\|.+?\|[ \t]*\r?\n)+", re.MULTILINE)

        def replace_table(match: re.Match[str]) -> str:
            raw = match.group(0).strip()
            if re.search(r"\|[ \t]*:?-+:?[ \t]*\|", raw):
                token = f"__ATOMIC_TABLE_BLOCK_{uuid.uuid4().hex[:8]}__"
                placeholders[token] = ("table", raw)
                return f"\n\n{token}\n\n"
            return match.group(0)

        masked_text = table_pattern.sub(replace_table, masked_text)
        return masked_text, placeholders

    def parse_heading_sections(self, markdown: str) -> list[RawSection]:
        """Parses Markdown into sections based on H1-H6 headers."""
        lines = markdown.splitlines()
        sections: list[RawSection] = []
        stack: list[tuple[int, str]] = []
        current_heading = "Document Root"
        current_level = 0
        current_lines: list[str] = []

        header_re = re.compile(r"^(#{1,6})\s+(.+)$")

        for line in lines:
            h_match = header_re.match(line.strip())
            if h_match:
                if current_lines or current_heading != "Document Root":
                    content = "\n".join(current_lines).strip()
                    breadcrumbs = [h for _, h in stack] if stack else [current_heading]
                    sections.append(
                        RawSection(
                            heading=current_heading,
                            level=current_level,
                            breadcrumbs=breadcrumbs,
                            content=content,
                        )
                    )
                    current_lines = []

                level = len(h_match.group(1))
                heading_text = h_match.group(2).strip()

                while stack and stack[-1][0] >= level:
                    stack.pop()
                stack.append((level, heading_text))

                current_heading = heading_text
                current_level = level
            else:
                current_lines.append(line)

        if current_lines or current_heading != "Document Root":
            content = "\n".join(current_lines).strip()
            breadcrumbs = [h for _, h in stack] if stack else [current_heading]
            sections.append(
                RawSection(
                    heading=current_heading,
                    level=current_level,
                    breadcrumbs=breadcrumbs,
                    content=content,
                )
            )

        return sections

    def _split_long_paragraph(self, paragraph: str) -> list[str]:
        """Splits long paragraphs along sentence or whitespace boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+", paragraph)
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for sentence in sentences:
            sentence_len = len(sentence)
            if sentence_len > self.max_chunk_size:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                    current_chunk = []
                    current_len = 0
                for i in range(0, sentence_len, self.max_chunk_size - self.chunk_overlap):
                    sub = sentence[i : i + self.max_chunk_size]
                    if sub.strip():
                        chunks.append(sub.strip())
            elif current_len + sentence_len + 1 <= self.max_chunk_size:
                current_chunk.append(sentence)
                current_len += sentence_len + 1
            else:
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                current_chunk = [sentence]
                current_len = sentence_len

        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _split_prose_block(self, prose: str) -> list[str]:
        """Splits narrative prose by paragraphs and sentence boundaries."""
        paragraphs = [p.strip() for p in prose.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current_buf: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current_len + para_len + 2 <= self.max_chunk_size:
                current_buf.append(para)
                current_len += para_len + 2
            else:
                if current_buf:
                    chunks.append("\n\n".join(current_buf))
                    current_buf = []
                    current_len = 0

                if para_len <= self.max_chunk_size:
                    current_buf.append(para)
                    current_len = para_len
                else:
                    chunks.extend(self._split_long_paragraph(para))

        if current_buf:
            chunks.append("\n\n".join(current_buf))

        return chunks

    def _split_oversized_table(self, table_text: str) -> list[str]:
        """Splits an oversized table by data rows, repeating the column header row on each sub-chunk."""
        lines = [ln.strip() for ln in table_text.strip().splitlines() if ln.strip()]
        if len(lines) < MIN_TABLE_LINES_FOR_SPLIT:
            return [table_text]

        header_str = f"{lines[0]}\n{lines[1]}"
        data_rows = lines[2:]

        chunks: list[str] = []
        current_rows: list[str] = []
        current_size = len(header_str)

        for row in data_rows:
            row_size = len(row) + 1
            if current_size + row_size > self.max_atomic_size and current_rows:
                chunk_table = f"{header_str}\n" + "\n".join(current_rows)
                chunks.append(chunk_table)
                current_rows = [row]
                current_size = len(header_str) + row_size
            else:
                current_rows.append(row)
                current_size += row_size

        if current_rows:
            chunk_table = f"{header_str}\n" + "\n".join(current_rows)
            chunks.append(chunk_table)

        return chunks

    def _split_oversized_code(self, code_text: str) -> list[str]:
        """Splits an oversized code block across line boundaries, wrapping each chunk in code fences.

        Handles info strings like `c++` or `objective-c` cleanly, hard-wraps lines longer than
        the budget, and keeps fence syntax valid.
        """
        match = re.match(r"^```([^\n]*)\n([\s\S]*?)```$", code_text.strip())
        if not match:
            match = re.match(r"^~~~([^\n]*)\n([\s\S]*?)~~~$", code_text.strip())
            if not match:
                return [code_text]

        lang = match.group(1).strip()
        body = match.group(2)
        lines = body.splitlines()

        fence_overhead = len(lang) + 8  # ```lang\n ... \n```
        max_line_budget = max(10, self.max_atomic_size - fence_overhead)

        # Pre-wrap lines exceeding line budget so single long lines fit
        wrapped_lines: list[str] = []
        for line in lines:
            if len(line) > max_line_budget:
                for i in range(0, len(line), max_line_budget):
                    wrapped_lines.append(line[i : i + max_line_budget])
            else:
                wrapped_lines.append(line)

        chunks: list[str] = []
        current_lines: list[str] = []
        current_size = fence_overhead

        for line in wrapped_lines:
            line_size = len(line) + 1
            if current_size + line_size > self.max_atomic_size and current_lines:
                chunk_code = f"```{lang}\n" + "\n".join(current_lines) + "\n```"
                chunks.append(chunk_code)
                current_lines = [line]
                current_size = fence_overhead + line_size
            else:
                current_lines.append(line)
                current_size += line_size

        if current_lines:
            chunk_code = f"```{lang}\n" + "\n".join(current_lines) + "\n```"
            chunks.append(chunk_code)

        return chunks

    def _partition_by_tokens(self, content: str, tokens: list[str]) -> list[str]:
        """Splits content into segments separated by placeholder tokens."""
        parts = [content]
        for tok in tokens:
            new_parts: list[str] = []
            for p in parts:
                if tok in p:
                    sub = p.split(tok)
                    for i, s in enumerate(sub):
                        if i > 0:
                            new_parts.append(tok)
                        if s:
                            new_parts.append(s)
                else:
                    new_parts.append(p)
            parts = new_parts
        return parts

    def _build_leaf(
        self,
        leaf_id: str,
        parent_id: str,
        article_id: str,
        source_file: str,
        sec: RawSection,
        formatted_breadcrumb: str,
        raw_text: str,
        block_type: str,
        is_atomic: bool,
    ) -> LeafChunk:
        search_text = (
            f"{formatted_breadcrumb}\n\n{raw_text}"
            if self.breadcrumb_mode == BreadcrumbMode.INLINE_PREFIX and formatted_breadcrumb
            else raw_text
        )
        return LeafChunk(
            chunk_id=leaf_id,
            parent_id=parent_id,
            breadcrumbs=sec.breadcrumbs,
            breadcrumb_str=formatted_breadcrumb,
            raw_text=raw_text,
            search_text=search_text,
            is_atomic_block=is_atomic,
            block_type=block_type,
            character_count=len(raw_text),
            qdrant_payload={
                "chunk_id": leaf_id,
                "parent_id": parent_id,
                "article_id": article_id,
                "source_file": source_file,
                "breadcrumbs": sec.breadcrumbs,
                "heading": sec.heading,
                "level": sec.level,
                "is_atomic_block": is_atomic,
                "block_type": block_type,
                "text": raw_text,
            },
        )

    def _process_atomic_segment(
        self,
        segment: str,
        placeholders: dict[str, tuple[str, str]],
        parent: ParentChunk,
        sec: RawSection,
        article_id: str,
        source_file: str,
        formatted_breadcrumb: str,
    ) -> list[LeafChunk]:
        """Processes an atomic block, splitting adaptively if it exceeds model context window."""
        block_type, original_code = placeholders[segment]
        leaves: list[LeafChunk] = []

        if len(original_code) <= self.max_atomic_size:
            leaf_id = f"{parent.chunk_id}-leaf{len(parent.child_chunk_ids) + 1}"
            parent.child_chunk_ids.append(leaf_id)
            leaves.append(
                self._build_leaf(
                    leaf_id=leaf_id,
                    parent_id=parent.chunk_id,
                    article_id=article_id,
                    source_file=source_file,
                    sec=sec,
                    formatted_breadcrumb=formatted_breadcrumb,
                    raw_text=original_code,
                    block_type=block_type,
                    is_atomic=True,
                )
            )
        else:
            # Oversized atomic block: apply adaptive structure-preserving splitting
            sub_pieces = (
                self._split_oversized_table(original_code)
                if block_type == "table"
                else self._split_oversized_code(original_code)
            )
            for piece in sub_pieces:
                leaf_id = f"{parent.chunk_id}-leaf{len(parent.child_chunk_ids) + 1}"
                parent.child_chunk_ids.append(leaf_id)
                leaves.append(
                    self._build_leaf(
                        leaf_id=leaf_id,
                        parent_id=parent.chunk_id,
                        article_id=article_id,
                        source_file=source_file,
                        sec=sec,
                        formatted_breadcrumb=formatted_breadcrumb,
                        raw_text=piece,
                        block_type=f"{block_type}_split",
                        is_atomic=True,
                    )
                )

        return leaves

    def split_markdown(
        self, markdown_text: str, source_file: str = "", article_id: str = ""
    ) -> list[LeafChunk]:
        """Performs hierarchical markdown chunking with breadcrumb injection and atomic preservation."""
        sections = self.parse_heading_sections(markdown_text)
        all_leaf_chunks: list[LeafChunk] = []

        doc_prefix = article_id or (
            re.sub(r"[^\w\-]", "_", source_file).strip("_") if source_file else "doc"
        )

        for sec_idx, sec in enumerate(sections, start=1):
            if not sec.content:
                continue

            parent_id = f"{doc_prefix}-p{sec_idx}"
            parent = ParentChunk(
                chunk_id=parent_id,
                heading=sec.heading,
                level=sec.level,
                breadcrumbs=sec.breadcrumbs,
                raw_text=sec.content,
            )

            formatted_breadcrumb = (
                " > ".join(sec.breadcrumbs)
                if self.breadcrumb_mode != BreadcrumbMode.DISABLED
                else ""
            )

            # Mask atomic blocks
            masked_content, placeholders = self._extract_atomic_blocks(sec.content)

            # Partition content by atomic block placeholders
            segments = (
                self._partition_by_tokens(masked_content, list(placeholders.keys()))
                if placeholders
                else [masked_content]
            )

            for segment in segments:
                segment_clean = segment.strip()
                if not segment_clean:
                    continue

                if segment_clean in placeholders:
                    leaves = self._process_atomic_segment(
                        segment_clean,
                        placeholders,
                        parent,
                        sec,
                        article_id,
                        source_file,
                        formatted_breadcrumb,
                    )
                    all_leaf_chunks.extend(leaves)
                else:
                    # Regular prose text
                    prose_chunks = self._split_prose_block(segment_clean)
                    for pc in prose_chunks:
                        if not pc.strip():
                            continue
                        leaf_id = f"{parent.chunk_id}-leaf{len(parent.child_chunk_ids) + 1}"
                        parent.child_chunk_ids.append(leaf_id)
                        leaf = self._build_leaf(
                            leaf_id=leaf_id,
                            parent_id=parent.chunk_id,
                            article_id=article_id,
                            source_file=source_file,
                            sec=sec,
                            formatted_breadcrumb=formatted_breadcrumb,
                            raw_text=pc,
                            block_type="prose",
                            is_atomic=False,
                        )
                        all_leaf_chunks.append(leaf)

        return all_leaf_chunks
