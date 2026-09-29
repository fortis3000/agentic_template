# Document Ingestion

The ingestion context coordinates parsing, intelligent routing, hierarchical chunking, embedding generation, and vector index synchronization for documents.

## Language

**IngestJob**:
A persisted unit of asynchronous work that synchronizes, extracts, chunks, and indexes a single document file or delta update.
_Avoid_: Task, work item, message

**JobQueue**:
A persistent FIFO queue responsible for scheduling, leasing, and tracking the lifecycle of ingest jobs.
_Avoid_: Task queue, message broker, event bus

**IngestionWorker**:
A background execution process that leases pending ingest jobs from the job queue and coordinates their execution pipeline.
_Avoid_: Consumer, background task, pipeline runner

**JobLease**:
A time-bounded reservation on an ingest job maintained via periodic worker heartbeats to detect and recover from crashes.
_Avoid_: Lock, worker reservation, task claim

**IdempotentIngestion**:
An execution guarantee where reprocessing a job safely cleans up prior chunk representations before inserting new ones, preventing duplicate vector embeddings.
_Avoid_: Deduplication, safe retry, upsert dedupe

**ChunkBatch**:
A grouped payload of extracted text chunks submitted together in a single vector embedding API request to maximize throughput.
_Avoid_: Bulk chunk, embedding batch, text packet

**RateLimiter**:
A token-bucket throughput governor enforcing per-provider request and token rate limits across all concurrent worker jobs.
_Avoid_: Throttler, traffic cop, delay timer

**JobStatus**:
The operational lifecycle state of an ingest job (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`).
_Avoid_: Job state, task status, execution phase

**JobStage**:
The fine-grained active processing phase of a running ingest job (`EXTRACTING`, `CHUNKING`, `EMBEDDING`, `INDEXING`).
_Avoid_: Step, phase, subtask

**JobProgress**:
Quantitative counters reporting processed units versus total units (such as pages parsed or chunks embedded) for a running job.
_Avoid_: Completion percentage, progress stats

**JobCancellation**:
The operational mechanism allowing clients to terminate a pending or running ingest job and cease downstream work.
_Avoid_: Job abort, kill, task stop

**JobRetention**:
The time-based policy governing automated pruning of terminal job records from the queue database after a retention period (default 7 days).
_Avoid_: Garbage collection, history purge, log rotation
