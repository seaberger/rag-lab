"""
PostgreSQL implementation of Document Registry.

This module provides a PostgreSQL-backed document registry that maintains
compatibility with the SQLite interface while adding multi-tenant support.
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from ..utils.common_utils import logger
from ..utils.config import PipelineConfig
from .postgres_base import PostgreSQLBase
from .registry import DocumentRecord, DocumentState, IndexRecord, IndexType


class PostgreSQLDocumentRegistry:
    """PostgreSQL implementation of document registry with multi-tenant support."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        tenant_id: str | None = None,
        connection_manager=None,
    ):
        """
        Initialize PostgreSQL document registry.

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

        # Initialize PostgreSQL base with connection manager
        if connection_manager:
            # Use shared connection pool from tenant manager
            self.db = connection_manager.get_pool(self.tenant_id, self.pg_settings.registry_schema)
        else:
            # Create dedicated connection pool
            self.db = PostgreSQLBase(
                self.pg_settings,
                self.pg_settings.registry_schema,
                log_queries=self.db_settings.log_queries,
            )
            # Initialize connection pool
            self.db.initialize()

        # Set tenant context for RLS
        self._set_tenant_context()

        # Ensure schema exists
        self._ensure_schema()

        logger.info(f"PostgreSQLDocumentRegistry initialized for tenant: {self.tenant_id}")

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

    def _ensure_schema(self):
        """Ensure the registry schema and tables exist."""
        # This would normally be handled by migrations, but we'll check
        if not self.db.table_exists("documents"):
            logger.warning("Registry tables not found. Run migrations first.")

    def register_document(
        self,
        source: str | Path,
        content_hash: str,
        size: int,
        modified_time: float,
        doc_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register a new document or update existing one."""
        if doc_id is None:
            doc_id = str(uuid.uuid4())

        source_key = str(Path(source).resolve())

        # Check if document already exists
        existing = self.get_document_by_source(source)

        if existing:
            # Update existing document
            if existing.content_hash != content_hash:
                # Content changed, mark as stale
                state = DocumentState.STALE.value
                vector_indexed = False
                keyword_indexed = False
                chunk_count = 0
                logger.info(f"Document content changed, marking as stale: {source}")
            else:
                # Keep existing state
                state = existing.state
                vector_indexed = existing.vector_indexed
                keyword_indexed = existing.keyword_indexed
                chunk_count = existing.chunk_count

            # Update document
            query = """
                UPDATE documents
                SET content_hash = %s,
                    size = %s,
                    modified_time = %s,
                    state = %s,
                    vector_indexed = %s,
                    keyword_indexed = %s,
                    chunk_count = %s,
                    metadata = %s,
                    updated_at = NOW()
                WHERE doc_id = %s AND tenant_id = %s
            """

            self.db.execute(
                query,
                (
                    content_hash,
                    size,
                    datetime.fromtimestamp(modified_time),
                    state,
                    vector_indexed,
                    keyword_indexed,
                    chunk_count,
                    self.db.json_to_jsonb(metadata) if metadata else None,
                    existing.doc_id,
                    self.tenant_id,
                ),
            )

            return existing.doc_id

        # Create new document
        query = """
            INSERT INTO documents (
                doc_id, tenant_id, source, content_hash, size,
                modified_time, state, metadata,
                vector_indexed, keyword_indexed, chunk_count
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        self.db.execute(
            query,
            (
                doc_id,  # Already a string, no need to convert to UUID
                self.tenant_id,
                source_key,
                content_hash,
                size,
                datetime.fromtimestamp(modified_time),
                DocumentState.NEW.value,
                self.db.json_to_jsonb(metadata) if metadata else None,
                False,  # vector_indexed
                False,  # keyword_indexed
                0,  # chunk_count
            ),
        )

        logger.info(f"Registered new document: {doc_id[:8]} - {source}")
        return doc_id

    def get_document(self, doc_id: str) -> DocumentRecord | None:
        """Get document by ID."""
        query = """
            SELECT * FROM documents
            WHERE doc_id = %s AND tenant_id = %s
        """

        row = self.db.fetch_one(query, (doc_id, self.tenant_id))

        if row:
            return self._row_to_document(row)
        return None

    def get_document_by_source(self, source: str | Path) -> DocumentRecord | None:
        """Get document by source path."""
        source_key = str(Path(source).resolve())

        query = """
            SELECT * FROM documents
            WHERE source = %s AND tenant_id = %s
        """

        row = self.db.fetch_one(query, (source_key, self.tenant_id))

        if row:
            return self._row_to_document(row)
        return None

    def _row_to_document(self, row: Dict[str, Any]) -> DocumentRecord:
        """Convert database row to DocumentRecord."""
        # Handle schema differences between SQLite and PostgreSQL
        # PostgreSQL has 'error_message' instead of 'error_count' and 'last_error'
        error_count = 0
        if row.get("error_message"):
            # If there's an error message, assume at least one error
            error_count = 1

        return DocumentRecord(
            doc_id=str(row["doc_id"]),
            source=row["source"],
            content_hash=row["content_hash"],
            size=row["size"] or 0,
            modified_time=row["modified_time"].timestamp() if row.get("modified_time") else 0,
            created_at=row["created_at"].timestamp() if row.get("created_at") else 0,
            updated_at=row["updated_at"].timestamp() if row.get("updated_at") else 0,
            state=row["state"],
            vector_indexed=row.get("vector_indexed", False),
            keyword_indexed=row.get("keyword_indexed", False),
            chunk_count=row.get("chunk_count", 0),
            error_count=error_count,
            last_error=row.get("error_message"),
            metadata=self.db.jsonb_to_dict(row.get("metadata")) or {},
        )

    def update_document_state(
        self, doc_id: str, state: DocumentState, error_msg: str | None = None
    ) -> bool:
        """Update document state and optionally record error."""
        query = """
            UPDATE documents
            SET state = %s,
                error_message = %s,
                updated_at = NOW()
            WHERE doc_id = %s AND tenant_id = %s
        """

        result = self.db.execute(query, (state.value, error_msg, doc_id, self.tenant_id))

        success = result > 0
        if success:
            logger.info(f"Updated document state: {doc_id[:8]} -> {state.value}")
        else:
            logger.warning(f"Failed to update document state: {doc_id[:8]}")

        return success

    def mark_indexed(self, doc_id: str, index_type: IndexType, chunk_count: int = 0) -> bool:
        """Mark document as indexed in specified index."""
        if index_type == IndexType.VECTOR:
            query = """
                UPDATE documents
                SET vector_indexed = TRUE,
                    state = %s,
                    chunk_count = %s,
                    updated_at = NOW()
                WHERE doc_id = %s AND tenant_id = %s
            """
        elif index_type == IndexType.KEYWORD:
            query = """
                UPDATE documents
                SET keyword_indexed = TRUE,
                    state = %s,
                    chunk_count = GREATEST(chunk_count, %s),
                    updated_at = NOW()
                WHERE doc_id = %s AND tenant_id = %s
            """
        else:  # BOTH
            query = """
                UPDATE documents
                SET vector_indexed = TRUE,
                    keyword_indexed = TRUE,
                    state = %s,
                    chunk_count = %s,
                    updated_at = NOW()
                WHERE doc_id = %s AND tenant_id = %s
            """

        result = self.db.execute(
            query,
            (
                DocumentState.INDEXED.value,
                chunk_count,
                doc_id,
                self.tenant_id,
            ),
        )

        success = result > 0
        if success:
            logger.info(f"Marked document as indexed: {doc_id[:8]} in {index_type.value}")

        return success

    def register_index_entry(
        self,
        doc_id: str,
        index_type: IndexType,
        node_id: str,
        chunk_index: int,
        content_hash: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Register an index entry for a document chunk.

        In the PostgreSQL implementation, individual chunk tracking is handled
        by the specialized keyword/vector index adapters. This method is kept
        for compatibility but doesn't perform any actual storage operations.
        """
        # In PostgreSQL architecture, chunk-level tracking is handled by:
        # - keyword_search table (for keyword index chunks)
        # - Qdrant vector database (for vector index chunks)
        # The registry only tracks document-level state, not individual chunks
        logger.debug(f"Index entry registration handled by specialized adapters: {doc_id[:8]}")
        return True

    def get_index_entries(
        self, doc_id: str, index_type: IndexType | None = None
    ) -> list[IndexRecord]:
        """Get index entries for a document.

        In the PostgreSQL implementation, individual chunk tracking is handled
        by the specialized keyword/vector index adapters. This method returns
        an empty list for compatibility.
        """
        # In PostgreSQL architecture, chunk-level information should be queried from:
        # - keyword_search table (for keyword index chunks)
        # - Qdrant vector database (for vector index chunks)
        # The registry only tracks document-level state, not individual chunks
        logger.debug(f"Index entries tracked by specialized adapters for: {doc_id[:8]}")
        return []

    def remove_document(self, doc_id: str) -> bool:
        """Remove document from registry.

        Note: In the PostgreSQL implementation, individual chunk cleanup is handled
        by the specialized keyword/vector index adapters via IndexManager.
        """
        query = """
            DELETE FROM documents
            WHERE doc_id = %s AND tenant_id = %s
        """

        try:
            result = self.db.execute(query, (doc_id, self.tenant_id))
            deleted = result > 0

            if deleted:
                logger.info(f"Removed document from registry: {doc_id[:8]}")
            else:
                logger.warning(f"Document not found in registry: {doc_id[:8]}")

            return deleted
        except Exception as e:
            logger.error(f"Failed to remove document {doc_id[:8]}: {e}")
            return False

    def remove_index_entries(self, doc_id: str, index_type: IndexType) -> bool:
        """Remove index entries for a specific index type.

        In the PostgreSQL implementation, individual chunk cleanup is handled
        by the specialized keyword/vector index adapters. This method only
        updates the document-level indexing flags.
        """
        try:
            # Update document index flags (the actual chunk removal is handled by adapters)
            if index_type == IndexType.VECTOR:
                flag_query = "UPDATE documents SET vector_indexed = FALSE WHERE doc_id = %s AND tenant_id = %s"
            elif index_type == IndexType.KEYWORD:
                flag_query = "UPDATE documents SET keyword_indexed = FALSE WHERE doc_id = %s AND tenant_id = %s"
            else:  # BOTH
                flag_query = "UPDATE documents SET vector_indexed = FALSE, keyword_indexed = FALSE WHERE doc_id = %s AND tenant_id = %s"

            result = self.db.execute(flag_query, (doc_id, self.tenant_id))

            if result > 0:
                logger.info(f"Updated index flags for document: {doc_id[:8]} ({index_type.value})")

            return result > 0
        except Exception as e:
            logger.error(f"Failed to remove index entries for {doc_id[:8]}: {e}")
            return False

    def list_documents(
        self,
        state: DocumentState | None = None,
        indexed: bool | None = None,
        limit: int | None = None,
    ) -> list[DocumentRecord]:
        """List documents with optional filtering."""
        conditions = ["tenant_id = %s"]
        params = [self.tenant_id]

        if state:
            conditions.append("state = %s")
            params.append(state.value)

        if indexed is not None:
            if indexed:
                conditions.append("(vector_indexed = TRUE OR keyword_indexed = TRUE)")
            else:
                conditions.append("(vector_indexed = FALSE AND keyword_indexed = FALSE)")

        query = f"""
            SELECT * FROM documents
            WHERE {" AND ".join(conditions)}
            ORDER BY updated_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        rows = self.db.fetch_all(query, tuple(params))

        return [self._row_to_document(row) for row in rows]

    def get_inconsistent_documents(self) -> list[DocumentRecord]:
        """Get documents with inconsistent state."""
        query = """
            SELECT d.* FROM documents d
            WHERE d.tenant_id = %s AND (
                -- Marked as indexed but no index entries
                (d.vector_indexed = TRUE AND NOT EXISTS (
                    SELECT 1 FROM registry.index_entries ie
                    WHERE ie.doc_id = d.doc_id
                    AND ie.tenant_id = d.tenant_id
                    AND ie.index_type = 'vector'
                )) OR
                -- Has index entries but not marked as indexed
                (d.vector_indexed = FALSE AND EXISTS (
                    SELECT 1 FROM registry.index_entries ie
                    WHERE ie.doc_id = d.doc_id
                    AND ie.tenant_id = d.tenant_id
                    AND ie.index_type = 'vector'
                ))
            )
        """

        rows = self.db.fetch_all(query, (self.tenant_id,))
        return [self._row_to_document(row) for row in rows]

    def get_orphaned_index_entries(self) -> list[IndexRecord]:
        """Get index entries without corresponding documents."""
        query = """
            SELECT ie.* FROM registry.index_entries ie
            LEFT JOIN documents d ON ie.doc_id = d.doc_id AND ie.tenant_id = d.tenant_id
            WHERE ie.tenant_id = %s AND d.doc_id IS NULL
        """

        rows = self.db.fetch_all(query, (self.tenant_id,))

        return [
            IndexRecord(
                doc_id=str(row["doc_id"]),
                index_type=row["index_type"],
                node_id=row["node_id"],
                chunk_index=row["chunk_index"],
                content_hash=row["content_hash"],
                created_at=row["created_at"].timestamp(),
                updated_at=row["updated_at"].timestamp(),
                metadata=self.db.jsonb_to_dict(row["metadata"]) or {},
            )
            for row in rows
        ]

    def get_statistics(self) -> dict[str, Any]:
        """Get registry statistics."""
        stats_query = """
            SELECT
                COUNT(*) as total_documents,
                COUNT(CASE WHEN state = %s THEN 1 END) as new_documents,
                COUNT(CASE WHEN state = %s THEN 1 END) as indexed_documents,
                COUNT(CASE WHEN state = %s THEN 1 END) as stale_documents,
                COUNT(CASE WHEN state = %s THEN 1 END) as corrupted_documents,
                COUNT(CASE WHEN vector_indexed = TRUE THEN 1 END) as vector_indexed,
                COUNT(CASE WHEN keyword_indexed = TRUE THEN 1 END) as keyword_indexed,
                SUM(chunk_count) as total_chunks,
                SUM(size) as total_size
            FROM documents
            WHERE tenant_id = %s
        """

        stats = self.db.fetch_one(
            stats_query,
            (
                DocumentState.NEW.value,
                DocumentState.INDEXED.value,
                DocumentState.STALE.value,
                DocumentState.CORRUPTED.value,
                self.tenant_id,
            ),
        )

        # Get index entries count
        index_query = """
            SELECT
                index_type,
                COUNT(*) as count
            FROM registry.index_entries
            WHERE tenant_id = %s
            GROUP BY index_type
        """

        index_rows = self.db.fetch_all(index_query, (self.tenant_id,))
        index_stats = {row["index_type"]: row["count"] for row in index_rows}

        return {
            "total_documents": stats["total_documents"] or 0,
            "documents_by_state": {
                "new": stats["new_documents"] or 0,
                "indexed": stats["indexed_documents"] or 0,
                "stale": stats["stale_documents"] or 0,
                "corrupted": stats["corrupted_documents"] or 0,
            },
            "indexed_documents": {
                "vector": stats["vector_indexed"] or 0,
                "keyword": stats["keyword_indexed"] or 0,
            },
            "total_chunks": stats["total_chunks"] or 0,
            "total_size": stats["total_size"] or 0,
            "index_entries": index_stats,
            "tenant_id": self.tenant_id,
        }

    def cleanup_orphaned_entries(self) -> int:
        """Remove orphaned index entries."""
        query = """
            DELETE FROM registry.index_entries ie
            WHERE ie.tenant_id = %s
            AND NOT EXISTS (
                SELECT 1 FROM documents d
                WHERE d.doc_id = ie.doc_id
                AND d.tenant_id = ie.tenant_id
            )
        """

        result = self.db.execute(query, (self.tenant_id,))

        if result > 0:
            logger.info(f"Cleaned up {result} orphaned index entries")

        return result

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
