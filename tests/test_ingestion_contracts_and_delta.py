"""Unit tests for ingestion leaf contracts, SQLiteJobQueue, and SQLiteDeltaEngine."""

from __future__ import annotations

import inspect
import os
import subprocess
import sys
import tempfile
import time

from src.ingestion import contracts
from src.ingestion.contracts import (
    ChunkingStrategy,
    CreateCollectionRequest,
    DeltaAction,
    DistanceMetric,
    IngestFileRequest,
    IngestSyncRequest,
    JobAction,
    JobProgress,
    JobStage,
    JobStatus,
    PdfExtractionTier,
)
from src.ingestion.delta import SQLiteDeltaEngine
from src.ingestion.queue import SQLiteJobQueue

EXPECTED_DEFAULT_CHUNK_SIZE = 350
EXPECTED_DEFAULT_DIMENSIONS = 768


def test_leaf_contracts_zero_internal_imports():
    """Verify that src.ingestion.contracts files contain zero internal project imports."""
    modules = [contracts.types, contracts.schemas, contracts.job_queue, contracts.delta_engine]
    for mod in modules:
        source = inspect.getsource(mod)
        for line in source.splitlines():
            clean_line = line.strip()
            if clean_line.startswith("import ") or clean_line.startswith("from "):
                assert not clean_line.startswith("from src."), (
                    f"Forbidden internal import in leaf contract: {clean_line}"
                )
                assert not clean_line.startswith("import src."), (
                    f"Forbidden internal import in leaf contract: {clean_line}"
                )


def test_subprocess_contracts_leaf_purity():
    """Verify that importing src.ingestion.contracts in isolation does not eagerly import pipeline/agents/tools."""
    code = (
        "import sys\n"
        "import src.ingestion.contracts\n"
        "leaked = [m for m in sys.modules if m.startswith('src.') "
        "and m not in ('src.ingestion', 'src.ingestion.contracts') "
        "and not m.startswith('src.ingestion.contracts.')]\n"
        "assert not leaked, f'Leaked modules: {leaked}'\n"
    )
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"Contract purity failed: {res.stderr}"


def test_contracts_schema_defaults():
    """Test schema instantiation and defaults."""
    req = IngestFileRequest(collection_name="test_col")
    assert req.collection_name == "test_col"
    assert req.chunk_size == EXPECTED_DEFAULT_CHUNK_SIZE
    assert req.chunking_strategy == ChunkingStrategy.HIERARCHICAL
    assert req.pdf_tier == PdfExtractionTier.TIER1_NATIVE

    sync_req = IngestSyncRequest(source_directory="/tmp/docs", collection_name="test_col")
    assert sync_req.prune_orphans is True
    assert ".pdf" in sync_req.file_types

    col_req = CreateCollectionRequest(collection_name="test_col", distance=DistanceMetric.COSINE)
    assert col_req.dimensions == EXPECTED_DEFAULT_DIMENSIONS
    assert col_req.enable_quantization is True


