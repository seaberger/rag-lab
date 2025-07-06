"""
SQLite to PostgreSQL migration tool for Pipeline v3.

This module provides tools to migrate data from SQLite databases to PostgreSQL,
supporting all four database types: registry, keyword index, jobs, and fingerprints.
"""

import asyncio
import contextlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from core.postgres_base import PostgreSQLBase
from tqdm import tqdm

from utils.common_utils import logger
from utils.config import PostgreSQLSettings


@dataclass
class MigrationStats:
    """Track migration statistics."""

    documents_migrated: int = 0
    index_entries_migrated: int = 0
    jobs_migrated: int = 0
    fingerprints_migrated: int = 0
    errors: List[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []

    def add_error(self, error: str):
        """Add an error to the stats."""
        self.errors.append(f"{datetime.now().isoformat()}: {error}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary."""
        return {
            "documents_migrated": self.documents_migrated,
            "index_entries_migrated": self.index_entries_migrated,
            "jobs_migrated": self.jobs_migrated,
            "fingerprints_migrated": self.fingerprints_migrated,
            "error_count": len(self.errors),
            "errors": self.errors[-10:],  # Last 10 errors
        }


class SQLiteToPostgresMigrator:
    """Migrate data from SQLite to PostgreSQL."""

    def __init__(
        self,
        sqlite_paths: Dict[str, Path],
        pg_settings: PostgreSQLSettings,
        tenant_id: str | None = None,
    ):
        """
        Initialize migrator.

        Args:
            sqlite_paths: Dictionary mapping database types to SQLite file paths
            pg_settings: PostgreSQL connection settings
            tenant_id: Target tenant ID for migration
        """
        self.sqlite_paths = sqlite_paths
        self.pg_settings = pg_settings
        self.tenant_id = tenant_id or pg_settings.default_tenant_id
        self.stats = MigrationStats()

        # Initialize PostgreSQL connections for each schema
        self.pg_registry = PostgreSQLBase(pg_settings, pg_settings.registry_schema)
        self.pg_search = PostgreSQLBase(pg_settings, pg_settings.search_schema)
        self.pg_jobs = PostgreSQLBase(pg_settings, pg_settings.jobs_schema)
        self.pg_fingerprints = PostgreSQLBase(pg_settings, pg_settings.fingerprints_schema)

    async def initialize(self):
        """Initialize PostgreSQL connections."""
        await self.pg_registry.initialize_async()
        await self.pg_search.initialize_async()
        await self.pg_jobs.initialize_async()
        await self.pg_fingerprints.initialize_async()

    async def close(self):
        """Close all connections."""
        await self.pg_registry.close_async()
        await self.pg_search.close_async()
        await self.pg_jobs.close_async()
        await self.pg_fingerprints.close_async()

    async def migrate_all(self, batch_size: int = 1000, skip_existing: bool = True):
        """
        Migrate all databases.

        Args:
            batch_size: Number of records to process in each batch
            skip_existing: Skip records that already exist in PostgreSQL
        """
        logger.info(f"Starting migration to PostgreSQL for tenant: {self.tenant_id}")

        try:
            await self.initialize()

            # Migrate each database type
            if "registry" in self.sqlite_paths:
                await self.migrate_registry(batch_size, skip_existing)

            if "keyword" in self.sqlite_paths:
                await self.migrate_keyword_index(batch_size, skip_existing)

            if "jobs" in self.sqlite_paths:
                await self.migrate_jobs(batch_size, skip_existing)

            if "fingerprints" in self.sqlite_paths:
                await self.migrate_fingerprints(batch_size, skip_existing)

            logger.info("Migration completed successfully")
            logger.info(f"Stats: {self.stats.to_dict()}")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            self.stats.add_error(f"Migration failed: {e!s}")
            raise
        finally:
            await self.close()

    async def migrate_registry(self, batch_size: int, skip_existing: bool):
        """Migrate document registry data."""
        logger.info("Migrating document registry...")

        sqlite_path = self.sqlite_paths["registry"]
        if not sqlite_path.exists():
            logger.warning(f"Registry database not found: {sqlite_path}")
            return

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get total count
            total = cursor.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            logger.info(f"Found {total} documents to migrate")

            # Migrate documents in batches
            offset = 0
            with tqdm(total=total, desc="Documents") as pbar:
                while offset < total:
                    rows = cursor.execute(
                        """
                        SELECT * FROM documents
                        ORDER BY created_at
                        LIMIT ? OFFSET ?
                        """,
                        (batch_size, offset),
                    ).fetchall()

                    if not rows:
                        break

                    await self._migrate_document_batch(rows, skip_existing)
                    pbar.update(len(rows))
                    offset += batch_size

            # Migrate index entries
            total = cursor.execute("SELECT COUNT(*) FROM index_entries").fetchone()[0]
            logger.info(f"Found {total} index entries to migrate")

            offset = 0
            with tqdm(total=total, desc="Index entries") as pbar:
                while offset < total:
                    rows = cursor.execute(
                        """
                        SELECT * FROM index_entries
                        ORDER BY created_at
                        LIMIT ? OFFSET ?
                        """,
                        (batch_size, offset),
                    ).fetchall()

                    if not rows:
                        break

                    await self._migrate_index_entry_batch(rows, skip_existing)
                    pbar.update(len(rows))
                    offset += batch_size

        finally:
            conn.close()

    async def _migrate_document_batch(self, rows: List[sqlite3.Row], skip_existing: bool):
        """Migrate a batch of documents."""
        values = []
        for row in rows:
            # Check if document already exists
            if skip_existing:
                exists = await self.pg_registry.fetch_one_async(
                    "SELECT 1 FROM documents WHERE doc_id = $1 AND tenant_id = $2",
                    uuid.UUID(row["doc_id"]),
                    uuid.UUID(self.tenant_id),
                )
                if exists:
                    continue

            values.append(
                (
                    uuid.UUID(row["doc_id"]),
                    uuid.UUID(self.tenant_id),
                    row["source"],
                    row["content_hash"],
                    row["size"],
                    datetime.fromisoformat(row["modified_time"]),
                    datetime.fromisoformat(row["created_at"]),
                    datetime.fromisoformat(row["updated_at"]),
                    row["state"],
                    bool(row["vector_indexed"]),
                    bool(row["keyword_indexed"]),
                    row["chunk_count"],
                    row["error_count"],
                    row["last_error"],
                    row["metadata"],
                )
            )

        if values:
            try:
                await self.pg_registry.execute_many_async(
                    """
                    INSERT INTO documents (
                        doc_id, tenant_id, source, content_hash, size,
                        modified_time, created_at, updated_at, state,
                        vector_indexed, keyword_indexed, chunk_count,
                        error_count, last_error, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (tenant_id, doc_id) DO NOTHING
                    """,
                    values,
                )
                self.stats.documents_migrated += len(values)
            except Exception as e:
                self.stats.add_error(f"Document batch error: {e!s}")
                logger.error(f"Failed to migrate document batch: {e}")

    async def _migrate_index_entry_batch(self, rows: List[sqlite3.Row], skip_existing: bool):
        """Migrate a batch of index entries."""
        values = []
        for row in rows:
            values.append(
                (
                    uuid.UUID(row["doc_id"]),
                    uuid.UUID(self.tenant_id),
                    row["index_type"],
                    row["node_id"],
                    row["chunk_index"],
                    row["content_hash"],
                    datetime.fromisoformat(row["created_at"]),
                    datetime.fromisoformat(row["updated_at"]),
                    row["metadata"],
                )
            )

        if values:
            try:
                await self.pg_registry.execute_many_async(
                    """
                    INSERT INTO index_entries (
                        doc_id, tenant_id, index_type, node_id,
                        chunk_index, content_hash, created_at,
                        updated_at, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (tenant_id, doc_id, index_type, chunk_index) DO NOTHING
                    """,
                    values,
                )
                self.stats.index_entries_migrated += len(values)
            except Exception as e:
                self.stats.add_error(f"Index entry batch error: {e!s}")
                logger.error(f"Failed to migrate index entry batch: {e}")

    async def migrate_keyword_index(self, batch_size: int, skip_existing: bool):
        """Migrate keyword search index data."""
        logger.info("Migrating keyword search index...")

        sqlite_path = self.sqlite_paths["keyword"]
        if not sqlite_path.exists():
            logger.warning(f"Keyword index database not found: {sqlite_path}")
            return

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get total count
            total = cursor.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
            logger.info(f"Found {total} search documents to migrate")

            # Migrate in batches
            offset = 0
            with tqdm(total=total, desc="Search documents") as pbar:
                while offset < total:
                    rows = cursor.execute(
                        """
                        SELECT * FROM search_documents
                        ORDER BY doc_id, chunk_id
                        LIMIT ? OFFSET ?
                        """,
                        (batch_size, offset),
                    ).fetchall()

                    if not rows:
                        break

                    await self._migrate_search_batch(rows, skip_existing)
                    pbar.update(len(rows))
                    offset += batch_size

        finally:
            conn.close()

    async def _migrate_search_batch(self, rows: List[sqlite3.Row], skip_existing: bool):
        """Migrate a batch of search documents."""
        values = []
        for row in rows:
            # Parse metadata
            metadata = {}
            if row["metadata"]:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    metadata = json.loads(row["metadata"])

            # Parse keywords array
            keywords = []
            if row["keywords"]:
                try:
                    keywords = json.loads(row["keywords"])
                except (json.JSONDecodeError, TypeError):
                    keywords = row["keywords"].split(",") if row["keywords"] else []

            values.append(
                (
                    uuid.UUID(row["doc_id"]),
                    uuid.UUID(self.tenant_id),
                    row["chunk_id"],
                    row["text"],
                    keywords,
                    self.pg_search.json_to_jsonb(metadata),
                    datetime.fromisoformat(row["created_at"]),
                )
            )

        if values:
            try:
                await self.pg_search.execute_many_async(
                    """
                    INSERT INTO documents (
                        doc_id, tenant_id, chunk_id, text,
                        keywords, metadata, created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (tenant_id, doc_id, chunk_id) DO NOTHING
                    """,
                    values,
                )
                self.stats.index_entries_migrated += len(values)
            except Exception as e:
                self.stats.add_error(f"Search batch error: {e!s}")
                logger.error(f"Failed to migrate search batch: {e}")

    async def migrate_jobs(self, batch_size: int, skip_existing: bool):
        """Migrate job queue data."""
        logger.info("Migrating job queue...")

        sqlite_path = self.sqlite_paths["jobs"]
        if not sqlite_path.exists():
            logger.warning(f"Jobs database not found: {sqlite_path}")
            return

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get total count
            total = cursor.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
            logger.info(f"Found {total} jobs to migrate")

            # Migrate in batches
            offset = 0
            with tqdm(total=total, desc="Jobs") as pbar:
                while offset < total:
                    rows = cursor.execute(
                        """
                        SELECT * FROM jobs
                        ORDER BY created_at
                        LIMIT ? OFFSET ?
                        """,
                        (batch_size, offset),
                    ).fetchall()

                    if not rows:
                        break

                    await self._migrate_job_batch(rows, skip_existing)
                    pbar.update(len(rows))
                    offset += batch_size

        finally:
            conn.close()

    async def _migrate_job_batch(self, rows: List[sqlite3.Row], skip_existing: bool):
        """Migrate a batch of jobs."""
        values = []
        for row in rows:
            # Parse payload
            payload = {}
            if row["payload"]:
                with contextlib.suppress(json.JSONDecodeError, TypeError):
                    payload = json.loads(row["payload"])

            # Parse result
            result = None
            if row["result"]:
                try:
                    result = json.loads(row["result"])
                except (json.JSONDecodeError, TypeError):
                    result = {"data": row["result"]}

            values.append(
                (
                    uuid.UUID(row["job_id"]),
                    uuid.UUID(self.tenant_id),
                    row["job_type"],
                    row["status"],
                    row["priority"],
                    self.pg_jobs.json_to_jsonb(payload),
                    self.pg_jobs.json_to_jsonb(result),
                    row["error_message"],
                    row["retry_count"],
                    row["max_retries"],
                    row["worker_id"],
                    datetime.fromisoformat(row["created_at"]),
                    datetime.fromisoformat(row["updated_at"]) if row["updated_at"] else None,
                    datetime.fromisoformat(row["started_at"]) if row["started_at"] else None,
                    datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
                )
            )

        if values:
            try:
                await self.pg_jobs.execute_many_async(
                    """
                    INSERT INTO queue (
                        job_id, tenant_id, job_type, status, priority,
                        payload, result, error_message, retry_count,
                        max_retries, worker_id, created_at, updated_at,
                        started_at, completed_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
                    ON CONFLICT (job_id) DO NOTHING
                    """,
                    values,
                )
                self.stats.jobs_migrated += len(values)
            except Exception as e:
                self.stats.add_error(f"Job batch error: {e!s}")
                logger.error(f"Failed to migrate job batch: {e}")

    async def migrate_fingerprints(self, batch_size: int, skip_existing: bool):
        """Migrate fingerprint data."""
        logger.info("Migrating fingerprints...")

        sqlite_path = self.sqlite_paths["fingerprints"]
        if not sqlite_path.exists():
            logger.warning(f"Fingerprints database not found: {sqlite_path}")
            return

        conn = sqlite3.connect(sqlite_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        try:
            # Get total count
            total = cursor.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
            logger.info(f"Found {total} fingerprints to migrate")

            # Migrate in batches
            offset = 0
            with tqdm(total=total, desc="Fingerprints") as pbar:
                while offset < total:
                    rows = cursor.execute(
                        """
                        SELECT * FROM fingerprints
                        ORDER BY created_at
                        LIMIT ? OFFSET ?
                        """,
                        (batch_size, offset),
                    ).fetchall()

                    if not rows:
                        break

                    await self._migrate_fingerprint_batch(rows, skip_existing)
                    pbar.update(len(rows))
                    offset += batch_size

        finally:
            conn.close()

    async def _migrate_fingerprint_batch(self, rows: List[sqlite3.Row], skip_existing: bool):
        """Migrate a batch of fingerprints."""
        values = []
        for row in rows:
            values.append(
                (
                    row["source"],
                    uuid.UUID(self.tenant_id),
                    row["content_hash"],
                    row["size"],
                    datetime.fromtimestamp(row["modified_time"]),
                    row["metadata_hash"],
                    uuid.UUID(row["doc_id"]) if row["doc_id"] else None,
                    row["processing_status"],
                    datetime.fromtimestamp(row["created_at"]),
                    datetime.fromtimestamp(row["last_seen"]),
                )
            )

        if values:
            try:
                await self.pg_fingerprints.execute_many_async(
                    """
                    INSERT INTO fingerprints (
                        source, tenant_id, content_hash, size,
                        modified_time, metadata_hash, doc_id,
                        processing_status, created_at, last_seen
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT (tenant_id, source) DO NOTHING
                    """,
                    values,
                )
                self.stats.fingerprints_migrated += len(values)
            except Exception as e:
                self.stats.add_error(f"Fingerprint batch error: {e!s}")
                logger.error(f"Failed to migrate fingerprint batch: {e}")

    async def verify_migration(self) -> Dict[str, Any]:
        """Verify migration by comparing counts."""
        verification = {
            "sqlite_counts": {},
            "postgres_counts": {},
            "matches": {},
        }

        # Get SQLite counts
        for db_type, path in self.sqlite_paths.items():
            if path.exists():
                conn = sqlite3.connect(path)
                cursor = conn.cursor()

                if db_type == "registry":
                    doc_count = cursor.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
                    index_count = cursor.execute("SELECT COUNT(*) FROM index_entries").fetchone()[0]
                    verification["sqlite_counts"]["documents"] = doc_count
                    verification["sqlite_counts"]["index_entries"] = index_count
                elif db_type == "keyword":
                    count = cursor.execute("SELECT COUNT(*) FROM search_documents").fetchone()[0]
                    verification["sqlite_counts"]["search_documents"] = count
                elif db_type == "jobs":
                    count = cursor.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
                    verification["sqlite_counts"]["jobs"] = count
                elif db_type == "fingerprints":
                    count = cursor.execute("SELECT COUNT(*) FROM fingerprints").fetchone()[0]
                    verification["sqlite_counts"]["fingerprints"] = count

                conn.close()

        # Get PostgreSQL counts
        await self.initialize()

        doc_count = await self.pg_registry.fetch_one_async(
            "SELECT COUNT(*) as count FROM documents WHERE tenant_id = $1",
            uuid.UUID(self.tenant_id),
        )
        verification["postgres_counts"]["documents"] = doc_count["count"]

        index_count = await self.pg_registry.fetch_one_async(
            "SELECT COUNT(*) as count FROM index_entries WHERE tenant_id = $1",
            uuid.UUID(self.tenant_id),
        )
        verification["postgres_counts"]["index_entries"] = index_count["count"]

        search_count = await self.pg_search.fetch_one_async(
            "SELECT COUNT(*) as count FROM documents WHERE tenant_id = $1",
            uuid.UUID(self.tenant_id),
        )
        verification["postgres_counts"]["search_documents"] = search_count["count"]

        job_count = await self.pg_jobs.fetch_one_async(
            "SELECT COUNT(*) as count FROM queue WHERE tenant_id = $1",
            uuid.UUID(self.tenant_id),
        )
        verification["postgres_counts"]["jobs"] = job_count["count"]

        fp_count = await self.pg_fingerprints.fetch_one_async(
            "SELECT COUNT(*) as count FROM fingerprints WHERE tenant_id = $1",
            uuid.UUID(self.tenant_id),
        )
        verification["postgres_counts"]["fingerprints"] = fp_count["count"]

        await self.close()

        # Check matches
        for key in verification["sqlite_counts"]:
            sqlite_val = verification["sqlite_counts"].get(key, 0)
            pg_val = verification["postgres_counts"].get(key, 0)
            verification["matches"][key] = sqlite_val == pg_val

        return verification


async def main():
    """Example migration script."""
    from utils.config import PipelineConfig

    # Load configuration
    config = PipelineConfig()

    # Define SQLite database paths
    sqlite_paths = {
        "registry": Path("./document_registry_v3.db"),
        "keyword": Path("./keyword_index_v3.db"),
        "jobs": Path("./jobs_v3.db"),
        "fingerprints": Path("./fingerprints_v3.db"),
    }

    # Create migrator
    migrator = SQLiteToPostgresMigrator(
        sqlite_paths,
        config.database.postgresql,
        tenant_id=config.database.postgresql.default_tenant_id,
    )

    # Run migration
    await migrator.migrate_all(batch_size=1000)

    # Verify migration
    verification = await migrator.verify_migration()
    print(f"Verification results: {json.dumps(verification, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
