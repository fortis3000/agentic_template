# RAG Operations & Document Ingestion Guide

This guide provides end-to-end operational instructions for running Retrieval-Augmented Generation (RAG), ingesting documents, configuring text chunking, and executing vector searches.

---

## 1. End-to-End RAG Architecture

```text
[Raw File: PDF/MD/HTML/TXT] 
         │
         ▼
[TextExtractor] ──► [Text Chunkers (Fixed/Markdown/Semantic)]
                                     │
                                     ▼
                        [EmbeddingModelFactory]
                                     │ (Vector Embeddings)
                                     ▼
                        [Qdrant Collection: agentic_docs]
                                     │
                                     ▼
                    [Vector Search Tool: qdrant_db.py]
                                     │
                                     ▼
                        [Agent Prompt Context Injection]
```

---

## 2. Ingesting Documents into Qdrant

### 2.1 Using Ingestion Pipeline
To ingest a document or directory of files into Qdrant:

```python
import asyncio
from src.ingestion.pipeline import run_ingestion_pipeline

async def main():
    results = await run_ingestion_pipeline(
        file_path="data/sample_document.pdf",
        collection_name="agentic_docs",
        chunker_type="markdown",
        chunk_size=500,
        chunk_overlap=50
    )
    print(f"Ingested {len(results)} chunks into Qdrant.")

asyncio.run(main())
```

---

## 3. Configuring Chunker Strategies

- **Fixed Chunker (`fixed`)**: Recommended for uniform plain text documents.
- **Markdown Chunker (`markdown`)**: Recommended for structured technical specs and READMEs. Preserves section header context.
- **Semantic Chunker (`semantic`)**: Recommended for complex prose where sentence context boundaries vary dynamically.

---

## 4. Querying Vector Database from Agents

Agents query Qdrant using the `qdrant_db` tool:

```python
from src.tools.qdrant_db import QdrantVectorStore

store = QdrantVectorStore(collection_name="agentic_docs")
matches = store.search_vectors(query="What is the architecture of the agent engine?", limit=3)
for match in matches:
    print(f"Score: {match.score} | Text: {match.payload['text']}")
```
