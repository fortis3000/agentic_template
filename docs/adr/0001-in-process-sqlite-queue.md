# In-Process SQLite Persistent Queue for Ingestion Service

We evaluated an external distributed broker (Redis + Celery/ARQ, per #57) against an in-process persistent queue for the dedicated document ingestion microservice. We decided to adopt an in-process SQLite-backed persistent queue (with WAL mode and asyncio worker pool) abstracted behind a `JobQueue` protocol. This provides durable, crash-safe job tracking and sequential/controlled execution without introducing extra container infrastructure overhead, while preserving a clean protocol boundary for horizontal scaling.

## Room for Improvement & Future Evolution

As document volume and multi-node ingestion requirements grow (per #57), the `JobQueue` protocol can be backed by Redis + ARQ or Celery to enable distributed worker pools without changing upstream API contracts or ingestion logic.

