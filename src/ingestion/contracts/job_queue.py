"""Protocol defining the interface for persistent ingestion job queues.

Contains zero internal project imports (standard library only) to ensure
clean dependency inversion and zero circular dependencies.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schemas import IngestJobDTO, IngestJobResponse, JobProgress
from .types import JobAction, JobStage, JobStatus


@runtime_checkable
class JobQueueProtocol(Protocol):
    """Protocol for enqueueing, leasing, heartbeating, and updating ingestion jobs."""

    def enqueue(self, filepath: str, collection_name: str, action: JobAction) -> int:
        """Enqueues a new job and returns its integer ID."""
        ...

    def lease_next_job(
        self, worker_id: str, lease_duration_seconds: float = 300.0
    ) -> IngestJobDTO | None:
        """Leases the next pending job to the specified worker."""
        ...

    def heartbeat(self, job_id: int, worker_id: str, lease_duration_seconds: float = 300.0) -> bool:
        """Extends the lease expiration timestamp for an active job."""
        ...

    def update_progress(self, job_id: int, stage: JobStage, progress: JobProgress) -> bool:
        """Updates the active stage and quantitative progress metrics."""
        ...

    def complete_job(self, job_id: int) -> bool:
        """Marks a job as COMPLETED."""
        ...

    def fail_job(self, job_id: int, error: str) -> bool:
        """Marks a job as FAILED with an error message."""
        ...

    def cancel_job(self, job_id: int) -> bool:
        """Cancels a pending or running job."""
        ...

    def get_job(self, job_id: int) -> IngestJobResponse | None:
        """Fetches public response representation of a job."""
        ...

    def list_jobs(
        self,
        collection_name: str | None = None,
        status: JobStatus | None = None,
        limit: int = 50,
    ) -> list[IngestJobResponse]:
        """Lists jobs matching optional filters."""
        ...

    def recover_stale_leases(self, max_retries: int = 3) -> int:
        """Recovers abandoned RUNNING jobs whose leases have expired."""
        ...

    def prune_old_jobs(self, retention_days: int = 7) -> int:
        """Prunes terminal jobs older than the retention period."""
        ...
