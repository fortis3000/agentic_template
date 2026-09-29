"""Asynchronous background worker coordinating ingestion job leasing, chunking, and Qdrant indexing.

Implements ADR-0001 (SQLite Queue & Async Worker Pool), ADR-0003 (Hierarchical Chunking),
and ADR-0004 (Direct AsyncQdrantClient batch upserting with deterministic point IDs).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from typing import Any

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from src.ingestion.contracts import (
    JobAction,
    JobProgress,
    JobStage,
    JobStatus,
)
from src.ingestion.delta import SQLiteDeltaEngine
from src.ingestion.hierarchical_chunker import HierarchicalMarkdownSplitter, LeafChunk
from src.ingestion.queue import SQLiteJobQueue
from src.tools.local.text_extractor import extract_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

NAMESPACE_INGESTION = uuid.UUID("37000000-0000-0000-0000-000000000037")


class DeterministicEmbeddingClient:
    """Generates deterministic embeddings for testing and environments without external API keys."""

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float]] = []
        for text in texts:
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [float(((h[i % len(h)] + i) % 256) / 256.0) for i in range(self.dimensions)]
            results.append(vec)
        return results


class IngestionWorker:
    """Coordinates background job leasing, document processing, and Qdrant indexing."""

    def __init__(
        self,
        queue: SQLiteJobQueue,
        delta_engine: SQLiteDeltaEngine,
        qdrant_client: AsyncQdrantClient,
        worker_id: str | None = None,
        concurrency: int = 2,
        lease_duration: float = 300.0,
        embed_client: Any = None,
    ) -> None:
        self.queue = queue
        self.delta_engine = delta_engine
        self.qdrant_client = qdrant_client
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.concurrency = max(1, min(concurrency, 8))
        self.lease_duration = lease_duration
        self._semaphore = asyncio.Semaphore(self.concurrency)
        self._stop_event = asyncio.Event()
        self._worker_task: asyncio.Task[None] | None = None
        self._sweeper_task: asyncio.Task[None] | None = None
        self.embed_client = embed_client or self._resolve_embed_client()

    def _resolve_embed_client(self) -> Any:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                from src.agents.config import EmbeddingModelConfigSchema  # noqa: PLC0415
                from src.agents.embeddings import EmbeddingModelFactory  # noqa: PLC0415

                return EmbeddingModelFactory.create(
                    EmbeddingModelConfigSchema(
                        provider="google",
                        model="gemini-embedding-001",
                        dimensions=768,
                        image_dimensions=768,
                    )
                )
            except Exception as e:
                logger.warning(
                    f"Failed to initialize Google embedding client: {e}. Falling back to deterministic."
                )
        return DeterministicEmbeddingClient(dimensions=768)

    async def start(self) -> None:
        """Starts worker polling loop and periodic cleanup sweeps."""
        self._stop_event.clear()
        self._worker_task = asyncio.create_task(self._run_loop(), name=f"{self.worker_id}-main")
        self._sweeper_task = asyncio.create_task(
            self._sweeper_loop(), name=f"{self.worker_id}-sweeper"
        )
        logger.info(
            f"IngestionWorker {self.worker_id} started with concurrency {self.concurrency}."
        )

    async def stop(self) -> None:
        """Gracefully halts worker polling and background sweeps."""
        self._stop_event.set()
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._sweeper_task:
            self._sweeper_task.cancel()
            try:
                await self._sweeper_task
            except asyncio.CancelledError:
                pass
        logger.info(f"IngestionWorker {self.worker_id} stopped.")

    async def _run_loop(self) -> None:
        """Continuous polling loop for leasing and processing pending jobs."""
        while not self._stop_event.is_set():
            try:
                # Wait for available concurrency slot before leasing
                await self._semaphore.acquire()
                job = self.queue.lease_next_job(
                    worker_id=self.worker_id,
                    lease_duration_seconds=self.lease_duration,
                )
                if not job:
                    self._semaphore.release()
                    await asyncio.sleep(0.5)
                    continue

                # Run job processing asynchronously
                asyncio.create_task(self._execute_job_wrapper(job))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in worker run loop: {e}", exc_info=True)
                await asyncio.sleep(1.0)

    async def _sweeper_loop(self) -> None:
        """Periodic background task for recovering stale leases and pruning old jobs."""
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(60.0)
                recovered = self.queue.recover_stale_leases(max_retries=3)
                if recovered > 0:
                    logger.info(f"Sweeper recovered {recovered} stale job leases.")
                pruned = self.queue.prune_old_jobs(retention_days=7)
                if pruned > 0:
                    logger.info(f"Sweeper pruned {pruned} old jobs.")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error in sweeper loop: {e}")

    async def _heartbeat_loop(self, job_id: int, stop_heartbeat: asyncio.Event) -> None:
        """Periodically renews job lease while processing."""
        interval = max(5.0, self.lease_duration / 3.0)
        while not stop_heartbeat.is_set():
            try:
                await asyncio.sleep(interval)
                if stop_heartbeat.is_set():
                    break
                renewed = self.queue.heartbeat(
                    job_id=job_id,
                    worker_id=self.worker_id,
                    lease_duration_seconds=self.lease_duration,
                )
                if not renewed:
                    logger.warning(f"Failed to renew heartbeat for job #{job_id}.")
                    break
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Heartbeat error for job #{job_id}: {e}")

    async def _execute_job_wrapper(self, job: Any) -> None:
        """Wraps single job execution with lease heartbeats and semaphore cleanup."""
        stop_heartbeat = asyncio.Event()
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job.id, stop_heartbeat))
        try:
            await self._process_job(job)
        except asyncio.CancelledError:
            logger.info(f"Job #{job.id} cancelled during execution.")
        except Exception as e:
            logger.error(f"Failed to process job #{job.id} ({job.filepath}): {e}", exc_info=True)
            self.queue.fail_job(job.id, worker_id=self.worker_id, error=str(e))
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            self._semaphore.release()

    async def _ensure_collection_exists(self, collection_name: str, dimensions: int = 768) -> None:
        """Provisions collection in Qdrant if it does not yet exist."""
        try:
            collections_resp = await self.qdrant_client.get_collections()
            existing = [c.name for c in collections_resp.collections]
            if collection_name not in existing:
                await self.qdrant_client.create_collection(
                    collection_name=collection_name,
                    vectors_config=qmodels.VectorParams(
                        size=dimensions,
                        distance=qmodels.Distance.COSINE,
                    ),
                )
                logger.info(
                    f"Created Qdrant collection '{collection_name}' with {dimensions} dimensions."
                )
        except Exception as e:
            logger.error(f"Error ensuring collection '{collection_name}' exists: {e}")

    def _extract_content(self, filepath: str) -> str:
        """Extracts text content from a source file based on extension."""
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Source file does not exist: {filepath}")

        with open(filepath, "rb") as f:
            file_bytes = f.read()

        ext = os.path.splitext(filepath)[1].lower()
        mime_map = {
            ".pdf": "application/pdf",
            ".md": "text/markdown",
            ".html": "text/html",
        }
        mime_type = mime_map.get(ext, "text/plain")
        text = extract_text(file_bytes, mime_type)
        if not text.strip():
            logger.warning(f"No text extracted from {filepath}.")
            return ""
        return text

    def _chunk_document(
        self, text: str, filepath: str, job_id: int, options: dict[str, str]
    ) -> list[LeafChunk]:
        """Splits markdown/extracted text into hierarchical leaf chunks."""
        chunk_size = int(options.get("chunk_size", 350))
        chunk_overlap = int(options.get("chunk_overlap", 50))
        splitter = HierarchicalMarkdownSplitter(
            max_chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        leaves: list[LeafChunk] = splitter.split_markdown(
            markdown_text=text,
            source_file=filepath,
            article_id=f"doc_{job_id}",
        )

        if not leaves and text.strip():
            leaves = [
                LeafChunk(
                    chunk_id=f"doc_{job_id}-leaf1",
                    parent_id=f"doc_{job_id}-p1",
                    breadcrumbs=["Document Root"],
                    breadcrumb_str="Document Root",
                    raw_text=text,
                    search_text=text,
                    is_atomic_block=False,
                    block_type="prose",
                    character_count=len(text),
                    qdrant_payload={
                        "chunk_id": f"doc_{job_id}-leaf1",
                        "source_file": filepath,
                        "text": text,
                    },
                )
            ]
        return leaves

    async def _generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generates embedding vectors for a batch of chunk texts."""
        if not texts:
            return []
        if hasattr(self.embed_client, "embed_batch"):
            batch_res = await self.embed_client.embed_batch(texts)
            return batch_res.embeddings if hasattr(batch_res, "embeddings") else batch_res
        return [[0.0] * 768 for _ in texts]

    async def _index_points(
        self, job: Any, leaves: list[LeafChunk], vectors: list[list[float]]
    ) -> list[str]:
        """Generates deterministic UUIDv5 point IDs and upserts points to Qdrant."""
        point_ids: list[str] = [
            str(
                uuid.uuid5(
                    NAMESPACE_INGESTION, f"{job.collection_name}:{job.filepath}:{leaf.chunk_id}"
                )
            )
            for leaf in leaves
        ]

        if point_ids:
            points = [
                qmodels.PointStruct(
                    id=pid,
                    vector=vec,
                    payload=leaf.qdrant_payload,
                )
                for pid, vec, leaf in zip(point_ids, vectors, leaves)
            ]
            await self.qdrant_client.upsert(
                collection_name=job.collection_name,
                points=points,
            )
        return point_ids

    async def _process_job(self, job: Any) -> None:
        """Executes full extraction, hierarchical chunking, embedding, and Qdrant upsert/delete."""
        logger.info(
            f"Worker {self.worker_id} executing job #{job.id}: {job.action} on {job.filepath}"
        )

        current = self.queue.get_job_dto(job.id)
        if current and current.status == JobStatus.CANCELLED:
            logger.info(f"Job #{job.id} was cancelled before processing.")
            return

        if job.action in (JobAction.DELETE, JobAction.DELETED):
            await self._handle_deletion(job)
            return

        if job.action in (JobAction.UPDATE, JobAction.MODIFIED):
            await self._prune_existing_chunks(job)

        # 1. EXTRACTING
        self.queue.update_progress(
            job.id,
            self.worker_id,
            JobStage.EXTRACTING,
            JobProgress(pages_processed=0, total_pages=1, chunks_indexed=0, total_chunks=0),
        )
        text = self._extract_content(job.filepath)

        # 2. CHUNKING
        self.queue.update_progress(
            job.id,
            self.worker_id,
            JobStage.CHUNKING,
            JobProgress(pages_processed=1, total_pages=1, chunks_indexed=0, total_chunks=0),
        )
        leaves = self._chunk_document(text, job.filepath, job.id, job.options)
        total_chunks = len(leaves)

        # 3. EMBEDDING
        self.queue.update_progress(
            job.id,
            self.worker_id,
            JobStage.EMBEDDING,
            JobProgress(
                pages_processed=1, total_pages=1, chunks_indexed=0, total_chunks=total_chunks
            ),
        )
        texts_to_embed = [leaf.search_text for leaf in leaves]
        vectors = await self._generate_embeddings(texts_to_embed)

        dim = len(vectors[0]) if vectors else 768
        await self._ensure_collection_exists(job.collection_name, dimensions=dim)

        # 4. INDEXING
        self.queue.update_progress(
            job.id,
            self.worker_id,
            JobStage.INDEXING,
            JobProgress(
                pages_processed=1, total_pages=1, chunks_indexed=0, total_chunks=total_chunks
            ),
        )
        point_ids = await self._index_points(job, leaves, vectors)

        file_hash = self.delta_engine._calculate_file_sha256(job.filepath)
        mtime = os.path.getmtime(job.filepath)
        self.delta_engine.record_file_synced(
            filepath=job.filepath,
            collection_name=job.collection_name,
            file_hash=file_hash,
            last_modified=mtime,
            chunk_ids=point_ids,
        )

        # Mark job complete with worker fencing
        self.queue.update_progress(
            job.id,
            self.worker_id,
            JobStage.INDEXING,
            JobProgress(
                pages_processed=1,
                total_pages=1,
                chunks_indexed=total_chunks,
                total_chunks=total_chunks,
            ),
        )
        self.queue.complete_job(job.id, worker_id=self.worker_id)
        logger.info(f"Job #{job.id} completed successfully ({total_chunks} chunks indexed).")

    async def _prune_existing_chunks(self, job: Any) -> None:
        """Removes previously indexed chunk points for a modified file."""
        try:
            existing_ids = self.delta_engine.get_existing_chunk_ids(
                job.filepath, job.collection_name
            )
            if existing_ids:
                await self.qdrant_client.delete(
                    collection_name=job.collection_name,
                    points_selector=qmodels.PointIdsList(points=existing_ids),
                )
                logger.info(
                    f"Pruned {len(existing_ids)} old chunks for {job.filepath} in {job.collection_name}."
                )
        except Exception as e:
            logger.warning(f"Failed to prune old chunks for {job.filepath}: {e}")

    async def _handle_deletion(self, job: Any) -> None:
        """Handles DELETE job action by removing points from Qdrant and file state from SQLite."""
        existing_ids = self.delta_engine.remove_file_record(job.filepath, job.collection_name)
        if existing_ids:
            try:
                await self.qdrant_client.delete(
                    collection_name=job.collection_name,
                    points_selector=qmodels.PointIdsList(points=existing_ids),
                )
                logger.info(
                    f"Deleted {len(existing_ids)} vector points for {job.filepath} from {job.collection_name}."
                )
            except Exception as e:
                logger.warning(f"Error deleting points from Qdrant for {job.filepath}: {e}")

        self.queue.complete_job(job.id, worker_id=self.worker_id)
        logger.info(f"DELETE job #{job.id} for {job.filepath} completed successfully.")
