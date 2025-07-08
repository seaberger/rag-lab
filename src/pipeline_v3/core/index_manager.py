"""
Index Manager - Phase 2 Implementation

Advanced index lifecycle management with CRUD operations for vector and keyword indexes.
Provides consistent operations across Qdrant vector store and PostgreSQL keyword index.
Requires DatabaseFactory adapters for all database operations.
"""

import asyncio
import time
from typing import Any
from uuid import UUID

import qdrant_client
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointStruct,
    VectorParams,
)

# Import custom data structures instead of LlamaIndex
from src.pipeline_v3.core.data_structures import (
    Document,
    TextChunk,
    TextSplitter,
)
from src.pipeline_v3.core.embedding_service import EmbeddingService
from src.pipeline_v3.core.registry import DocumentRegistry, DocumentState, IndexType
from src.pipeline_v3.core.transaction_coordinator import (
    Checkpoint,
    OperationType,
    TransactionOperation,
)
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig
from src.pipeline_v3.utils.filter_utils import FilterBuilder

# Backend-aware helpers are now integrated into our custom structures
BACKEND_AWARE_HELPERS = True
BACKEND_AWARE_QUERY = True


class IndexManager:
    """Advanced index lifecycle management for vector and keyword indexes."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        registry: DocumentRegistry | None = None,
        keyword_index: Any | None = None,
    ):
        """Initialize index manager with configuration.

        Args:
            config: Pipeline configuration
            registry: Optional DocumentRegistry (for backwards compatibility)
            keyword_index: Optional keyword index adapter from DatabaseFactory
        """
        self.config = config or PipelineConfig()

        # Use provided registry or create new one
        self.registry = registry or DocumentRegistry(config)

        # Storage paths
        self.qdrant_path = self.config.qdrant.path
        self.keyword_db_path = self.config.storage.keyword_db_path

        # Initialize components
        self._init_qdrant()

        # Keyword index adapter is required - no SQLite fallback
        if keyword_index:
            self.keyword_index = keyword_index
            self.keyword_conn = None  # Not used when using adapter
            logger.info("IndexManager using DatabaseFactory keyword index adapter")
        else:
            # PostgreSQL is required - no SQLite fallback
            raise ValueError(
                "IndexManager requires a keyword index adapter. "
                "SQLite is no longer supported. Please use DatabaseFactory to create adapters."
            )

        # Initialize embedding service and text splitter
        self.embedding_service = EmbeddingService(self.config)
        self.text_splitter = TextSplitter(
            chunk_size=self.config.chunking.chunk_size,
            chunk_overlap=self.config.chunking.chunk_overlap,
        )

        # Cache for document sources
        self._doc_source_cache = {}

        # Backend awareness is now integrated into our custom structures
        logger.info(f"Using custom structures with backend: {self.config.database.backend}")

        logger.info(
            f"IndexManager initialized with Qdrant: {self.qdrant_path} and keyword index adapter"
        )

    def _init_qdrant(self) -> None:
        """Initialize Qdrant vector store (supports both local and server modes)."""
        try:
            # Create Qdrant client based on mode
            if self.config.qdrant.mode == "server":
                # Server mode configuration
                import os

                logger.info(
                    f"Initializing Qdrant in server mode: {self.config.qdrant.server.host}:{self.config.qdrant.server.port}"
                )

                # Get API key from environment if not in config
                api_key = self.config.qdrant.server.api_key
                if api_key is None:
                    api_key = os.getenv("QDRANT_API_KEY")

                self.qdrant_client = qdrant_client.QdrantClient(
                    host=self.config.qdrant.server.host,
                    port=self.config.qdrant.server.port,
                    grpc_port=self.config.qdrant.server.grpc_port,
                    api_key=api_key,
                    https=self.config.qdrant.server.https,
                    timeout=self.config.qdrant.server.timeout,
                )

                # Ensure collection exists
                self._ensure_collection_exists()

            else:
                # Local mode (default)
                logger.info(f"Initializing Qdrant in local mode: {self.qdrant_path}")
                self.qdrant_client = qdrant_client.QdrantClient(path=self.qdrant_path)

                # Ensure collection exists in local mode too
                self._ensure_collection_exists()

            logger.info(f"Qdrant client initialized: {self.config.qdrant.collection_name}")

        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self.qdrant_client = None

    def _ensure_collection_exists(self) -> None:
        """Ensure the Qdrant collection exists with proper configuration."""
        try:
            # Check if collection exists
            collections = self.qdrant_client.get_collections()
            collection_names = [col.name for col in collections.collections]

            if self.config.qdrant.collection_name not in collection_names:
                logger.info(f"Creating Qdrant collection: {self.config.qdrant.collection_name}")

                # Create collection with proper vector configuration
                self.qdrant_client.create_collection(
                    collection_name=self.config.qdrant.collection_name,
                    vectors_config=VectorParams(
                        size=self.config.openai.dimensions,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {self.config.qdrant.collection_name}")
            else:
                logger.info(f"Collection already exists: {self.config.qdrant.collection_name}")

        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise

    # DatabaseFactory adapter helper methods
    def _keyword_index_chunks(self, chunks: list[TextChunk]) -> bool:
        """Add chunks to keyword index using DatabaseFactory adapter."""
        if not self.keyword_index:
            logger.error("No keyword index adapter available")
            return False

        try:
            # Get doc_id from first chunk's metadata
            doc_id = chunks[0].metadata.get("doc_id", "unknown")
            source = chunks[0].metadata.get("source", "unknown")
            pairs = chunks[0].metadata.get("pairs", [])

            # Debug log to understand why source might be unknown
            logger.debug(f"Chunk 0 metadata keys: {list(chunks[0].metadata.keys())}")
            logger.debug(f"Extracted source: '{source}', doc_id: '{doc_id}'")

            # Pass chunks directly - the adapter expects TextChunk objects
            logger.debug(f"Indexing {len(chunks)} chunks with pairs: {pairs}")
            self.keyword_index.index_nodes(chunks, doc_id, source, pairs)
            logger.debug(f"Successfully indexed {len(chunks)} chunks for doc {doc_id[:8]}")
            return True
        except Exception as e:
            logger.error(f"Failed to index chunks with adapter: {e}")
            import traceback

            logger.error(f"Traceback: {traceback.format_exc()}")
            return False

    def _keyword_search(
        self, query: str, top_k: int, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search keyword index using DatabaseFactory adapter."""
        if not self.keyword_index:
            logger.error("No keyword index adapter available for search")
            return []

        # Add backend-specific filters if needed
        if filters and self.config.database.backend == "postgresql":
            if "metadata" not in filters:
                filters["metadata"] = {}
            filters["metadata"]["tenant_id"] = self.config.database.postgresql.default_tenant_id

        try:
            # Check if the adapter supports filters
            import inspect

            sig = inspect.signature(self.keyword_index.search)
            if "filters" in sig.parameters:
                return self.keyword_index.search(query, top_k, filters=filters)
            else:
                # Adapter doesn't support filters, just do basic search
                return self.keyword_index.search(query, top_k)
        except Exception as e:
            logger.error(f"Failed to search with adapter: {e}")
            return []

    def _keyword_remove_document(self, doc_id: str) -> int:
        """Remove document from keyword index using DatabaseFactory adapter."""
        if not self.keyword_index:
            logger.error("No keyword index adapter available")
            return 0

        try:
            # Assuming adapter has a remove_document method
            if hasattr(self.keyword_index, "remove_document"):
                return self.keyword_index.remove_document(doc_id)
            else:
                logger.warning("Keyword index adapter does not support remove_document")
                return 0
        except Exception as e:
            logger.error(f"Failed to remove document with adapter: {e}")
            return 0

    def _keyword_get_stats(self) -> dict[str, Any]:
        """Get keyword index statistics using DatabaseFactory adapter."""
        if not self.keyword_index:
            logger.error("No keyword index adapter available")
            return {"total_entries": 0, "unique_documents": 0}

        try:
            return self.keyword_index.get_stats()
        except Exception as e:
            logger.error(f"Failed to get stats with adapter: {e}")
            return {"total_entries": 0, "unique_documents": 0}

    def _keyword_check_document_exists(self, doc_id: str) -> dict[str, Any]:
        """Check if document exists in keyword index using DatabaseFactory adapter."""
        if not self.keyword_index:
            logger.error("No keyword index adapter available")
            return {
                "exists": False,
                "count": 0,
                "error": "Keyword index not available",
            }

        try:
            # Most adapters don't have a specific exists method, so we search for the doc
            if hasattr(self.keyword_index, "search"):
                results = self.keyword_index.search("*", top_k=1, filters={"doc_id": doc_id})
                count = len(results)
                return {"exists": count > 0, "count": count}
            else:
                logger.warning("Keyword index adapter does not support search")
                return {"exists": False, "count": 0}
        except Exception as e:
            logger.error(f"Failed to check document exists with adapter: {e}")
            return {"exists": False, "count": 0, "error": str(e)}

    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """Add document to specified indexes."""
        try:
            # Create document with custom structure
            doc_metadata = metadata or {}
            doc_metadata["doc_id"] = doc_id  # Ensure doc_id is in metadata
            doc = Document(text=content, doc_id=doc_id, metadata=doc_metadata)

            # Split into chunks
            chunks = self.text_splitter.create_chunks(doc)

            # Add backend-specific metadata
            if self.config.database.backend == "postgresql":
                tenant_id = self.config.database.postgresql.default_tenant_id
                for chunk in chunks:
                    chunk.metadata["tenant_id"] = tenant_id
                    chunk.metadata["backend"] = "postgresql"
            else:
                for chunk in chunks:
                    chunk.metadata["backend"] = "sqlite"

            success = True

            # Add to vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.qdrant_client:
                try:
                    # Generate embeddings for all chunks
                    texts = [chunk.text for chunk in chunks]
                    embeddings = self.embedding_service.get_text_embedding_batch(texts)

                    # Create points for Qdrant
                    points = []
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
                        point = PointStruct(
                            id=chunk.id,
                            vector=embedding,
                            payload={
                                "text": chunk.text,
                                "doc_id": doc_id,
                                "chunk_index": i,
                                "metadata": chunk.metadata,
                            },
                        )
                        points.append(point)

                    # Upsert to Qdrant
                    self.qdrant_client.upsert(
                        collection_name=self.config.qdrant.collection_name,
                        points=points,
                    )

                    # Register index entries
                    for i, chunk in enumerate(chunks):
                        logger.debug(
                            f"Registering vector index entry: doc_id={doc_id}, chunk_id={chunk.id}"
                        )
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.VECTOR,
                            node_id=chunk.id,
                            chunk_index=i,
                            content_hash=chunk.hash,
                            metadata=chunk.metadata,
                        )

                    logger.info(
                        f"Added document {doc_id[:8]} to vector index ({len(chunks)} chunks)"
                    )

                except Exception as e:
                    logger.error(f"Failed to add to vector index: {e}")
                    success = False

            # Add to keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH] and (
                self.keyword_index or self.keyword_conn
            ):
                try:
                    # Use helper method for keyword indexing
                    keyword_success = self._keyword_index_chunks(chunks)

                    if keyword_success:
                        # Register index entries
                        for i, chunk in enumerate(chunks):
                            self.registry.register_index_entry(
                                doc_id=doc_id,
                                index_type=IndexType.KEYWORD,
                                node_id=chunk.id,
                                chunk_index=i,
                                content_hash=chunk.hash,
                                metadata=chunk.metadata,
                            )

                        logger.info(
                            f"Added document {doc_id[:8]} to keyword index ({len(chunks)} chunks)"
                        )
                    else:
                        success = False

                except Exception as e:
                    logger.error(f"Failed to add to keyword index: {e}")
                    success = False

            # Update registry if successful
            if success:
                self.registry.mark_indexed(doc_id, index_types, len(chunks))
            else:
                self.registry.update_document_state(
                    doc_id, DocumentState.CORRUPTED, "Failed to index"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to add document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False

    def add_chunks(
        self,
        doc_id: str,
        chunks: list[TextChunk],
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """Add pre-processed chunks to specified indexes.

        This method is used when chunks have already been processed with
        keyword enhancement or other transformations.

        Args:
            doc_id: Document identifier
            chunks: Pre-processed TextChunk objects
            index_types: Which indexes to update

        Returns:
            Success status
        """
        logger.debug(
            f"add_chunks called with doc_id={doc_id}, {len(chunks)} chunks, index_types={index_types}"
        )
        try:
            if not chunks:
                logger.warning(f"No chunks provided for document {doc_id}")
                return False

            success = True

            # Ensure backend-specific metadata
            if self.config.database.backend == "postgresql":
                tenant_id = self.config.database.postgresql.default_tenant_id
                for chunk in chunks:
                    chunk.metadata["tenant_id"] = tenant_id
                    chunk.metadata["backend"] = "postgresql"
                    chunk.metadata["doc_id"] = doc_id
            else:
                for chunk in chunks:
                    chunk.metadata["backend"] = "sqlite"
                    chunk.metadata["doc_id"] = doc_id

            # Add to vector index
            if index_types.value in ["vector", "both"] and self.qdrant_client:
                try:
                    # Generate embeddings for all chunks
                    texts = [chunk.text for chunk in chunks]
                    embeddings = self.embedding_service.get_text_embedding_batch(texts)

                    # Create points for Qdrant
                    points = []
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
                        point = PointStruct(
                            id=chunk.id,
                            vector=embedding,
                            payload={
                                "text": chunk.text,
                                "doc_id": doc_id,
                                "chunk_index": i,
                                "metadata": chunk.metadata,
                            },
                        )
                        points.append(point)

                    # Upsert to Qdrant
                    self.qdrant_client.upsert(
                        collection_name=self.config.qdrant.collection_name,
                        points=points,
                    )

                    # Register index entries
                    for i, chunk in enumerate(chunks):
                        logger.debug(
                            f"Registering vector index entry: doc_id={doc_id}, chunk_id={chunk.id}"
                        )
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.VECTOR,
                            node_id=chunk.id,
                            chunk_index=i,
                            content_hash=chunk.hash,
                            metadata=chunk.metadata,
                        )

                    logger.info(
                        f"Added document {doc_id[:8]} to vector index ({len(chunks)} chunks)"
                    )

                except Exception as e:
                    logger.error(f"Failed to add chunks to vector index: {e}")
                    success = False

            # Add to keyword index
            if index_types.value in ["keyword", "both"] and (
                self.keyword_index or self.keyword_conn
            ):
                try:
                    # Use helper method for keyword indexing
                    keyword_success = self._keyword_index_chunks(chunks)

                    if keyword_success:
                        # Register index entries
                        for i, chunk in enumerate(chunks):
                            self.registry.register_index_entry(
                                doc_id=doc_id,
                                index_type=IndexType.KEYWORD,
                                node_id=chunk.id,
                                chunk_index=i,
                                content_hash=chunk.hash,
                                metadata=chunk.metadata,
                            )

                        logger.info(
                            f"Added document {doc_id[:8]} to keyword index ({len(chunks)} chunks)"
                        )
                    else:
                        success = False

                except Exception as e:
                    logger.error(f"Failed to add chunks to keyword index: {e}")
                    success = False

            # Update registry if successful
            if success:
                try:
                    self.registry.mark_indexed(doc_id, index_types, len(chunks))
                    logger.debug(f"Successfully marked document {doc_id[:8]} as indexed")
                except Exception as e:
                    logger.error(f"Failed to mark document as indexed: {e}")
                    import traceback

                    logger.error(f"Traceback: {traceback.format_exc()}")
                    success = False
                    self.registry.update_document_state(
                        doc_id, DocumentState.CORRUPTED, f"Failed to mark as indexed: {e}"
                    )
            else:
                self.registry.update_document_state(
                    doc_id, DocumentState.CORRUPTED, "Failed to index chunks"
                )

            logger.debug(f"add_chunks returning success={success} for doc {doc_id[:8]}")
            return success

        except Exception as e:
            logger.error(f"Failed to add chunks for document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False

    def update_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """Update document in specified indexes."""
        try:
            # Remove existing entries first
            if not self.remove_document(doc_id, index_types):
                logger.warning(f"Failed to remove existing entries for {doc_id}")

            # Add updated document
            return self.add_document(doc_id, content, metadata, index_types)

        except Exception as e:
            logger.error(f"Failed to update document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False

    def remove_document(self, doc_id: str, index_types: IndexType = IndexType.BOTH) -> bool:
        """Remove document from specified indexes."""
        try:
            success = True

            # Get existing index entries
            entries = self.registry.get_index_entries(doc_id)

            # Remove from vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.qdrant_client:
                try:
                    vector_entries = [e for e in entries if e.index_type == IndexType.VECTOR.value]
                    if vector_entries:
                        # Use filter-based deletion to ensure all chunks are removed
                        self.qdrant_client.delete(
                            collection_name=self.config.qdrant.collection_name,
                            points_selector=FilterSelector(
                                filter=Filter(
                                    must=[
                                        FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                                    ]
                                )
                            ),
                        )
                        logger.info(
                            f"Removed all chunks for document {doc_id[:8]} from vector index"
                        )

                except Exception as e:
                    logger.error(f"Failed to remove from vector index: {e}")
                    success = False

            # Remove from keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH] and (
                self.keyword_index or self.keyword_conn
            ):
                try:
                    deleted_count = self._keyword_remove_document(doc_id)

                    if deleted_count > 0:
                        logger.info(
                            f"Removed {deleted_count} keyword entries for document {doc_id[:8]}"
                        )

                except Exception as e:
                    logger.error(f"Failed to remove from keyword index: {e}")
                    success = False

            # Update registry - only remove index entries, not the document itself
            if success:
                self.registry.remove_index_entries(doc_id, index_types)

                logger.info(f"Removed document {doc_id[:8]} from {index_types.value} index(es)")

            return success

        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {e}")
            return False

    def get_document_chunks(
        self, doc_id: str, index_type: IndexType = IndexType.VECTOR
    ) -> list[dict[str, Any]]:
        """Get document chunks from specified index."""
        chunks = []

        try:
            if index_type == IndexType.VECTOR and self.qdrant_client:
                # Get from vector index via registry
                entries = self.registry.get_index_entries(doc_id, IndexType.VECTOR)

                for entry in entries:
                    # Note: Qdrant doesn't provide easy content retrieval by node_id
                    # This would need enhancement for full content retrieval
                    chunks.append(
                        {
                            "node_id": entry.node_id,
                            "chunk_index": entry.chunk_index,
                            "content_hash": entry.content_hash,
                            "metadata": entry.metadata,
                            "source": "vector",
                        }
                    )

            elif index_type == IndexType.KEYWORD and self.keyword_conn:
                cursor = self.keyword_conn.execute(
                    """
                    SELECT node_id, chunk_index, content, metadata, content_hash
                    FROM keyword_index WHERE doc_id = ?
                    ORDER BY chunk_index
                """,
                    (doc_id,),
                )

                for row in cursor.fetchall():
                    chunks.append(
                        {
                            "node_id": row[0],
                            "chunk_index": row[1],
                            "content": row[2],
                            "metadata": row[3],
                            "content_hash": row[4],
                            "source": "keyword",
                        }
                    )

        except Exception as e:
            logger.error(f"Failed to get chunks for document {doc_id}: {e}")

        return chunks

    def _extract_payload_data(self, payload: dict) -> dict:
        """Extract data from Qdrant payload, handling server mode serialization.

        In server mode, node data is serialized in _node_content field.
        This method extracts the actual data regardless of storage format.
        """
        try:
            # Check if this is server mode format with _node_content
            if "_node_content" in payload and isinstance(payload["_node_content"], str):
                import json

                node_content = json.loads(payload["_node_content"])

                # Extract commonly needed fields
                extracted = {
                    "text": node_content.get("text", ""),
                    "metadata": node_content.get("metadata", {}),
                    "doc_id": payload.get("doc_id")
                    or node_content.get("metadata", {}).get("doc_id", "unknown"),
                }

                # Merge top-level payload fields (excluding _node_content)
                for key, value in payload.items():
                    if key not in ["_node_content", "_node_type"]:
                        extracted[key] = value

                return extracted
            else:
                # Direct payload format (local mode or legacy)
                return payload

        except Exception as e:
            logger.warning(f"Failed to extract payload data: {e}")
            return payload

    def _get_document_source(self, doc_id: str) -> str:
        """Get document source path from registry with caching."""
        if doc_id in self._doc_source_cache:
            return self._doc_source_cache[doc_id]

        try:
            doc = self.registry.get_document(doc_id)
            if doc:
                # Extract just the filename from the full path
                source_path = doc.source
                if "/" in source_path:
                    source = source_path.split("/")[-1]
                else:
                    source = source_path
                self._doc_source_cache[doc_id] = source
                return source
        except Exception as e:
            logger.debug(f"Could not retrieve source for doc {doc_id}: {e}")

        return "unknown"

    def search_vector(
        self, query: str, top_k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search vector index."""
        logger.debug(f"search_vector called: query='{query}', top_k={top_k}, filters={filters}")
        if not self.qdrant_client:
            logger.error("Vector search not available")
            return []

        try:
            # Parse unified filters
            parsed_filters = FilterBuilder.parse_unified_filters(filters)

            # Create query embedding
            query_embedding = self.embedding_service.get_text_embedding(query)

            # Build Qdrant filter from parsed filters
            qdrant_filter = None
            must_conditions = []

            # Add user-provided filters if present
            if parsed_filters:
                # Add doc_ids filter if present
                if "doc_ids" in parsed_filters:
                    for doc_id in parsed_filters["doc_ids"]:
                        must_conditions.append(
                            FieldCondition(key="doc_id", match=MatchValue(value=doc_id))
                        )

                # Add metadata filters
                if "metadata" in parsed_filters:
                    for key, value in parsed_filters["metadata"].items():
                        must_conditions.append(
                            FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
                        )

            # Add backend-specific filters for PostgreSQL (always apply for tenant isolation)
            if self.config.database.backend == "postgresql":
                tenant_id = self.config.database.postgresql.default_tenant_id
                logger.debug(f"Vector search: filtering by tenant_id = {tenant_id}")
                must_conditions.append(
                    FieldCondition(key="metadata.tenant_id", match=MatchValue(value=tenant_id))
                )
            else:
                logger.debug(f"Backend: {self.config.database.backend} - no tenant filtering")

            if must_conditions:
                qdrant_filter = Filter(must=must_conditions)

            # Search Qdrant directly
            search_results = self.qdrant_client.search(
                collection_name=self.config.qdrant.collection_name,
                query_vector=query_embedding,
                query_filter=qdrant_filter,
                limit=top_k,
                with_payload=True,
            )

            # Convert results to expected format
            results = []
            for result in search_results:
                payload = result.payload
                doc_id = payload.get("doc_id", "unknown")

                results.append(
                    {
                        "node_id": str(result.id),
                        "chunk_id": str(result.id),  # Alias for compatibility
                        "score": result.score,
                        "content": payload.get("text", ""),
                        "text": payload.get("text", ""),  # Alias for compatibility
                        "metadata": payload.get("metadata", {}),
                        "doc_id": doc_id,
                        "source": self._get_document_source(doc_id),
                        "chunk_index": payload.get("chunk_index", 0),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    def search_keyword(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        doc_filter: list[str] | None = None,  # Backward compatibility
    ) -> list[dict[str, Any]]:
        """Search keyword index."""
        if not (self.keyword_index or self.keyword_conn):
            logger.error("Keyword search not available")
            return []

        try:
            # Handle backward compatibility
            if doc_filter and not filters:
                filters = {"doc_ids": doc_filter}

            # Parse unified filters
            parsed_filters = FilterBuilder.parse_unified_filters(filters)

            # Use helper method for keyword search
            search_results = self._keyword_search(query, top_k, parsed_filters)

            # Convert to expected format and add source information
            results = []
            for result in search_results:
                doc_id = result.get("metadata", {}).get("doc_id", result.get("doc_id", "unknown"))
                results.append(
                    {
                        "doc_id": doc_id,
                        "node_id": result.get("node_id", "unknown"),
                        "chunk_index": result.get("chunk_index", 0),
                        "content": result.get("text", result.get("content", "")),
                        "metadata": result.get("metadata", {}),
                        "score": result.get("score", 0.0),
                        "source": self._get_document_source(doc_id),
                    }
                )

            return results

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filters: dict[str, Any] | None = None,
        fusion_method: str = "rrf",  # "rrf", "weighted", "adaptive"
    ) -> list[dict[str, Any]]:
        """
        Perform advanced hybrid search with multiple fusion algorithms.

        Args:
            fusion_method: "rrf" (Reciprocal Rank Fusion), "weighted" (score-based),
                          "adaptive" (query-dependent weighting)
        """
        try:
            # Get more results for better fusion quality
            search_multiplier = max(3, top_k // 5)  # Adaptive multiplier
            vector_results = self.search_vector(query, top_k * search_multiplier, filters=filters)
            keyword_results = self.search_keyword(query, top_k * search_multiplier, filters=filters)

            # Choose fusion method
            if fusion_method == "rrf":
                return self._reciprocal_rank_fusion(vector_results, keyword_results, top_k, query)
            if fusion_method == "adaptive":
                return self._adaptive_fusion(vector_results, keyword_results, top_k, query)
            return self._enhanced_weighted_fusion(
                vector_results, keyword_results, top_k, vector_weight, keyword_weight
            )

        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []

    def _reciprocal_rank_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
        query: str,
        k: int = 60,  # RRF constant
    ) -> list[dict[str, Any]]:
        """
        Reciprocal Rank Fusion - industry standard for hybrid search.
        More robust than score-based fusion as it only uses ranking order.
        """
        combined_scores = {}

        # Add vector rankings - RRF formula: 1 / (k + rank)
        for rank, result in enumerate(vector_results, 1):
            node_id = result["node_id"]
            rrf_score = 1.0 / (k + rank)
            combined_scores[node_id] = {
                "result": result,
                "rrf_score": rrf_score,
                "vector_rank": rank,
                "keyword_rank": None,
                "search_type": "vector",
            }

        # Add keyword rankings
        for rank, result in enumerate(keyword_results, 1):
            node_id = result["node_id"]
            rrf_score = 1.0 / (k + rank)

            if node_id in combined_scores:
                # Found in both - combine RRF scores
                combined_scores[node_id]["rrf_score"] += rrf_score
                combined_scores[node_id]["keyword_rank"] = rank
                combined_scores[node_id]["search_type"] = "hybrid"
            else:
                combined_scores[node_id] = {
                    "result": result,
                    "rrf_score": rrf_score,
                    "vector_rank": None,
                    "keyword_rank": rank,
                    "search_type": "keyword",
                }

        # Sort by RRF score and prepare results
        sorted_items = sorted(
            combined_scores.items(), key=lambda x: x[1]["rrf_score"], reverse=True
        )[:top_k]

        results = []
        for _node_id, data in sorted_items:
            result = data["result"].copy()
            result["normalized_score"] = data["rrf_score"]
            result["fusion_score"] = data["rrf_score"]
            result["search_type"] = data["search_type"]
            result["vector_rank"] = data["vector_rank"]
            result["keyword_rank"] = data["keyword_rank"]
            results.append(result)

        return results

    def _adaptive_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
        query: str,
    ) -> list[dict[str, Any]]:
        """
        Adaptive fusion that adjusts weights based on query characteristics and result overlap.
        """
        # Analyze query characteristics
        query_length = len(query.split())
        has_technical_terms = any(
            term in query.lower()
            for term in [
                "sensor",
                "laser",
                "power",
                "wavelength",
                "calibration",
                "measurement",
            ]
        )
        has_model_numbers = any(char.isdigit() for char in query)

        # Calculate result overlap
        vector_nodes = {r["node_id"] for r in vector_results}
        keyword_nodes = {r["node_id"] for r in keyword_results}
        overlap_ratio = (
            len(vector_nodes & keyword_nodes) / len(vector_nodes | keyword_nodes)
            if vector_nodes or keyword_nodes
            else 0
        )

        # Adaptive weight calculation
        if has_model_numbers or len(query.split()) <= 2:
            # Short queries or model numbers - favor keyword search
            vector_weight = 0.3 + (overlap_ratio * 0.2)
            keyword_weight = 0.7 - (overlap_ratio * 0.2)
        elif has_technical_terms and query_length > 3:
            # Technical concept queries - favor vector search
            vector_weight = 0.8 - (overlap_ratio * 0.1)
            keyword_weight = 0.2 + (overlap_ratio * 0.1)
        else:
            # Balanced approach
            vector_weight = 0.6
            keyword_weight = 0.4

        logger.info(
            f"Adaptive weights: vector={vector_weight:.2f}, keyword={keyword_weight:.2f}, overlap={overlap_ratio:.2f}"
        )

        return self._enhanced_weighted_fusion(
            vector_results, keyword_results, top_k, vector_weight, keyword_weight
        )

    def _enhanced_weighted_fusion(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int,
        vector_weight: float,
        keyword_weight: float,
    ) -> list[dict[str, Any]]:
        """Enhanced weighted fusion with better normalization and score distribution awareness."""

        # Enhanced normalization using z-score for better distribution handling
        def normalize_scores_enhanced(results: list[dict], score_key: str = "score") -> list[dict]:
            if not results:
                return results

            scores = [r.get(score_key, 0) for r in results]

            # Handle BM25 negative scores
            if score_key == "score" and any(s < 0 for s in scores):
                # Convert BM25 scores to positive range [0, 1]
                min_score = min(scores)
                max_score = max(scores)
                if max_score > min_score:
                    for _i, result in enumerate(results):
                        original_score = result.get(score_key, 0)
                        normalized = (original_score - min_score) / (max_score - min_score)
                        result["normalized_score"] = normalized
                else:
                    for result in results:
                        result["normalized_score"] = 0.5
            else:
                # Standard min-max normalization for vector scores
                max_score = max(scores) if scores else 1
                if max_score > 0:
                    for result in results:
                        result["normalized_score"] = result.get(score_key, 0) / max_score
                else:
                    for result in results:
                        result["normalized_score"] = 0

            return results

        # Normalize both result sets
        vector_results = normalize_scores_enhanced(vector_results)
        keyword_results = normalize_scores_enhanced(keyword_results)

        # Apply weights and combine
        combined = {}

        for result in vector_results:
            node_id = result["node_id"]
            weighted_score = result["normalized_score"] * vector_weight
            combined[node_id] = result.copy()
            combined[node_id]["fusion_score"] = weighted_score
            combined[node_id]["vector_score"] = result["normalized_score"]
            combined[node_id]["keyword_score"] = 0
            combined[node_id]["search_type"] = "vector"

        for result in keyword_results:
            node_id = result["node_id"]
            weighted_score = result["normalized_score"] * keyword_weight

            if node_id in combined:
                # Boost for appearing in both indexes
                boost_factor = 1.1  # 10% boost for consensus
                combined[node_id]["fusion_score"] = (
                    combined[node_id]["fusion_score"] + weighted_score
                ) * boost_factor
                combined[node_id]["keyword_score"] = result["normalized_score"]
                combined[node_id]["search_type"] = "hybrid"
            else:
                combined[node_id] = result.copy()
                combined[node_id]["fusion_score"] = weighted_score
                combined[node_id]["vector_score"] = 0
                combined[node_id]["keyword_score"] = result["normalized_score"]
                combined[node_id]["search_type"] = "keyword"

        # Sort by fusion score
        sorted_results = sorted(combined.values(), key=lambda x: x["fusion_score"], reverse=True)[
            :top_k
        ]

        # Set final normalized_score for compatibility
        for result in sorted_results:
            result["normalized_score"] = result["fusion_score"]

        return sorted_results

    def verify_consistency(self) -> dict[str, Any]:
        """Verify consistency between indexes and registry."""
        try:
            # Get registry statistics
            registry_stats = self.registry.get_statistics()

            # Check vector index consistency
            vector_consistency = self._check_vector_consistency()

            # Check keyword index consistency
            keyword_consistency = self._check_keyword_consistency()

            # Overall health score
            total_issues = (
                vector_consistency.get("missing_nodes", 0)
                + vector_consistency.get("extra_nodes", 0)
                + keyword_consistency.get("missing_entries", 0)
                + keyword_consistency.get("extra_entries", 0)
                + registry_stats["consistency"]["inconsistent_documents"]
                + registry_stats["consistency"]["orphaned_entries"]
            )

            health_score = max(0, 100 - (total_issues * 5))

            return {
                "registry": registry_stats,
                "vector_index": vector_consistency,
                "keyword_index": keyword_consistency,
                "overall_health": {
                    "score": health_score,
                    "total_issues": total_issues,
                    "status": (
                        "healthy"
                        if health_score >= 90
                        else "degraded"
                        if health_score >= 70
                        else "unhealthy"
                    ),
                },
                "timestamp": time.time(),
            }

        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return {"error": str(e)}

    def _check_vector_consistency(self) -> dict[str, Any]:
        """Check vector index consistency."""
        try:
            if not self.qdrant_client:
                return {"error": "Vector store not available"}

            # Get collection info
            collection_info = self.qdrant_client.get_collection(self.config.qdrant.collection_name)
            vector_count = collection_info.points_count

            # Get registry vector entries
            registry_entries = []
            for doc in self.registry.list_documents():
                if doc.vector_indexed:
                    entries = self.registry.get_index_entries(doc.doc_id, IndexType.VECTOR)
                    registry_entries.extend(entries)

            registry_count = len(registry_entries)

            return {
                "vector_store_count": vector_count,
                "registry_count": registry_count,
                "difference": abs(vector_count - registry_count),
                "consistent": vector_count == registry_count,
            }

        except Exception as e:
            logger.error(f"Vector consistency check failed: {e}")
            return {"error": str(e)}

    def _check_keyword_consistency(self) -> dict[str, Any]:
        """Check keyword index consistency."""
        try:
            if not (self.keyword_index or self.keyword_conn):
                return {"error": "Keyword index not available"}

            # Get keyword index count using helper method
            keyword_stats = self._keyword_get_stats()
            keyword_count = keyword_stats.get("total_entries", 0)

            # Get registry keyword entries
            registry_entries = []
            for doc in self.registry.list_documents():
                if doc.keyword_indexed:
                    entries = self.registry.get_index_entries(doc.doc_id, IndexType.KEYWORD)
                    registry_entries.extend(entries)

            registry_count = len(registry_entries)

            return {
                "keyword_index_count": keyword_count,
                "registry_count": registry_count,
                "difference": abs(keyword_count - registry_count),
                "consistent": keyword_count == registry_count,
            }

        except Exception as e:
            logger.error(f"Keyword consistency check failed: {e}")
            return {"error": str(e)}

    def repair_indexes(self) -> dict[str, Any]:
        """Repair index inconsistencies."""
        try:
            repair_results = {
                "registry_cleanup": 0,
                "vector_repairs": 0,
                "keyword_repairs": 0,
                "errors": [],
            }

            # Clean up registry inconsistencies
            try:
                orphaned_count = self.registry.cleanup_orphaned_entries()
                repair_results["registry_cleanup"] = orphaned_count
            except Exception as e:
                repair_results["errors"].append(f"Registry cleanup failed: {e}")

            # Mark inconsistent documents for reprocessing
            try:
                inconsistent_docs = self.registry.get_inconsistent_documents()
                for doc in inconsistent_docs:
                    self.registry.update_document_state(doc.doc_id, DocumentState.STALE)
                repair_results["vector_repairs"] = len(inconsistent_docs)
            except Exception as e:
                repair_results["errors"].append(f"Vector repair failed: {e}")

            logger.info(f"Index repair completed: {repair_results}")
            return repair_results

        except Exception as e:
            logger.error(f"Index repair failed: {e}")
            return {"error": str(e)}

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive index statistics."""
        try:
            stats = {
                "registry": self.registry.get_statistics(),
                "timestamp": time.time(),
            }

            # Vector index stats
            if self.qdrant_client:
                try:
                    collection_info = self.qdrant_client.get_collection(
                        self.config.qdrant.collection_name
                    )
                    stats["vector_index"] = {
                        "points_count": collection_info.points_count,
                        "collection_name": self.config.qdrant.collection_name,
                        "status": "available",
                    }
                except Exception as e:
                    stats["vector_index"] = {"status": "error", "error": str(e)}
            else:
                stats["vector_index"] = {"status": "unavailable"}

            # Keyword index stats
            if self.keyword_index or self.keyword_conn:
                try:
                    keyword_stats = self._keyword_get_stats()
                    stats["keyword_index"] = {
                        "entry_count": keyword_stats.get("total_entries", 0),
                        "document_count": keyword_stats.get("unique_documents", 0),
                        "status": "available",
                        "backend": "adapter" if self.keyword_index else "legacy_sqlite",
                    }
                except Exception as e:
                    stats["keyword_index"] = {"status": "error", "error": str(e)}
            else:
                stats["keyword_index"] = {"status": "unavailable"}

            return stats

        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}

    async def verify_vector_index_state(self, doc_id: str) -> dict[str, Any]:
        """
        Verify if a document exists in the vector index.

        Args:
            doc_id: Document ID to check

        Returns:
            Dict with:
            - exists: bool - whether document has any vectors
            - count: int - number of vectors for this document
            - node_ids: List[str] - list of node IDs (optional)
        """
        try:
            if not self.qdrant_client:
                return {
                    "exists": False,
                    "count": 0,
                    "error": "Vector store not available",
                }

            # Query Qdrant for points with this doc_id
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            # Search for all points with this doc_id in their payload
            result = self.qdrant_client.scroll(
                collection_name=self.config.qdrant.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
                limit=1000,  # Reasonable limit for document chunks
                with_payload=True,
                with_vectors=False,
            )

            points = result[0] if result and len(result) > 0 else []
            node_ids = [str(point.id) for point in points]

            return {
                "exists": len(points) > 0,
                "count": len(points),
                "node_ids": node_ids,
            }

        except Exception as e:
            logger.error(f"Failed to verify vector index state for {doc_id}: {e}")
            return {"exists": False, "count": 0, "error": str(e)}

    async def verify_keyword_index_state(self, doc_id: str) -> dict[str, Any]:
        """
        Verify if a document exists in the keyword index.

        Args:
            doc_id: Document ID to check

        Returns:
            Dict with:
            - exists: bool - whether document has any entries
            - count: int - number of keyword entries
        """
        try:
            return self._keyword_check_document_exists(doc_id)

        except Exception as e:
            logger.error(f"Failed to verify keyword index state for {doc_id}: {e}")
            return {"exists": False, "count": 0, "error": str(e)}

    async def delete_from_vector_index(self, doc_id: str) -> bool:
        """
        Delete a document from vector index only.

        Args:
            doc_id: Document ID to delete

        Returns:
            bool: Success status
        """
        try:
            if not self.qdrant_client:
                logger.warning("Qdrant client not available")
                return False

            # Use filter-based deletion to ensure all chunks are removed
            self.qdrant_client.delete(
                collection_name=self.config.qdrant.collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                    )
                ),
            )
            logger.info(f"Deleted all chunks for document {doc_id[:8]} from vector index")
            return True

        except Exception as e:
            logger.error(f"Failed to delete {doc_id} from vector index: {e}")
            return False

    async def delete_from_keyword_index(self, doc_id: str) -> bool:
        """
        Delete a document from keyword index only.

        Args:
            doc_id: Document ID to delete

        Returns:
            bool: Success status
        """
        try:
            if not (self.keyword_index or self.keyword_conn):
                logger.warning("Keyword index not available")
                return False

            # Delete from keyword index using helper method
            deleted_count = self._keyword_remove_document(doc_id)

            if deleted_count > 0:
                logger.info(
                    f"Deleted {deleted_count} entries for document {doc_id[:8]} from keyword index"
                )

            return True

        except Exception as e:
            logger.error(f"Failed to delete {doc_id} from keyword index: {e}")
            return False

    # Transaction support methods for Issue #27

    def prepare_add_transaction(
        self, operation: TransactionOperation, operation_id: UUID
    ) -> Checkpoint:
        """
        Prepare an add document operation for transaction.

        Args:
            operation: Transaction operation with document data
            operation_id: Unique operation ID

        Returns:
            Checkpoint with current state for rollback
        """
        # Capture current state for potential rollback
        doc_id = operation.doc_id

        # Check if document already exists in indexes
        vector_state = asyncio.run(self.verify_vector_index_state(doc_id))
        keyword_state = asyncio.run(self.verify_keyword_index_state(doc_id))

        checkpoint = Checkpoint(
            system_name="IndexManager",
            operation_id=operation_id,
            doc_id=doc_id,
            operation_type=operation.operation_type,
            state_before={
                "vector_exists": vector_state.get("exists", False),
                "vector_count": vector_state.get("count", 0),
                "keyword_exists": keyword_state.get("exists", False),
                "keyword_count": keyword_state.get("count", 0),
            },
        )

        # Store operation data for commit phase
        # In a real implementation, this would be stored persistently
        checkpoint.operation_data = operation.data

        return checkpoint

    def commit_transaction(self, checkpoint: Checkpoint) -> bool:
        """
        Commit a prepared transaction.

        Args:
            checkpoint: Checkpoint from prepare phase

        Returns:
            bool: Success status
        """
        try:
            if checkpoint.operation_type == OperationType.ADD_DOCUMENT:
                # Add to indexes using stored operation data
                if hasattr(checkpoint, "operation_data") and "nodes" in checkpoint.operation_data:
                    nodes = checkpoint.operation_data["nodes"]
                    doc_id = checkpoint.doc_id

                    # Add to both indexes
                    # Convert nodes to chunks if needed
                    if nodes and hasattr(nodes[0], "text"):
                        # Already TextChunk objects or compatible
                        result = self.add_chunks(
                            doc_id=doc_id, chunks=nodes, index_types=IndexType.BOTH
                        )
                    else:
                        logger.error("Invalid node data in checkpoint")
                        result = False
                    return result

            elif checkpoint.operation_type == OperationType.DELETE_DOCUMENT:
                # Delete from both indexes
                success = True
                success &= asyncio.run(self.delete_from_vector_index(checkpoint.doc_id))
                success &= asyncio.run(self.delete_from_keyword_index(checkpoint.doc_id))
                return success

            return True

        except Exception as e:
            logger.error(f"Failed to commit transaction: {e}")
            return False

    def rollback_transaction(self, checkpoint: Checkpoint) -> bool:
        """
        Rollback a transaction to previous state.

        Args:
            checkpoint: Checkpoint with state to restore

        Returns:
            bool: Success status
        """
        try:
            doc_id = checkpoint.doc_id
            state_before = checkpoint.state_before

            # If document didn't exist before, remove it
            if not state_before.get("vector_exists", False) and not state_before.get(
                "keyword_exists", False
            ):
                asyncio.run(self.delete_from_vector_index(doc_id))
                asyncio.run(self.delete_from_keyword_index(doc_id))

            # Note: Full rollback would require storing actual data
            # This is a simplified version that removes added data

            logger.info(f"Rolled back transaction for document {doc_id[:8]}")
            return True

        except Exception as e:
            logger.error(f"Failed to rollback transaction: {e}")
            return False

    def close(self) -> None:
        """Close database connections."""
        # Close DatabaseFactory adapter if available
        if hasattr(self, "keyword_index") and self.keyword_index:
            if hasattr(self.keyword_index, "close"):
                self.keyword_index.close()
                logger.debug("Keyword index adapter closed")

        # Close legacy SQLite connection if available
        if hasattr(self, "keyword_conn") and self.keyword_conn:
            self.keyword_conn.close()
            logger.debug("Legacy keyword index connection closed")

        if hasattr(self, "registry"):
            self.registry.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
