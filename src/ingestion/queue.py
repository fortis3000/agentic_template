"""SQLite-backed persistent job queue implementation for Ingestion Service.

Implements JobQueueProtocol adhering to Leaf Contracts with WAL mode,
atomic worker leasing, lease fencing, heartbeat tracking, and automatic crash recovery sweeps.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time

from src.ingestion.contracts import (
    IngestJobDTO,
    JobAction,
    JobProgress,
    JobStage,
    JobStatus,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteJobQueue:
    """Persistent job queue backed by SQLite in WAL mode."""

    def __init__(self, db_path: str = "data/service_ingestion_state.db") -> None:
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
                    stage TEXT,
                    progress TEXT NOT NULL,
                    options TEXT,
                    worker_id TEXT,
                    lease_expires_at REAL,
                    retry_count INTEGER DEFAULT 0,
                    created_at REAL NOT NULL,
                    completed_at REAL,
                    error TEXT
                )
                """
            )
            # Ensure options column exists if migrating an existing DB
            cursor = self.conn.execute("PRAGMA table_info(ingest_jobs)")
            cols = [row["name"] for row in cursor.fetchall()]
            if "options" not in cols:
                self.conn.execute("ALTER TABLE ingest_jobs ADD COLUMN options TEXT")
            self.conn.execute("PRAGMA journal_mode=WAL;")

    def enqueue(
        self,
        filepath: str,
        collection_name: str,
        action: JobAction,
        options: dict[str, str | int | float | bool] | None = None,
    ) -> int:
        now = time.time()
        initial_progress = json.dumps(JobProgress().to_dict())
        options_json = json.dumps(options or {})
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO ingest_jobs (
                    filepath, collection_name, action, status, stage,
                    progress, options, retry_count, created_at
                )
                VALUES (?, ?, ?, ?, NULL, ?, ?, 0, ?)
                """,
                (
                    filepath,
                    collection_name,
                    action.value,
                    JobStatus.PENDING.value,
                    initial_progress,
                    options_json,
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
        """Atomically leases the next pending job to the specified worker."""
        now = time.time()
        lease_expires = now + lease_duration_seconds
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, worker_id = ?, lease_expires_at = ?, stage = ?
                WHERE id = (
                    SELECT id FROM ingest_jobs
                    WHERE status = ?
                    ORDER BY id ASC
                    LIMIT 1
                )
                RETURNING id
                """,
                (
                    JobStatus.RUNNING.value,
                    worker_id,
                    lease_expires,
                    JobStage.EXTRACTING.value,
                    JobStatus.PENDING.value,
                ),
            )
            row = cursor.fetchone()
            if not row:
                return None
            job_id = row[0]

        return self.get_job_dto(job_id)

    def heartbeat(self, job_id: int, worker_id: str, lease_duration_seconds: float = 300.0) -> bool:
        """Extends the lease expiration timestamp for an active job held by worker_id."""
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

    def update_progress(
        self, job_id: int, worker_id: str, stage: JobStage, progress: JobProgress
    ) -> bool:
        """Updates the active stage and quantitative progress metrics with lease fencing."""
        progress_json = json.dumps(progress.to_dict())
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET stage = ?, progress = ?
                WHERE id = ? AND worker_id = ? AND status = ?
                """,
                (stage.value, progress_json, job_id, worker_id, JobStatus.RUNNING.value),
            )
            return cursor.rowcount > 0

    def complete_job(self, job_id: int, worker_id: str) -> bool:
        """Marks a job as COMPLETED with worker lease fencing."""
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, completed_at = ?, lease_expires_at = NULL
                WHERE id = ? AND worker_id = ? AND status = ?
                """,
                (
                    JobStatus.COMPLETED.value,
                    now,
                    job_id,
                    worker_id,
                    JobStatus.RUNNING.value,
                ),
            )
            return cursor.rowcount > 0

    def fail_job(self, job_id: int, worker_id: str, error: str) -> bool:
        """Marks a job as FAILED with an error message and worker lease fencing."""
        now = time.time()
        with self.conn:
            cursor = self.conn.execute(
                """
                UPDATE ingest_jobs
                SET status = ?, error = ?, completed_at = ?, lease_expires_at = NULL
                WHERE id = ? AND worker_id = ? AND status = ?
                """,
                (JobStatus.FAILED.value, error, now, job_id, worker_id, JobStatus.RUNNING.value),
            )
            return cursor.rowcount > 0

    def cancel_job(self, job_id: int) -> bool:
        """Cancels a pending or running job."""
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
        """Fetches the internal DTO representation of a job."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM ingest_jobs WHERE id = ?", (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        prog_data = json.loads(row["progress"] or "{}")
        progress = JobProgress.from_dict(prog_data)
        options = json.loads(row["options"] or "{}") if "options" in row.keys() else {}
        stage_val = JobStage(row["stage"]) if row["stage"] else None
        return IngestJobDTO(
            id=row["id"],
            filepath=row["filepath"],
            collection_name=row["collection_name"],
            action=JobAction(row["action"]),
            status=JobStatus(row["status"]),
            stage=stage_val,
            progress=progress,
            options=options,
            worker_id=row["worker_id"],
            lease_expires_at=row["lease_expires_at"],
            retry_count=row["retry_count"],
            created_at=row["created_at"],
            completed_at=row["completed_at"],
            error=row["error"],
        )

    def get_job(self, job_id: int) -> IngestJobDTO | None:
        """Protocol conformance method returning IngestJobDTO."""
        return self.get_job_dto(job_id)

    def list_jobs(
        self,
        collection_name: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[IngestJobDTO]:
        query = "SELECT id FROM ingest_jobs WHERE 1=1"
        params: list[str | int] = []
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
        jobs: list[IngestJobDTO] = []
        for r in rows:
            dto = self.get_job_dto(r["id"])
            if dto:
                jobs.append(dto)
        return jobs

    def recover_stale_leases(self, max_retries: int = 3) -> int:
        """Recovers abandoned RUNNING jobs whose leases have expired.

        Sets completed_at when status becomes FAILED so jobs can be pruned.
        """
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
                    WHEN retry_count < ? THEN NULL
                    ELSE stage
                END,
                retry_count = retry_count + 1,
                worker_id = NULL,
                lease_expires_at = NULL,
                completed_at = CASE
                    WHEN retry_count >= ? THEN ?
                    ELSE completed_at
                END,
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
                    max_retries,
                    now,
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
        """Prunes terminal jobs older than the retention period."""
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