def test_sqlite_job_queue_lifecycle_and_fencing():
    """Test full lifecycle of job queue: enqueue, lease, progress, complete, prune, and lease fencing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_queue.db")
        queue = SQLiteJobQueue(db_path=db_path)

        # 1. Enqueue
        job_id = queue.enqueue(
            "/app/data/sample.pdf", "test_col", JobAction.NEW, {"chunk_size": 350}
        )
        assert job_id > 0

        job = queue.get_job_dto(job_id)
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.stage is None
        assert job.options == {"chunk_size": 350}

        # 2. Lease next job
        leased = queue.lease_next_job(worker_id="worker-1", lease_duration_seconds=10.0)
        assert leased is not None
        assert leased.id == job_id
        assert leased.status == JobStatus.RUNNING
        assert leased.stage == JobStage.EXTRACTING

        # 3. Heartbeat
        heartbeat_ok = queue.heartbeat(job_id, "worker-1", lease_duration_seconds=20.0)
        assert heartbeat_ok is True

        # Stale worker heartbeat should fail
        assert queue.heartbeat(job_id, "worker-stale") is False

        # 4. Progress Update with lease fencing
        prog = JobProgress(pages_processed=1, total_pages=5, chunks_indexed=3, total_chunks=15)
        # Stale worker cannot update progress
        assert queue.update_progress(job_id, "worker-stale", JobStage.CHUNKING, prog) is False

        prog_ok = queue.update_progress(job_id, "worker-1", JobStage.CHUNKING, prog)
        assert prog_ok is True

        job_updated = queue.get_job_dto(job_id)
        assert job_updated is not None
        assert job_updated.stage == JobStage.CHUNKING
        assert job_updated.progress.pages_processed == 1

        # 5. Complete Job with lease fencing
        assert queue.complete_job(job_id, worker_id="worker-stale") is False

        complete_ok = queue.complete_job(job_id, worker_id="worker-1")
        assert complete_ok is True

        job_completed = queue.get_job_dto(job_id)
        assert job_completed is not None
        assert job_completed.status == JobStatus.COMPLETED
        assert job_completed.completed_at is not None

        # Verify fail_job does not overwrite terminal COMPLETED state
        assert queue.fail_job(job_id, worker_id="worker-1", error="late failure") is False
        job_after_fail = queue.get_job_dto(job_id)
        assert job_after_fail is not None
        assert job_after_fail.status == JobStatus.COMPLETED


def test_sqlite_job_queue_crash_recovery_and_pruning():
    """Test recovery of orphaned jobs with expired leases and retention pruning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_queue.db")
        queue = SQLiteJobQueue(db_path=db_path)

        job_id = queue.enqueue("/app/data/sample.pdf", "test_col", JobAction.NEW)
        # Lease with 0.01s expiration
        leased = queue.lease_next_job(worker_id="worker-crash", lease_duration_seconds=0.01)
        assert leased is not None
        time.sleep(0.05)  # Wait for lease to expire

        # Sweep should recover this job back to PENDING (retry 1)
        recovered = queue.recover_stale_leases(max_retries=3)
        assert recovered == 1

        job_recovered = queue.get_job_dto(job_id)
        assert job_recovered is not None
        assert job_recovered.status == JobStatus.PENDING
        assert job_recovered.retry_count == 1
        assert job_recovered.worker_id is None

        # Exceed max retries: lease again with 0.01s and sweep
        queue.lease_next_job(worker_id="worker-crash-2", lease_duration_seconds=0.01)
        time.sleep(0.05)
        # Now sweep with max_retries=1 to trigger terminal failure
        recovered_terminal = queue.recover_stale_leases(max_retries=1)
        assert recovered_terminal == 1

        job_failed = queue.get_job_dto(job_id)
        assert job_failed is not None
        assert job_failed.status == JobStatus.FAILED
        assert job_failed.completed_at is not None  # Must be set so it can be pruned

        # Prune with retention_days=0 should delete the failed job
        pruned = queue.prune_old_jobs(retention_days=0)
        assert pruned == 1
        assert queue.get_job_dto(job_id) is None


def test_sqlite_delta_engine_change_detection_and_scoping():
    """Test SQLiteDeltaEngine detecting ADD, UPDATE, UNCHANGED, and DELETE with directory scoping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "state.db")
        docs_dir = os.path.join(tmpdir, "docs")
        other_dir = os.path.join(tmpdir, "other_docs")
        os.makedirs(docs_dir, exist_ok=True)
        os.makedirs(other_dir, exist_ok=True)

        engine = SQLiteDeltaEngine(db_path=db_path)
        file1 = os.path.join(docs_dir, "doc1.txt")
        file2 = os.path.join(other_dir, "doc2.PDF")  # Upper-case extension
        with open(file1, "w") as f:
            f.write("Initial content version 1")
        with open(file2, "w") as f:
            f.write("Other directory content")

        # 1. Scan docs_dir with case-insensitive extension
        result1 = engine.compute_deltas(docs_dir, "col1", [".txt"])
        assert result1.scanned_count == 1
        assert len(result1.deltas) == 1
        assert result1.deltas[0].action == DeltaAction.ADD

        # Record file1 and file2 as synced into col1
        h1 = result1.deltas[0].current_hash
        mtime1 = os.path.getmtime(file1)
        engine.record_file_synced(file1, "col1", h1, mtime1, ["chunk-1", "chunk-2"])

        result_other = engine.compute_deltas(other_dir, "col1", ["pdf"])
        assert len(result_other.deltas) == 1
        assert result_other.deltas[0].action == DeltaAction.ADD
        engine.record_file_synced(file2, "col1", "hash2", os.path.getmtime(file2), ["chunk-3"])

        # 2. Rescanning docs_dir MUST NOT mark file2 in other_dir as DELETE!
        result2 = engine.compute_deltas(docs_dir, "col1", [".txt"])
        assert len(result2.deltas) == 1
        assert result2.deltas[0].action == DeltaAction.UNCHANGED
        assert not any(d.action == DeltaAction.DELETE for d in result2.deltas)

        # 3. Modify content of file1 should detect UPDATE
        with open(file1, "w") as f:
            f.write("Modified content version 2")

        result3 = engine.compute_deltas(docs_dir, "col1", [".txt"])
        assert len(result3.deltas) == 1
        assert result3.deltas[0].action == DeltaAction.UPDATE
        assert result3.deltas[0].existing_chunk_ids == ["chunk-1", "chunk-2"]

        # 4. Delete file1 from disk should detect DELETE strictly scoped to docs_dir
        os.remove(file1)
        result4 = engine.compute_deltas(docs_dir, "col1", [".txt"])
        assert len(result4.deltas) == 1
        assert result4.deltas[0].action == DeltaAction.DELETE
        assert result4.deltas[0].existing_chunk_ids == ["chunk-1", "chunk-2"]

        # Remove record
        purged_ids = engine.remove_file_record(file1, "col1")
        assert purged_ids == ["chunk-1", "chunk-2"]
