# Prototype: Hierarchical Markdown Splitting & Multipage Article Assembly (Issue #96)

## Overview & Status

This prototype resolves **Issue #96** (part of Wayfinder Map #90) evaluating:
1. **Hierarchical Markdown Splitter**: Constructing heading trees (H1–H6), breadcrumb injection, and context-window-safe atomic block handling.
2. **Parent-Child Chunk Linkages**: Multi-scale representation in Qdrant payloads for hierarchical retrieval.
3. **Multipage Article Assembly (Issue #60)**: Prototyped and evaluated; explicitly ruled **out of scope** for the initial microservice release to focus on stable single-page/file ingestion.

---

## Strategic Decisions

### 1. Breadcrumb Strategy: Option A (`INLINE_PREFIX`)
* **Decision**: Ancestor breadcrumbs (e.g. `[Context: Architecture > Vector Store > Payloads]`) are prepended directly to the chunk text before computing embeddings and upserting to Qdrant.
* **Rationale**: Gives embedding models and BM25 sparse indexers immediate semantic grounding, eliminating the "lost topic" problem when isolated paragraphs or table rows do not repeat their parent section title.
* **Payload Storage**: Full breadcrumb list (`breadcrumbs: list[str]`) is also preserved in Qdrant metadata for UI rendering and optional filtered queries.

### 2. Ensuring Atomic Blocks Fit Model Context Windows
* **Baseline**: Code blocks (```` ```...``` ````) and Markdown tables (`| ... |`) are masked with atomic tokens and preserved as indivisible leaf chunks (`is_atomic_block=True`) whenever $\text{size} \le \text{max\_atomic\_size}$.
* **Adaptive Fallback When Exceeding Context Window**:
  1. **Markdown Tables (Header-Preserving Row Chunking)**:
     - The column header row and separator (`| Col A | Col B | \n | --- | --- |`) are extracted.
     - The table is partitioned across multiple sub-chunks by rows.
     - The header row is automatically repeated at the top of each sub-chunk table.
     - *Result*: Every chunk remains a valid, syntactically complete Markdown table that fits comfortably within the embedding token window without losing column definitions.
  2. **Code Blocks (Syntax-Bounded Fenced Chunking)**:
     - Large code files are split across logical function/class boundaries or line breaks.
     - Every sub-chunk is re-wrapped in the language fence (```` ```python ... ``` ````) with a `# (continued from previous chunk)` comment header.
     - *Result*: No broken syntax or unclosed code fences.

### 3. Multipage Article Assembly (Issue #60)
* **Decision**: **Ruled Out of Scope** for the initial ingestion service release.
* **Rationale**: The 5-stage reconstruction pipeline (running margin stripping, jump-line tracking, cross-page de-hyphenation) was proven feasible in the prototype, but adds unnecessary complexity to the core ingestion microservice MVP. Ingestion will operate per-file/per-page until the containerized microservice and delta sync engine are operational. Issue #60 remains open on the backlog for a dedicated follow-up effort.

---

## How to Run the Prototype

```bash
# Interactive TUI: inspect heading trees, test oversized tables and code blocks
uv run python src/ingestion/prototype_chunking_and_assembly.py

# Automated non-interactive demo / test suite
uv run python src/ingestion/prototype_chunking_and_assembly.py --demo
```
