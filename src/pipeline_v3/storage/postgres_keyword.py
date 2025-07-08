"""
PostgreSQL implementation of keyword search with full-text search.

This module provides PostgreSQL-backed full-text search that replaces
SQLite FTS5 with PostgreSQL's native tsvector/tsquery functionality.
"""

import re
from typing import Any, Dict, List

from src.pipeline_v3.core.data_structures import TextChunk
from src.pipeline_v3.core.postgres_base import PostgreSQLBase
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class PostgreSQLKeywordIndex:
    """PostgreSQL full-text search index with BM25-like ranking."""

    def __init__(
        self, config: PipelineConfig = None, tenant_id: str | None = None, connection_manager=None
    ):
        """
        Initialize PostgreSQL keyword index.

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
            self.db = connection_manager.get_pool(self.tenant_id, self.pg_settings.search_schema)
        else:
            # Create dedicated connection pool
            self.db = PostgreSQLBase(
                self.pg_settings,
                self.pg_settings.search_schema,
                log_queries=self.db_settings.log_queries,
            )
            # Initialize connection pool
            self.db.initialize()

        # Set tenant context for RLS
        self._set_tenant_context()

        logger.info(f"PostgreSQLKeywordIndex initialized for tenant: {self.tenant_id}")

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

    def index_nodes(
        self,
        nodes: List[TextChunk],
        doc_id: str,
        source: str,
        pairs: List[tuple[str, str]],
    ):
        """Index nodes for full-text search."""
        # Insert or update document metadata
        metadata_query = """
            INSERT INTO doc_metadata (doc_id, tenant_id, source, metadata, chunk_count)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (doc_id)
            DO UPDATE SET
                tenant_id = EXCLUDED.tenant_id,
                source = EXCLUDED.source,
                metadata = EXCLUDED.metadata,
                chunk_count = EXCLUDED.chunk_count
        """

        # Store pairs in metadata JSON
        metadata = {"pairs": pairs}

        self.db.execute(
            metadata_query,
            (
                doc_id,
                self.tenant_id,
                source,
                self.db.json_to_jsonb(metadata),
                len(nodes),
            ),
        )

        # Delete existing chunks for this document
        delete_query = """
            DELETE FROM keyword_search
            WHERE doc_id = %s AND tenant_id = %s
        """
        self.db.execute(delete_query, (doc_id, self.tenant_id))

        # Index each chunk
        for node in nodes:
            # Extract keywords if present (for future use)
            # keywords = ""
            # if "Context:" in node.text:
            #     # Extract keyword line
            #     parts = node.text.split("Context:", 1)
            #     if len(parts) > 1:
            #         keywords = parts[1].strip().split("\n")[0]

            # Clean text for indexing
            clean_text = self._clean_text(node.text)

            # Insert chunk
            chunk_query = """
                INSERT INTO keyword_search (
                    doc_id, node_id, tenant_id, chunk_index, content, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (tenant_id, node_id) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata
            """

            self.db.execute(
                chunk_query,
                (
                    doc_id,
                    node.node_id,
                    self.tenant_id,
                    node.metadata.get("chunk_index", 0),
                    clean_text,
                    self.db.json_to_jsonb(node.metadata),
                ),
            )

        logger.info(f"Indexed {len(nodes)} chunks for document: {doc_id[:8]}")

    def _clean_text(self, text: str) -> str:
        """Clean text for better indexing."""
        # Remove markdown formatting
        text = re.sub(r"[#*`\[\]()]", " ", text)
        # Normalize whitespace
        return " ".join(text.split())

    def _escape_search_query(self, query: str) -> str:
        """Escape PostgreSQL full-text search special characters."""
        if not query or not query.strip():
            return ""

        # Remove quotes to prevent injection
        query = query.replace('"', " ").replace("'", " ")

        # Remove PostgreSQL operators
        query = re.sub(r"[(){}[\]<>|&:!]", " ", query)

        # Remove SQL comments
        query = re.sub(r"[-]{2,}.*$", " ", query)
        query = re.sub(r"/\*.*?\*/", " ", query, flags=re.DOTALL)

        # Remove SQL keywords
        sql_keywords = [
            "DROP",
            "DELETE",
            "INSERT",
            "UPDATE",
            "CREATE",
            "ALTER",
            "UNION",
            "SELECT",
            "FROM",
            "WHERE",
            "TABLE",
            "DATABASE",
            "SCHEMA",
            "GRANT",
            "REVOKE",
            "EXECUTE",
        ]
        for keyword in sql_keywords:
            query = re.sub(rf"\b{keyword}\b", " ", query, flags=re.IGNORECASE)

        # Clean up whitespace
        query = " ".join(query.split())

        # Return safe default if empty
        if not query.strip():
            return "placeholder"

        return query

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Full-text search using PostgreSQL tsquery.

        Args:
            query: Search query
            limit: Maximum results to return

        Returns:
            List of search results with scores
        """
        # Escape and prepare query
        clean_query = self._escape_search_query(query)

        # Use phrase search for better results
        search_query = """
            SELECT
                doc_id,
                node_id,
                chunk_index,
                content as text,
                metadata,
                ts_rank(content_tsvector, query) AS score
            FROM
                keyword_search,
                plainto_tsquery('english', %s) query
            WHERE
                tenant_id = %s AND
                content_tsvector @@ query
            ORDER BY score DESC
            LIMIT %s
        """

        try:
            rows = self.db.fetch_all(search_query, (clean_query, self.tenant_id, limit))

            return [
                {
                    "doc_id": str(row["doc_id"]),
                    "node_id": row["node_id"],
                    "chunk_index": row["chunk_index"],
                    "text": row["text"],
                    "metadata": self.db.jsonb_to_dict(row["metadata"]) or {},
                    "score": float(row["score"]),
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            return []

    def search_with_filters(
        self, query: str, filters: Dict[str, Any], limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search with metadata filters using JSONB queries.

        Args:
            query: Search query
            filters: Metadata filters
            limit: Maximum results

        Returns:
            Filtered search results
        """
        clean_query = self._escape_search_query(query)

        # Build filter conditions
        conditions = ["tenant_id = %s", "search_vector @@ query"]
        params = [self.tenant_id]

        # Add JSONB filters
        for key, value in filters.items():
            if isinstance(value, list | tuple):
                # Array contains
                conditions.append("metadata @> %s")
                params.append(self.db.json_to_jsonb({key: value}))
            else:
                # Exact match
                conditions.append("metadata @> %s")
                params.append(self.db.json_to_jsonb({key: value}))

        # Build query
        search_query = f"""
            SELECT
                doc_id,
                chunk_id,
                text,
                keywords,
                metadata,
                ts_rank(search_vector, query) AS score
            FROM
                documents,
                plainto_tsquery('english', %s) query
            WHERE
                {" AND ".join(conditions)}
            ORDER BY score DESC
            LIMIT %s
        """

        # Add query text and limit to params
        params.insert(1, clean_query)  # Insert after tenant_id
        params.append(limit)

        try:
            rows = self.db.fetch_all(search_query, tuple(params))

            return [
                {
                    "doc_id": str(row["doc_id"]),
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "keywords": row["keywords"],
                    "metadata": self.db.jsonb_to_dict(row["metadata"]) or {},
                    "score": float(row["score"]),
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Filtered search failed: {e}")
            return []

    def search_by_part_number(self, part_number: str) -> List[Dict[str, Any]]:
        """Search specifically by part number in metadata."""
        # Use JSONB search for pairs
        query = """
            SELECT DISTINCT
                dm.doc_id,
                dm.source,
                dm.metadata
            FROM doc_metadata dm
            WHERE
                dm.tenant_id = %s AND
                dm.metadata @> %s
        """

        # Search for part number in pairs array
        search_filter = {"pairs": [[part_number]]}  # Nested array structure

        rows = self.db.fetch_all(query, (self.tenant_id, self.db.json_to_jsonb(search_filter)))

        results = []
        for row in rows:
            metadata = self.db.jsonb_to_dict(row["metadata"]) or {}
            results.append(
                {
                    "doc_id": str(row["doc_id"]),
                    "source": row["source"],
                    "pairs": metadata.get("pairs", []),
                }
            )

        return results

    def fuzzy_search(
        self, query: str, similarity: float = 0.3, limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Fuzzy search using PostgreSQL trigram similarity.

        Args:
            query: Search query
            similarity: Minimum similarity threshold (0-1)
            limit: Maximum results

        Returns:
            Fuzzy search results
        """
        clean_query = self._escape_search_query(query)

        # Use trigram similarity for fuzzy matching
        fuzzy_query = """
            SELECT
                doc_id,
                chunk_id,
                text,
                keywords,
                metadata,
                similarity(text, %s) AS score
            FROM documents
            WHERE
                tenant_id = %s AND
                text %% %s AND
                similarity(text, %s) > %s
            ORDER BY score DESC
            LIMIT %s
        """

        try:
            rows = self.db.fetch_all(
                fuzzy_query,
                (
                    clean_query,
                    self.tenant_id,
                    clean_query,
                    clean_query,
                    similarity,
                    limit,
                ),
            )

            return [
                {
                    "doc_id": str(row["doc_id"]),
                    "chunk_id": row["chunk_id"],
                    "text": row["text"],
                    "keywords": row["keywords"],
                    "metadata": self.db.jsonb_to_dict(row["metadata"]) or {},
                    "score": float(row["score"]),
                }
                for row in rows
            ]

        except Exception as e:
            logger.error(f"Fuzzy search failed: {e}")
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get index statistics."""
        stats_query = """
            SELECT
                COUNT(DISTINCT doc_id) as total_documents,
                COUNT(*) as total_chunks,
                COUNT(*) as chunks_with_keywords,
                pg_size_pretty(pg_relation_size('keyword_search')) as table_size,
                pg_size_pretty(pg_relation_size('idx_keyword_search_fts')) as index_size
            FROM keyword_search
            WHERE tenant_id = %s
        """

        stats = self.db.fetch_one(stats_query, (self.tenant_id,))

        return {
            "total_documents": stats["total_documents"] or 0,
            "total_chunks": stats["total_chunks"] or 0,
            "documents_with_keywords": stats["chunks_with_keywords"] or 0,
            "table_size": stats["table_size"],
            "index_size": stats["index_size"],
            "tenant_id": self.tenant_id,
        }

    def delete_document(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        query = """
            DELETE FROM keyword_search
            WHERE doc_id = %s AND tenant_id = %s
        """

        result = self.db.execute(query, (doc_id, self.tenant_id))

        # Also delete from metadata
        meta_query = """
            DELETE FROM doc_metadata
            WHERE doc_id = %s AND tenant_id = %s
        """
        self.db.execute(meta_query, (doc_id, self.tenant_id))

        logger.info(f"Deleted {result} chunks for document: {doc_id[:8]}")
        return result

    def remove_document(self, doc_id: str) -> int:
        """Remove document from index (alias for delete_document for interface compatibility)."""
        return self.delete_document(doc_id)

    def rebuild_search_vectors(self) -> int:
        """Rebuild search vectors for all documents (maintenance operation)."""
        # This would be triggered if we change the text search configuration
        query = """
            UPDATE keyword_search
            SET content_tsvector = to_tsvector('english', content)
            WHERE tenant_id = %s
        """

        result = self.db.execute(query, (self.tenant_id,))
        logger.info(f"Rebuilt search vectors for {result} documents")
        return result

    def close(self):
        """Close database connection."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
