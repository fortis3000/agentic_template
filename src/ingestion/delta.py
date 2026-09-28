"""SQLite-backed Delta Synchronization Engine for Document Ingestion.

Implements DeltaSyncEngineProtocol to track document hashes, detect changes
(NEW, MODIFIED, DELETED), and identify orphaned vector point IDs.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3

from src.ingestion.contracts import (
    DeltaAction,
    DeltaSyncEngineProtocol,
    DeltaSyncResult,
    FileDelta,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SQLiteDeltaEngine(DeltaSyncEngineProtocol):
    """Tracks document synchronization state using an embedded SQLite database."""

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
                CREATE TABLE IF NOT EXISTS files (
                    filepath TEXT,
                    collection_name TEXT,
                    last_modified REAL,
                    hash TEXT,
                    chunk_ids TEXT,
                    PRIMARY KEY (filepath, collection_name)
                )
                """
            )
            self.conn.execute("PRAGMA journal_mode=WAL;")

    def _calculate_file_sha256(self, filepath: str) -> str:
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def compute_deltas(
        self,
        source_directory: str,
        collection_name: str,
        file_types: list[str],
    ) -> DeltaSyncResult:
        if not os.path.exists(source_directory):
            logger.warning(f"Source directory does not exist: {source_directory}")
            return DeltaSyncResult(
                source_directory=source_directory,
                collection_name=collection_name,
                scanned_count=0,
                deltas=[],
            )

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT filepath, hash, chunk_ids FROM files WHERE collection_name = ?",
            (collection_name,),
        )
        stored_records = {
            row["filepath"]: {
                "hash": row["hash"],
                "chunk_ids": json.loads(row["chunk_ids"] or "[]"),
            }
            for row in cursor.fetchall()
        }

        disk_files: set[str] = set()
        deltas: list[FileDelta] = []

        for root, _, files in os.walk(source_directory):
            for file in files:
                if any(file.endswith(ext) for ext in file_types):
                    full_path = os.path.join(root, file)
                    disk_files.add(full_path)
                    current_hash = self._calculate_file_sha256(full_path)
                    mtime = os.path.getmtime(full_path)

                    if full_path not in stored_records:
                        deltas.append(
                            FileDelta(
                                filepath=full_path,
                                collection_name=collection_name,
                                action=DeltaAction.ADD,
                                current_hash=current_hash,
                                stored_hash=None,
                                last_modified=mtime,
                                existing_chunk_ids=[],
                            )
                        )
                    elif stored_records[full_path]["hash"] != current_hash:
                        deltas.append(
                            FileDelta(
                                filepath=full_path,
                                collection_name=collection_name,
                                action=DeltaAction.UPDATE,
                                current_hash=current_hash,
                                stored_hash=stored_records[full_path]["hash"],
                                last_modified=mtime,
                                existing_chunk_ids=stored_records[full_path]["chunk_ids"],
                            )
                        )
                    else:
                        deltas.append(
                            FileDelta(
                                filepath=full_path,
                                collection_name=collection_name,
                                action=DeltaAction.UNCHANGED,
                                current_hash=current_hash,
                                stored_hash=current_hash,
                                last_modified=mtime,
                                existing_chunk_ids=stored_records[full_path]["chunk_ids"],
                            )
                        )

        # Check for deleted files (in SQLite, missing on disk)
        for stored_path, data in stored_records.items():
            if stored_path not in disk_files:
                deltas.append(
                    FileDelta(
                        filepath=stored_path,
                        collection_name=collection_name,
                        action=DeltaAction.DELETE,
                        current_hash="",
                        stored_hash=data["hash"],
                        last_modified=0.0,
                        existing_chunk_ids=data["chunk_ids"],
                    )
                )

        return DeltaSyncResult(
            source_directory=source_directory,
            collection_name=collection_name,
            scanned_count=len(disk_files),
            deltas=deltas,
        )

    def record_file_synced(
        self,
        filepath: str,
        collection_name: str,
        file_hash: str,
        last_modified: float,
        chunk_ids: list[str],
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO files (filepath, collection_name, last_modified, hash, chunk_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filepath, collection_name, last_modified, file_hash, json.dumps(chunk_ids)),
            )

    def get_existing_chunk_ids(self, filepath: str, collection_name: str) -> list[str]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT chunk_ids FROM files WHERE filepath = ? AND collection_name = ?",
            (filepath, collection_name),
        )
        row = cursor.fetchone()
        if row and row["chunk_ids"]:
            return json.loads(row["chunk_ids"])
        return []

    def remove_file_record(self, filepath: str, collection_name: str) -> list[str]:
        chunk_ids = self.get_existing_chunk_ids(filepath, collection_name)
        with self.conn:
            self.conn.execute(
                "DELETE FROM files WHERE filepath = ? AND collection_name = ?",
                (filepath, collection_name),
            )
        return chunk_ids
