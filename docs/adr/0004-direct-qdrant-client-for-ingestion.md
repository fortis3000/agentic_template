# ADR-0004: Direct AsyncQdrantClient Integration for Ingestion Microservice

## Context & Problem Statement
The ingestion microservice must index extracted and chunked document embeddings into vector collections and prune orphaned vector points when source documents are modified or removed. We evaluated two architectural options for VectorDB integration:
1. **Option A (MCP over SSE/HTTP)**: Calling the existing `vectordb_store` MCP tool over SSE/HTTP.
2. **Option B (Direct AsyncQdrantClient)**: Connecting directly to Qdrant via `AsyncQdrantClient` over the Docker Compose service mesh.

## Decision
We adopt **Option B (Direct AsyncQdrantClient)** for the dedicated ingestion microservice:
1. **High-Throughput Batch Upserts**: `AsyncQdrantClient` natively supports batching hundreds of vector points per HTTP/gRPC call (`qdrant.upsert(points=[PointStruct(...)])`), whereas the MCP tool processes vectors individually or requires conversational SSE tool serialization.
2. **Atomic Orphan Pruning**: Direct client supports deterministic ID deletion (`qdrant.delete(points_selector=PointIdsList(...))`), enabling the delta sync engine to purge stale chunks before upserting updated points without orphaned fragments.
3. **Collection Provisioning & Quantization**: Direct client allows configuring HNSW parameters, scalar quantization, and payload schema indexes on `POST /collections`.
4. **Architectural Separation of Concerns**: The MCP tools (`vectordb_search`, `vectordb_store`) remain optimized for runtime agent chat sessions, while the ingestion service operates as an autonomous, high-throughput ETL data pipeline.

## Tracing Architecture
Spans are instrumented via OpenTelemetry and Arize Phoenix:
* Root Span: `ingestion.process_file`
* Child Spans:
  * `extraction.pdf_inspect`: Detect-then-route latency, page classifications (`TextBased`, `Scanned`).
  * `chunking.hierarchical`: Number of leaf chunks, heading depth, atomic blocks preserved.
  * `embedding.generate_batch`: Token count, model latency, batch size.
  * `vectordb.upsert_points`: Number of points upserted, Qdrant collection name.
