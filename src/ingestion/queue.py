"""SQLite-backed persistent job queue implementation for Ingestion Service.

Implements JobQueueProtocol adhering to Leaf Contracts with WAL mode,
worker leasing, heartbeat tracking, and automatic crash recovery sweeps.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any

from src.ingestion.contracts import (
    IngestJobDTO,
    IngestJobResponse,
    JobAction,
    JobProgress,
    JobQueueProtocol,
    JobStage,
    JobStatus,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteJobQueue(JobQueueProtocol):
    """Persistent job queue backed by SQLite in WAL mode."""

    def __init__(self, db_path: str = "data/ingestion_state.db") -> None:
        self.db_path = db_path
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        with self.conn:
            self.conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ingest_jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filepath TEXT NOT NULL,
                    collection_name TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress TEXT NOT NULL,
                    worker_id TEXT,
                    lease_expires_at REAL,
                    retry_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    error TEXT
                )
                """
            )
            self.conn.execute("PRAGMA journal_mode=WAL;")

    def enqueue(self, filepath: str, collection_name: str, action: JobAction) -> int:
        now = time.time()
        initial_progress = json.dumps(
            {"pages_processed": 0, "total_pages": 0, "chunks_indexed": 0, "total_chunks": 0}
        )
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO ingest_jobs (
                    filepath, collection_name, action, status, stage,
                    progress, retry_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    filepath,
                    collection_name,
                    action.value,
                    JobStatus.PENDING.value,
                    JobStage.QUEUED.value,
                    initial_progress,
                    now,
                ),
            )
            job_id = cursor.lastrowid
            if job_id is None:
                raise RuntimeError("Failed to retrieve lastrowid for enqueued job")
            return job_id

    def lease_next_job(
        self, worker_id: str, lease_duration_seconds: float = 300.0
    ) -> IngestJobDTO | None:
        now = time.time()
        lease_expires = now + lease_duration_seconds
        with self.conn:
            cursor = self.conn.execute(
                """
                SELECT id FROM ingest_jobs
                WHERE status = ?
                ORDER BY id ASC
                LIMIT 1
                """,
                (JobStatus.PENDING.value,),
            )
            row = cursor.fetchone()
            if not row:
                return None

            job_id = row["id"]
            self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, worker_id = ?, lease_expires_at = ?, stage = ?
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.RUNNING.value,
                    worker_id,
                    lease_expires,
                    JobStage.EXTRACTING.value,
                    job_id,
                    JobStatus.PENDING.value,
                ),
            )

        return self.get_job_dto(job_id)

    def heartbeat(self, job_id: int, worker_id: str, lease_duration_seconds: float = 300.0) -> bool:
        new_expires = time.time() + lease_duration_seconds
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET lease_expires_at = ?
                WHERE id = ? AND worker_id = ? AND status = ?
                """,
                (new_expires, job_id, worker_id, JobStatus.RUNNING.value),
            )
            return cursor.rowcount > 0

    def update_progress(self, job_id: int, stage: JobStage, progress: JobProgress) -> bool:
        progress_json = json.dumps(
            {
                "pages_processed": progress.pages_processed,
                "total_pages": progress.total_pages,
                "chunks_indexed": progress.chunks_indexed,
                "total_chunks": progress.total_chunks,
            }
        )
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET stage = ?, progress = ?
                WHERE id = ? AND status = ?
                """,
                (stage.value, progress_json, job_id, JobStatus.RUNNING.value),
            )
            return cursor.rowcount > 0

    def complete_job(self, job_id: int) -> bool:
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, stage = ?, completed_at = ?, lease_expires_at = NULL
                WHERE id = ? AND status = ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    JobStage.DONE.value,
                    now,
                    job_id,
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount > 0

    def fail_job(self, job_id: int, error: str) -> bool:
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, error = ?, completed_at = ?, lease_expires_at = NULL
                WHERE id = ?
                """,
                (JobStatus.FAILED.value, error, now, job_id),
            )
            return cursor.rowcount > 0

    def cancel_job(self, job_id: int) -> bool:
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, completed_at = ?, lease_expires_at = NULL
                WHERE id = ? AND status IN (?, ?)
                """,
                (
                    JobStatus.CANCELLED.value,
                    now,
                    job_id,
                    JobStatus.PENDING.value,
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount > 0

    def get_job_dto(self, job_id: int) -> IngestJobDTO | None:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        prog_data = json.loads(row["progress"] or "{}")
        progress = JobProgress(
            pages_processed=prog_data.get("pages_processed", 0),
            total_pages=prog_data.get("total_pages", 0),
            chunks_indexed=prog_data.get("chunks_indexed", 0),
            total_chunks=prog_data.get("total_chunks", 0),
        )
        return IngestJobDTO(
            id=row["id"],
            filepath=row["filepath"],
            collection_name=row["collection_name"],
            action=JobAction(row["action"]),
            status=JobStatus(row["status"]),
            stage=JobStage(row["stage"]),
            progress=progress,
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

    def get_job(self, job_id: int) -> IngestJobResponse | None:
        dto = self.get_job_dto(job_id)
        if not dto:
            return None
        return IngestJobResponse(
            id=dto.id,
            filepath=dto.filepath,
            collection_name=dto.collection_name,
            action=dto.action.value,
            status=dto.status.value,
            stage=dto.stage.value,
            progress={
                "pages_processed": dto.progress.pages_processed,
                "total_pages": dto.progress.total_pages,
                "chunks_indexed": dto.progress.chunks_indexed,
                "total_chunks": dto.progress.total_chunks,
            },
            retry_count=dto.retry_count,
            created_at=dto.created_at,
            completed_at=dto.completed_at,
            error=dto.error,
        )

    def list_jobs(
        self,
        collection_name: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[IngestJobResponse]:
        query = "SELECT id FROM ingest_jobs WHERE 1=1"
        params: list[Any] = []
        if collection_name:
            query += " AND collection_name = ?"
            params.append(collection_name)
        if status:
            query += " AND status = ?"
            params.append(status.value)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        cursor = self.conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        jobs: list[IngestJobResponse] = []
        for r in rows:
            resp = self.get_job(r["id"])
            if resp:
                jobs.append(resp)
        return jobs

    def recover_stale_leases(self, max_retries: int = 3) -> int:
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = CASE
                    WHEN retry_count < ? THEN ?
                    ELSE ?
                END,
                stage = CASE
                    WHEN retry_count < ? THEN ?
                    ELSE ?
                END,
                retry_count = retry_count + 1,
                worker_id = NULL,
                lease_expires_at = NULL,
                error = CASE
                    WHEN retry_count >= ? THEN 'Exceeded max retry attempts after worker lease expiration'
                    ELSE error
                END
                WHERE status = ? AND lease_expires_at IS NOT NULL AND lease_expires_at < ?
                """,
                (
                    max_retries,
                    JobStatus.PENDING.value,
                    JobStatus.FAILED.value,
                    max_retries,
                    JobStage.QUEUED.value,
                    JobStage.DONE.value,
                    max_retries,
                    JobStatus.RUNNING.value,
                    now,
                ),
            )
            recovered = cursor.rowcount
            if recovered > 0:
                logger.info(f"Recovered {recovered} stale job leases.")
            return recovered

    def prune_old_jobs(self, retention_days: int = 7) -> int:
        cutoff = time.time() - (retention_days * 86400)
        with self.conn:
            cursor = self.conn.execute(
                """
                DELETE FROM ingest_jobs
                WHERE status IN (?, ?, ?) AND completed_at IS NOT NULL AND completed_at < ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    JobStatus.FAILED.value,
                    JobStatus.CANCELLED.value,
                    cutoff,
                ),
            )
            pruned = cursor.rowcount
            if pruned > 0:
                logger.info(f"Pruned {pruned} old ingestion jobs.")
            return pruned
