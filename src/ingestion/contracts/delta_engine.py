"""Protocol defining the interface for document delta synchronization engines.

Contains zero internal project imports (standard library only) to ensure
clean dependency inversion and zero circular dependencies.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schemas import DeltaSyncResult


@runtime_checkable
class DeltaSyncEngineProtocol(Protocol):
    """Protocol for scanning file changes, recording state, and identifying orphaned chunks."""

    def compute_deltas(
        self,
        source_directory: str,
        collection_name: str,
        file_types: list[str],
    ) -> DeltaSyncResult:
        """Scans a directory and returns files classified as ADD, UPDATE, DELETE, or UNCHANGED."""
        ...

    def record_file_synced(
        self,
        filepath: str,
        collection_name: str,
        file_hash: str,
        last_modified: float,
        chunk_ids: list[str],
    ) -> None:
        """Records or updates a file's synchronized state in the tracking database."""
        ...

    def get_existing_chunk_ids(self, filepath: str, collection_name: str) -> list[str]:
        """Retrieves previously indexed chunk IDs for a file."""
        ...

    def remove_file_record(self, filepath: str, collection_name: str) -> list[str]:
        """Removes a file record and returns its orphaned chunk IDs for deletion from vector DB."""
        ...
