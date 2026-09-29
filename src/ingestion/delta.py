"""SQLite-backed Delta Synchronization Engine for Document Ingestion.

Tracks document hashes, detects changes (ADD, UPDATE, DELETE, UNCHANGED),
and identifies orphaned vector point IDs with directory-scoped tracking.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from typing import TypedDict

from src.ingestion.contracts import (
    DeltaAction,
    DeltaSyncResult,
    FileDelta,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


class StoredRecord(TypedDict):
    hash: str
    last_modified: float
    chunk_ids: list[str]


class SQLiteDeltaEngine:
    """Tracks document synchronization state using an embedded SQLite database."""

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

        real_source_dir = os.path.realpath(source_directory)
        normalized_exts = {
            ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in file_types
        }

        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT filepath, hash, chunk_ids, last_modified FROM files WHERE collection_name = ?",
            (collection_name,),
        )
        stored_records: dict[str, StoredRecord] = {
            os.path.realpath(row["filepath"]): {
                "hash": str(row["hash"]),
                "last_modified": float(row["last_modified"] or 0.0),
                "chunk_ids": list(json.loads(row["chunk_ids"] or "[]")),
            }
            for row in cursor.fetchall()
        }

        disk_files: set[str] = set()
        deltas: list[FileDelta] = []

        for root, _, files in os.walk(real_source_dir):
            for file in files:
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext in normalized_exts:
                    full_path = os.path.realpath(os.path.join(root, file))
                    disk_files.add(full_path)
                    mtime = os.path.getmtime(full_path)

                    stored_info = stored_records.get(full_path)
                    if stored_info is None:
                        current_hash = self._calculate_file_sha256(full_path)
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
                    else:
                        # Fast path: check mtime before computing SHA-256
                        current_hash: str = (
                            stored_info["hash"]
                            if stored_info["last_modified"] == mtime
                            else self._calculate_file_sha256(full_path)
                        )

                        if stored_info["hash"] != current_hash:
                            deltas.append(
                                FileDelta(
                                    filepath=full_path,
                                    collection_name=collection_name,
                                    action=DeltaAction.UPDATE,
                                    current_hash=current_hash,
                                    stored_hash=stored_info["hash"],
                                    last_modified=mtime,
                                    existing_chunk_ids=stored_info["chunk_ids"],
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
                                    existing_chunk_ids=stored_info["chunk_ids"],
                                )
                            )

        # Check for deleted files: strictly scoped to paths under real_source_dir matching file_types
        source_dir_prefix = real_source_dir + os.sep
        for stored_path, data in stored_records.items():
            is_under_source = (
                stored_path.startswith(source_dir_prefix) or stored_path == real_source_dir
            )
            ext = os.path.splitext(stored_path)[1].lower()
            if is_under_source and ext in normalized_exts and stored_path not in disk_files:
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
        real_path = os.path.realpath(filepath)
        with self.conn:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO files (filepath, collection_name, last_modified, hash, chunk_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (real_path, collection_name, last_modified, file_hash, json.dumps(chunk_ids)),
            )

    def get_existing_chunk_ids(self, filepath: str, collection_name: str) -> list[str]:
        real_path = os.path.realpath(filepath)
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT chunk_ids FROM files WHERE filepath = ? AND collection_name = ?",
            (real_path, collection_name),
        )
        row = cursor.fetchone()
        if row and row["chunk_ids"]:
            return json.loads(row["chunk_ids"])
        return []

    def remove_file_record(self, filepath: str, collection_name: str) -> list[str]:
        real_path = os.path.realpath(filepath)
        chunk_ids = self.get_existing_chunk_ids(real_path, collection_name)
        with self.conn:
            self.conn.execute(
                "DELETE FROM files WHERE filepath = ? AND collection_name = ?",
                (real_path, collection_name),
            )
        return chunk_ids
