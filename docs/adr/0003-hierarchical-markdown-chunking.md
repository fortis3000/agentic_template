# ADR-0003: Hierarchical Markdown Splitting & Context-Window-Safe Atomic Chunking

## Context & Problem Statement
Document ingestion in RAG systems frequently suffers from two retrieval failures:
1. **Lost Topic Context**: Sub-chunks of sections (paragraphs, tables) do not repeat the document or section titles, leading to poor embedding similarity and low BM25 recall when queries target the overarching topic.
2. **Severed Syntax & Table Fragmentation**: Fixed-length character window chunkers slice Markdown tables and code blocks mid-entity, destroying table headers and invalidating programming syntax.

## Decision
For the dedicated document ingestion microservice, we adopt:
1. **Stack-Based Heading Tree Splitter**: Parses `#` through `######` headings into hierarchical sections with full ancestor breadcrumbs.
2. **Inline Breadcrumb Injection (Option A)**: Prepends `[Context: H1 > H2 > H3]` directly to the chunk text before generating dense vector embeddings and BM25 sparse indices, while also storing `breadcrumbs: list[str]` in Qdrant metadata payloads.
3. **Atomic Block Masking & Context-Window Safeguards**:
   - Code blocks and Markdown tables are masked with atomic placeholder tokens prior to splitting, ensuring they remain intact up to the model context limit (`max_atomic_size`).
   - If a table exceeds `max_atomic_size`, it is partitioned across sub-chunks by data rows with the column header row automatically repeated on each chunk (**Header-Preserving Row Chunking**).
   - If a code block exceeds `max_atomic_size`, it is partitioned along function/line boundaries and re-wrapped in code fences (**Syntax-Bounded Fenced Chunking**).
4. **Parent-Child Retrieval Model**: Leaf chunks ($\le 350$–$500$ chars) are indexed as primary points in Qdrant for semantic precision, storing `parent_id` referencing the enclosing `ParentChunk` section.
5. **Out of Scope**: Multipage article assembly (per Issue #60) is explicitly deferred out of scope for the initial ingestion service release. Documents are ingested per-page/per-file.

## Consequences & Room for Improvement
- Granular leaf vectors achieve high semantic precision while retaining full contextual grounding via breadcrumbs.
- Table structures and code blocks remain syntactically valid when retrieved in isolation.
- Future follow-up phases can implement AST-based code parsers and multipage periodical reconstruction once the core containerized pipeline is in production.
