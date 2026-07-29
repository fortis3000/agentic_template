import argparse
import asyncio
import hashlib
import json
import os
import sqlite3
import time
from typing import Any

import yaml
from pydantic import BaseModel, Field

from src.agents.embeddings import EmbeddingModelConfigSchema, EmbeddingModelFactory
from src.ingestion.helper import ingest_document
from src.tools.vectordb_base import VectorDBFactory
from src.utils.logger import get_logger

logger = get_logger(__name__)


class IngestionConfigSchema(BaseModel):
    source_directory: str
    collection_name: str
    chunk_size: int = 500
    chunk_overlap: int = 50
    file_types: list[str] = Field(default_factory=lambda: [".pdf", ".txt", ".md", ".html"])
    embedding_model: EmbeddingModelConfigSchema
    vectordb: dict[str, Any] = Field(
        default_factory=lambda: {"type": "qdrant", "host": "localhost", "port": 6333}
    )
    state_db_path: str = "data/ingestion_state.db"
    chunking_strategy: str = "fixed"  # "fixed", "markdown", "semantic"
    semantic_threshold: float = 0.5


class IngestionPipeline:
    """Ingestion pipeline that supports delta updates and job queue persistence."""

    def __init__(self, config: IngestionConfigSchema):
        self.config = config

        # Ensure data folder exists for state database
        state_dir = os.path.dirname(config.state_db_path)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)

        self.conn = sqlite3.connect(config.state_db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        """Initialize tables for delta tracking and job queuing."""
        cursor = self.conn.cursor()
        cursor.execute(
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS ingest_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filepath TEXT,
                collection_name TEXT,
                action TEXT, -- 'NEW', 'MODIFIED', 'DELETED'
                status TEXT, -- 'PENDING', 'RUNNING', 'COMPLETED', 'FAILED'
                created_at REAL,
                completed_at REAL,
                error TEXT
            )
            """
        )
        self.conn.commit()

    def _calculate_file_sha256(self, filepath: str) -> str:
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def check_deltas_and_queue_jobs(self) -> int:
        """Scan directory and enqueue jobs for new, modified, or deleted files."""
        logger.info(f"Scanning directory: {self.config.source_directory}")
        if not os.path.exists(self.config.source_directory):
            logger.error(f"Source directory does not exist: {self.config.source_directory}")
            return 0

        cursor = self.conn.cursor()

        # 1. Clear completed/failed jobs from previous runs to keep queue clean
        cursor.execute(
            "DELETE FROM ingest_jobs WHERE collection_name = ?", (self.config.collection_name,)
        )
        self.conn.commit()

        # 2. Scan folder
        scanned_files = {}
        for root, _, files in os.walk(self.config.source_directory):
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.config.file_types:
                    filepath = os.path.join(root, file)
                    mtime = os.path.getmtime(filepath)
                    scanned_files[filepath] = mtime

        # 3. Check for new or modified files
        new_or_modified_count = 0
        for filepath, mtime in scanned_files.items():
            file_hash = self._calculate_file_sha256(filepath)

            cursor.execute(
                "SELECT last_modified, hash FROM files WHERE filepath = ? AND collection_name = ?",
                (filepath, self.config.collection_name),
            )
            row = cursor.fetchone()

            if not row:
                # File is new
                logger.info(f"Detected new file: {filepath}")
                cursor.execute(
                    """
                    INSERT INTO ingest_jobs (filepath, collection_name, action, status, created_at)
                    VALUES (?, ?, 'NEW', 'PENDING', ?)
                    """,
                    (filepath, self.config.collection_name, time.time()),
                )
                new_or_modified_count += 1
            else:
                db_mtime = row["last_modified"]
                db_hash = row["hash"]
                if mtime != db_mtime or file_hash != db_hash:
                    # File is modified
                    logger.info(f"Detected modified file: {filepath}")
                    cursor.execute(
                        """
                        INSERT INTO ingest_jobs (filepath, collection_name, action, status, created_at)
                        VALUES (?, ?, 'MODIFIED', 'PENDING', ?)
                        """,
                        (filepath, self.config.collection_name, time.time()),
                    )
                    new_or_modified_count += 1

        # 4. Check for deleted files
        cursor.execute(
            "SELECT filepath FROM files WHERE collection_name = ?", (self.config.collection_name,)
        )
        db_files = [row["filepath"] for row in cursor.fetchall()]

        deleted_count = 0
        for db_filepath in db_files:
            if db_filepath not in scanned_files:
                logger.info(f"Detected deleted file: {db_filepath}")
                cursor.execute(
                    """
                    INSERT INTO ingest_jobs (filepath, collection_name, action, status, created_at)
                    VALUES (?, ?, 'DELETED', 'PENDING', ?)
                    """,
                    (db_filepath, self.config.collection_name, time.time()),
                )
                deleted_count += 1

        self.conn.commit()
        total_jobs = new_or_modified_count + deleted_count
        logger.info(
            f"Scan complete. Enqueued {total_jobs} ingestion jobs ({new_or_modified_count} new/modified, {deleted_count} deleted)."
        )
        return total_jobs

    async def process_queue(self) -> None:
        """Process all pending ingestion jobs sequentially."""
        cursor = self.conn.cursor()

        # Instantiate VectorDB and Embedding clients
        db_cfg = self.config.vectordb.copy()
        db_type = db_cfg.pop("type", "qdrant")
        vectordb = VectorDBFactory.create(db_type, **db_cfg)

        # Onboard embedding model
        embed_client = EmbeddingModelFactory.create(self.config.embedding_model)
        dim = self.config.embedding_model.dimensions
        if not dim:
            # Probe dimension if not defined
            probe = await embed_client.embed_text("probe")
            dim = probe.dimensions
            self.config.embedding_model.dimensions = dim

        # Ensure collection exists in VectorDB
        await vectordb.create_collection(self.config.collection_name, vector_size=dim)

        while True:
            cursor.execute(
                """
                SELECT id, filepath, action FROM ingest_jobs 
                WHERE collection_name = ? AND status = 'PENDING' 
                ORDER BY id LIMIT 1
                """,
                (self.config.collection_name,),
            )
            job = cursor.fetchone()
            if not job:
                break

            job_id = job["id"]
            filepath = job["filepath"]
            action = job["action"]

            logger.info(f"Processing job {job_id}: {action} for {filepath}")
            cursor.execute(
                "UPDATE ingest_jobs SET status = 'RUNNING' WHERE id = ?",
                (job_id,),
            )
            self.conn.commit()

            try:
                await self._process_job(cursor, filepath, action, vectordb, embed_client)
                cursor.execute(
                    "UPDATE ingest_jobs SET status = 'COMPLETED', completed_at = ? WHERE id = ?",
                    (time.time(), job_id),
                )
                logger.info(f"Successfully processed job {job_id} for {filepath}")
            except Exception as e:
                logger.error(f"Failed to process job {job_id} for {filepath}: {e}")
                cursor.execute(
                    "UPDATE ingest_jobs SET status = 'FAILED', error = ?, completed_at = ? WHERE id = ?",
                    (str(e), time.time(), job_id),
                )

            self.conn.commit()

    async def _process_job(
        self,
        cursor: sqlite3.Cursor,
        filepath: str,
        action: str,
        vectordb: Any,
        embed_client: Any,
    ) -> None:
        """Internal helper to process a single NEW, MODIFIED, or DELETED file job."""
        if action == "DELETED":
            # Delete existing chunks from VectorDB
            cursor.execute(
                "SELECT chunk_ids FROM files WHERE filepath = ? AND collection_name = ?",
                (filepath, self.config.collection_name),
            )
            file_row = cursor.fetchone()
            if file_row and file_row["chunk_ids"]:
                chunk_ids = json.loads(file_row["chunk_ids"])
                await vectordb.delete(self.config.collection_name, chunk_ids)

            cursor.execute(
                "DELETE FROM files WHERE filepath = ? AND collection_name = ?",
                (filepath, self.config.collection_name),
            )

        elif action in ("NEW", "MODIFIED"):
            if action == "MODIFIED":
                # Delete existing chunks first
                cursor.execute(
                    "SELECT chunk_ids FROM files WHERE filepath = ? AND collection_name = ?",
                    (filepath, self.config.collection_name),
                )
                file_row = cursor.fetchone()
                if file_row and file_row["chunk_ids"]:
                    chunk_ids = json.loads(file_row["chunk_ids"])
                    await vectordb.delete(self.config.collection_name, chunk_ids)

            # Extract, chunk and ingest using shared utility
            with open(filepath, "rb") as f:
                file_data = f.read()

            ext = os.path.splitext(filepath)[1].lower()
            mime_type = "text/plain"
            if ext == ".pdf":
                mime_type = "application/pdf"
            elif ext == ".md":
                mime_type = "text/markdown"
            elif ext == ".html":
                mime_type = "text/html"

            chunk_ids = await ingest_document(
                filepath=filepath,
                file_bytes=file_data,
                mime_type=mime_type,
                config=self.config,
                vectordb=vectordb,
                embed_client=embed_client,
            )

            # Save / Update file state in SQLite
            file_hash = self._calculate_file_sha256(filepath)
            mtime = os.path.getmtime(filepath)
            cursor.execute(
                """
                INSERT OR REPLACE INTO files (filepath, collection_name, last_modified, hash, chunk_ids)
                VALUES (?, ?, ?, ?, ?)
                """,
                (filepath, self.config.collection_name, mtime, file_hash, json.dumps(chunk_ids)),
            )

    def close(self) -> None:
        self.conn.close()


async def run_pipeline(config_path: str) -> None:
    """Run ingestion pipeline using a configuration YAML file."""
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Allow custom ingestion key resolving config
    config = IngestionConfigSchema.model_validate(data)
    pipeline = IngestionPipeline(config)
    try:
        jobs_count = pipeline.check_deltas_and_queue_jobs()
        if jobs_count > 0:
            await pipeline.process_queue()
        else:
            logger.info("No delta updates detected. Vector DB is up to date.")
    finally:
        pipeline.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest documents into VectorDB with delta updates."
    )
    parser.add_argument("--config", required=True, help="Path to ingestion config YAML file.")
    args = parser.parse_args()

    asyncio.run(run_pipeline(args.config))


if __name__ == "__main__":
    main()
