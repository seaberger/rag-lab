"""
PostgreSQL implementation of Fingerprint Store.

This module provides a PostgreSQL-backed fingerprint store for document
change detection with multi-tenant support.
"""

import hashlib
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.pipeline_v3.core.fingerprint import DocumentFingerprint
from src.pipeline_v3.core.postgres_base import PostgreSQLBase
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class PostgreSQLFingerprintManager:
    """PostgreSQL implementation of fingerprint store with multi-tenant support."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        tenant_id: str | None = None,
        connection_manager=None,
    ):
        """
        Initialize PostgreSQL fingerprint manager.

        Args:
            config: Pipeline configuration
            tenant_id: Tenant ID for multi-tenant isolation
            connection_manager: Optional tenant connection manager for pooling
        """
        self.config = config or PipelineConfig()

        # Get database settings
        if not hasattr(self.config, "database") or self.config.database.backend != "postgresql":
            raise ValueError("PostgreSQL backend not configured")

        self.db_settings = self.config.database
        self.pg_settings = self.db_settings.postgresql

        # Set tenant ID
        self.tenant_id = tenant_id or self.pg_settings.default_tenant_id

        # Fingerprint settings
        self.retention_days = self.config.fingerprint.retention_days
        self.include_metadata = self.config.fingerprint.include_metadata

        # Initialize PostgreSQL base with connection manager
        if connection_manager:
            # Use shared connection pool from tenant manager
            self.db = connection_manager.get_pool(
                self.tenant_id, self.pg_settings.fingerprints_schema
            )
        else:
            # Create dedicated connection pool
            self.db = PostgreSQLBase(
                self.pg_settings,
                self.pg_settings.fingerprints_schema,
                log_queries=self.db_settings.log_queries,
            )
            # Initialize connection pool
            self.db.initialize()

        # Set tenant context for RLS
        self._set_tenant_context()

        logger.info(f"PostgreSQLFingerprintManager initialized for tenant: {self.tenant_id}")

    def _set_tenant_context(self):
        """Set the tenant context for Row Level Security."""
        try:
            self.db.execute(
                "SELECT tenants.set_current_tenant(%s)",
                (self.tenant_id,),
            )
            logger.debug(f"Set tenant context to: {self.tenant_id}")
        except Exception as e:
            # Fallback if tenant functions don't exist (single-tenant mode)
            logger.warning(f"Could not set tenant context: {e}")

    @staticmethod
    def compute_fingerprint(
        source: str | Path, include_metadata: bool = True
    ) -> DocumentFingerprint:
        """Compute fingerprint for a document."""
        source_path = Path(source)

        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source}")

        # Read file content
        with open(source_path, "rb") as f:
            content = f.read()

        # Compute content hash
        content_hash = hashlib.sha256(content).hexdigest()

        # Get file stats
        stats = source_path.stat()
        size = stats.st_size
        modified_time = stats.st_mtime

        # Compute metadata hash if requested
        metadata_hash = ""
        if include_metadata:
            metadata_str = f"{source_path.name}:{size}:{modified_time}"
            metadata_hash = hashlib.md5(metadata_str.encode()).hexdigest()  # noqa: S324

        current_time = time.time()

        return DocumentFingerprint(
            source=str(source_path.resolve()),
            content_hash=content_hash,
            size=size,
            modified_time=modified_time,
            metadata_hash=metadata_hash,
            created_at=current_time,
            last_seen=current_time,
        )

    def get_fingerprint(self, source: str | Path) -> DocumentFingerprint | None:
        """Get stored fingerprint for a document."""
        source_key = str(Path(source).resolve())

        query = """
            SELECT * FROM fingerprints
            WHERE source = %s AND tenant_id = %s
        """

        row = self.db.fetch_one(query, (source_key, self.tenant_id))

        if row:
            return self._row_to_fingerprint(row)
        return None

    def _row_to_fingerprint(self, row: Dict[str, Any]) -> DocumentFingerprint:
        """Convert database row to DocumentFingerprint."""
        # Extract metadata fields from JSON (if needed in future)
        # metadata = self.db.jsonb_to_dict(row.get("metadata", {})) or {}

        return DocumentFingerprint(
            source=row["source"],
            content_hash=row["content_hash"],
            size=row["size"],
            modified_time=row["modified_time"].timestamp() if row["modified_time"] else time.time(),
            metadata_hash=row.get("metadata_hash", ""),
            created_at=row["created_at"].timestamp() if row["created_at"] else time.time(),
            last_seen=row["last_seen"].timestamp() if row.get("last_seen") else time.time(),
            doc_id=str(row["doc_id"]) if row.get("doc_id") else None,
            processing_status=row.get("processing_status", "unknown"),
        )

    def update_fingerprint(
        self,
        fingerprint: DocumentFingerprint,
        doc_id: str | None = None,
        processing_status: str = "processed",
    ) -> bool:
        """Update or create fingerprint record."""
        query = """
            INSERT INTO fingerprints (
                tenant_id, source, content_hash, size, modified_time, metadata_hash,
                doc_id, processing_status, created_at, last_seen
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW()
            )
            ON CONFLICT (tenant_id, source) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                size = EXCLUDED.size,
                modified_time = EXCLUDED.modified_time,
                metadata_hash = EXCLUDED.metadata_hash,
                doc_id = EXCLUDED.doc_id,
                processing_status = EXCLUDED.processing_status,
                last_seen = NOW()
        """

        try:
            # Build metadata dict (kept for reference)
            # metadata = {
            #     "metadata_hash": fingerprint.metadata_hash,
            #     "doc_id": doc_id,
            #     "processing_status": processing_status,
            # }

            self.db.execute(
                query,
                (
                    self.tenant_id,
                    fingerprint.source,
                    fingerprint.content_hash,
                    fingerprint.size,
                    datetime.fromtimestamp(fingerprint.modified_time),
                    fingerprint.metadata_hash,
                    uuid.UUID(doc_id) if doc_id else None,
                    processing_status,
                ),
            )

            logger.info(f"Updated fingerprint for: {Path(fingerprint.source).name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update fingerprint: {e}")
            return False

    def has_changed(self, source: str | Path) -> bool:
        """Check if document has changed since last fingerprint."""
        source_path = Path(source)

        if not source_path.exists():
            return True  # Non-existent file is considered changed

        # Get stored fingerprint
        stored = self.get_fingerprint(source)
        if not stored:
            return True  # No fingerprint means new document

        # Compute current fingerprint
        current = self.compute_fingerprint(source, self.include_metadata)

        # Compare fingerprints
        content_changed = stored.content_hash != current.content_hash

        if self.include_metadata:
            metadata_changed = (
                stored.size != current.size
                or abs(stored.modified_time - current.modified_time) > 1.0  # 1 second tolerance
            )
            return content_changed or metadata_changed

        return content_changed

    def get_processing_status(self, source: str | Path) -> str:
        """Get processing status for a document."""
        fingerprint = self.get_fingerprint(source)
        return fingerprint.processing_status if fingerprint else "unknown"

    def mark_processing_status(
        self, source: str | Path, status: str, doc_id: str | None = None
    ) -> bool:
        """Mark processing status for a document."""
        source_key = str(Path(source).resolve())

        query = """
            UPDATE fingerprints
            SET processing_status = %s,
                doc_id = COALESCE(%s, doc_id),
                last_seen = NOW()
            WHERE source = %s AND tenant_id = %s
        """

        result = self.db.execute(
            query,
            (status, uuid.UUID(doc_id) if doc_id else None, source_key, self.tenant_id),
        )

        return result > 0

    def get_document_history(self, source: str | Path) -> list[dict[str, Any]]:
        """Get processing history for a document (current version only in this implementation)."""
        fingerprint = self.get_fingerprint(source)

        if not fingerprint:
            return []

        # In this implementation, we only track current version
        # Full history would require a separate history table
        return [
            {
                "source": fingerprint.source,
                "content_hash": fingerprint.content_hash,
                "size": fingerprint.size,
                "modified_time": fingerprint.modified_time,
                "created_at": fingerprint.created_at,
                "last_seen": fingerprint.last_seen,
                "processing_status": fingerprint.processing_status,
                "doc_id": fingerprint.doc_id,
            }
        ]

    def list_documents(
        self,
        status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[DocumentFingerprint]:
        """List tracked documents with optional filtering."""
        conditions = ["tenant_id = %s"]
        params = [self.tenant_id]

        if status:
            conditions.append("processing_status = %s")
            params.append(status)

        query = f"""
            SELECT * FROM fingerprints
            WHERE {" AND ".join(conditions)}
            ORDER BY last_seen DESC
            LIMIT %s OFFSET %s
        """

        params.extend([limit or 100, offset])

        rows = self.db.fetch_all(query, tuple(params))

        return [self._row_to_fingerprint(row) for row in rows]

    def cleanup_old_fingerprints(self, older_than_days: int | None = None) -> int:
        """Remove fingerprints older than retention period."""
        days = older_than_days or self.retention_days

        query = """
            DELETE FROM fingerprints
            WHERE tenant_id = %s
            AND last_seen < NOW() - INTERVAL '%s days'
        """

        result = self.db.execute(query, (self.tenant_id, days))

        if result > 0:
            logger.info(f"Cleaned up {result} old fingerprints")

        return result

    def get_stats(self) -> dict[str, Any]:
        """Get fingerprint store statistics."""
        stats_query = """
            SELECT
                COUNT(*) as total_documents,
                COUNT(CASE WHEN processing_status = 'processed' THEN 1 END) as processed,
                COUNT(CASE WHEN processing_status = 'failed' THEN 1 END) as failed,
                COUNT(CASE WHEN processing_status = 'unknown' THEN 1 END) as unknown,
                COUNT(DISTINCT content_hash) as unique_content,
                MAX(last_seen) as most_recent_update,
                MIN(created_at) as oldest_document
            FROM fingerprints
            WHERE tenant_id = %s
        """

        stats = self.db.fetch_one(stats_query, (self.tenant_id,))

        # Size statistics
        size_query = """
            SELECT
                SUM(size) as total_size,
                AVG(size) as avg_size,
                MAX(size) as max_size,
                MIN(size) as min_size
            FROM fingerprints
            WHERE tenant_id = %s
        """

        size_stats = self.db.fetch_one(size_query, (self.tenant_id,))

        return {
            "total_documents": stats["total_documents"] or 0,
            "status_breakdown": {
                "processed": stats["processed"] or 0,
                "failed": stats["failed"] or 0,
                "unknown": stats["unknown"] or 0,
            },
            "unique_content_hashes": stats["unique_content"] or 0,
            "size_stats": {
                "total_bytes": size_stats["total_size"] or 0,
                "average_bytes": int(size_stats["avg_size"] or 0),
                "max_bytes": size_stats["max_size"] or 0,
                "min_bytes": size_stats["min_size"] or 0,
            },
            "most_recent_update": stats["most_recent_update"].isoformat()
            if stats["most_recent_update"]
            else None,
            "oldest_document": stats["oldest_document"].isoformat()
            if stats["oldest_document"]
            else None,
            "tenant_id": self.tenant_id,
        }

    def find_duplicates(self) -> dict[str, list[str]]:
        """Find documents with identical content."""
        query = """
            SELECT content_hash, array_agg(source) as sources
            FROM fingerprints
            WHERE tenant_id = %s
            GROUP BY content_hash
            HAVING COUNT(*) > 1
        """

        rows = self.db.fetch_all(query, (self.tenant_id,))

        duplicates = {}
        for row in rows:
            duplicates[row["content_hash"]] = row["sources"]

        return duplicates

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
