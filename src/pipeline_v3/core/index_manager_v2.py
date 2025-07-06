"""
Index Manager V2 - LlamaIndex-free Implementation

Advanced index lifecycle management with CRUD operations for vector and keyword indexes.
Uses custom data structures and direct Qdrant/OpenAI integration.
"""

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

import qdrant_client
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from src.pipeline_v3.core.data_structures import Document, TextChunk, TextSplitter
from src.pipeline_v3.core.embedding_service import EmbeddingService
from src.pipeline_v3.core.registry import DocumentRegistry, DocumentState, IndexType
from src.pipeline_v3.core.unified_query_engine import QueryRequest, UnifiedQueryEngine
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class IndexManagerV2:
    """Advanced index lifecycle management without LlamaIndex dependencies."""

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

        # Use provided keyword index adapter or create legacy SQLite connection
        if keyword_index:
            self.keyword_index = keyword_index
            self.keyword_conn = None  # Not used when using adapter
            logger.info("IndexManagerV2 using DatabaseFactory keyword index adapter")
        else:
            self.keyword_index = None
            self._init_keyword_index()  # Legacy SQLite initialization
            logger.info("IndexManagerV2 using legacy SQLite keyword index")

        # Initialize embedding service
        self.embedding_service = EmbeddingService(self.config)

        # Initialize text splitter
        self.text_splitter = TextSplitter(
            chunk_size=self.config.chunking.chunk_size,
            chunk_overlap=self.config.chunking.chunk_overlap,
        )

        # Initialize unified query engine
        self.query_engine = UnifiedQueryEngine(
            config=self.config,
            registry=self.registry,
            keyword_index=self.keyword_index,
            qdrant_client=self.qdrant_client,
            embedding_service=self.embedding_service,
        )

        # Cache for document sources
        self._doc_source_cache = {}

        adapter_info = "with adapter" if keyword_index else "with legacy SQLite"
        logger.info(
            f"IndexManagerV2 initialized with Qdrant: {self.qdrant_path} and keyword index {adapter_info}"
        )

    def _init_qdrant(self) -> None:
        """Initialize Qdrant vector store (supports both local and server modes)."""
        try:
            if self.config.qdrant.use_server:
                # Server mode
                self.qdrant_client = qdrant_client.QdrantClient(
                    host=self.config.qdrant.host,
                    port=self.config.qdrant.port,
                )
                logger.info(
                    f"Connected to Qdrant server at {self.config.qdrant.host}:{self.config.qdrant.port}"
                )
            else:
                # Local mode
                Path(self.qdrant_path).mkdir(parents=True, exist_ok=True)
                self.qdrant_client = qdrant_client.QdrantClient(path=self.qdrant_path)
                logger.info(f"Initialized local Qdrant at {self.qdrant_path}")

            # Create collection if it doesn't exist
            collections = self.qdrant_client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.config.qdrant.collection_name not in collection_names:
                self.qdrant_client.create_collection(
                    collection_name=self.config.qdrant.collection_name,
                    vectors_config=VectorParams(
                        size=self.config.openai.dimensions,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created Qdrant collection: {self.config.qdrant.collection_name}")

        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self.qdrant_client = None

    def _init_keyword_index(self) -> None:
        """Initialize legacy SQLite FTS5 keyword index."""
        try:
            # Create parent directory if needed
            Path(self.keyword_db_path).parent.mkdir(parents=True, exist_ok=True)

            self.keyword_conn = sqlite3.connect(self.keyword_db_path)
            self.keyword_conn.row_factory = sqlite3.Row

            # Create FTS5 table if it doesn't exist
            self.keyword_conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS keyword_index USING fts5(
                    doc_id UNINDEXED,
                    node_id UNINDEXED,
                    chunk_index UNINDEXED,
                    content,
                    metadata UNINDEXED,
                    content_hash UNINDEXED,
                    tokenize = 'porter'
                )
            """)
            self.keyword_conn.commit()
            logger.info(f"Initialized SQLite keyword index at {self.keyword_db_path}")

        except Exception as e:
            logger.error(f"Failed to initialize keyword index: {e}")
            self.keyword_conn = None

    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        index_types: IndexType = IndexType.BOTH,
    ) -> bool:
        """Add document to specified indexes."""
        try:
            # Create document
            doc = Document(text=content, doc_id=doc_id, metadata=metadata or {})

            # Split into chunks
            chunks = self.text_splitter.create_chunks(doc)

            # Ensure backend-specific metadata
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
                    # Generate embeddings
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
        try:
            success = True

            # Add to vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.qdrant_client:
                try:
                    # Generate embeddings
                    texts = [chunk.text for chunk in chunks]
                    embeddings = self.embedding_service.get_text_embedding_batch(texts)

                    # Create points for Qdrant
                    points = []
                    for i, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=False)):
                        # Ensure required metadata
                        chunk.metadata["doc_id"] = doc_id
                        chunk.metadata["chunk_index"] = i

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
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.VECTOR,
                            node_id=chunk.id,
                            chunk_index=i,
                            content_hash=chunk.hash,
                            metadata=chunk.metadata,
                        )

                    logger.info(
                        f"Added {len(chunks)} chunks to vector index for document {doc_id[:8]}"
                    )

                except Exception as e:
                    logger.error(f"Failed to add chunks to vector index: {e}")
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
                            f"Added {len(chunks)} chunks to keyword index for document {doc_id[:8]}"
                        )
                    else:
                        success = False

                except Exception as e:
                    logger.error(f"Failed to add chunks to keyword index: {e}")
                    success = False

            # Update registry if successful
            if success:
                self.registry.mark_indexed(doc_id, index_types, len(chunks))
            else:
                self.registry.update_document_state(
                    doc_id, DocumentState.CORRUPTED, "Failed to index chunks"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to add chunks for document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False

    def _keyword_index_chunks(self, chunks: list[TextChunk]) -> bool:
        """Index chunks for keyword search using either adapter or legacy SQLite."""
        if self.keyword_index:
            # Use DatabaseFactory adapter
            try:
                # Prepare data for adapter (it expects nodes)
                # Most adapters expect a list of nodes with specific structure
                nodes = []
                for chunk in chunks:
                    # Create a dict that mimics the expected structure
                    node_data = {
                        "id_": chunk.id,
                        "text": chunk.text,
                        "metadata": chunk.metadata,
                        "hash": chunk.hash,
                    }
                    nodes.append(node_data)

                # Call the adapter's index method
                if hasattr(self.keyword_index, "index_nodes"):
                    # Get doc_id from first chunk's metadata
                    doc_id = chunks[0].metadata.get("doc_id", "unknown")
                    source = chunks[0].metadata.get("source", "unknown")
                    pairs = []  # TODO: Extract actual pairs if needed

                    self.keyword_index.index_nodes(nodes, doc_id, source, pairs)
                    return True
                else:
                    logger.warning("Keyword index adapter does not support index_nodes")
                    return False
            except Exception as e:
                logger.error(f"Failed to index chunks with adapter: {e}")
                return False
        elif self.keyword_conn:
            # Use legacy SQLite FTS5
            try:
                for i, chunk in enumerate(chunks):
                    doc_id = chunk.metadata.get("doc_id", "unknown")
                    self.keyword_conn.execute(
                        """INSERT INTO keyword_index
                           (doc_id, node_id, chunk_index, content, metadata, content_hash)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (
                            doc_id,
                            chunk.id,
                            i,
                            chunk.text,
                            json.dumps(chunk.metadata),
                            chunk.hash,
                        ),
                    )
                self.keyword_conn.commit()
                return True
            except Exception as e:
                logger.error(f"Failed to index chunks with legacy SQLite: {e}")
                return False
        else:
            logger.warning("No keyword index available (neither adapter nor legacy SQLite)")
            return False

    async def search(
        self,
        query: str,
        search_type: str = "hybrid",
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """
        Unified search interface using the new query engine.

        Args:
            query: Search query
            search_type: "vector", "keyword", or "hybrid"
            top_k: Number of results
            filters: Optional filters
            **kwargs: Additional parameters for QueryRequest

        Returns:
            List of search results
        """
        request = QueryRequest(
            query=query, top_k=top_k, search_type=search_type, filters=filters, **kwargs
        )

        results = await self.query_engine.search(request)

        # Convert QueryResult objects to dicts for compatibility
        return [
            {
                "doc_id": r.doc_id,
                "chunk_id": r.chunk_id,
                "node_id": r.chunk_id,  # Alias for compatibility
                "score": r.score,
                "text": r.text,
                "content": r.text,  # Alias for compatibility
                "metadata": r.metadata,
                "source": r.source,
                "search_type": r.search_type,
                "backend": r.backend,
            }
            for r in results
        ]

    def search_vector(
        self, query: str, top_k: int = 10, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search vector index (synchronous wrapper)."""
        return asyncio.run(self.search(query, "vector", top_k, filters))

    def search_keyword(
        self,
        query: str,
        top_k: int = 10,
        filters: dict[str, Any] | None = None,
        doc_filter: list[str] | None = None,  # Backward compatibility
    ) -> list[dict[str, Any]]:
        """Search keyword index (synchronous wrapper)."""
        # Handle backward compatibility
        if doc_filter and not filters:
            filters = {"doc_ids": doc_filter}

        return asyncio.run(self.search(query, "keyword", top_k, filters))

    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filters: dict[str, Any] | None = None,
        fusion_method: str = "rrf",
    ) -> list[dict[str, Any]]:
        """Perform hybrid search (synchronous wrapper)."""
        return asyncio.run(
            self.search(
                query,
                "hybrid",
                top_k,
                filters,
                vector_weight=vector_weight,
                keyword_weight=keyword_weight,
                fusion_method=fusion_method,
            )
        )

    def remove_document(self, doc_id: str, index_types: IndexType = IndexType.BOTH) -> bool:
        """Remove document from specified indexes."""
        try:
            # Get all index entries for the document
            entries = self.registry.get_index_entries(doc_id)

            success = True

            # Remove from vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.qdrant_client:
                try:
                    # Get all chunk IDs for this document
                    vector_ids = [
                        entry.node_id for entry in entries if entry.index_type == IndexType.VECTOR
                    ]

                    if vector_ids:
                        # Delete from Qdrant
                        self.qdrant_client.delete(
                            collection_name=self.config.qdrant.collection_name,
                            points_selector=vector_ids,
                        )

                        logger.info(
                            f"Removed {len(vector_ids)} chunks from vector index for document {doc_id[:8]}"
                        )

                except Exception as e:
                    logger.error(f"Failed to remove from vector index: {e}")
                    success = False

            # Remove from keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH]:
                try:
                    removed_count = self._keyword_remove_document(doc_id)
                    logger.info(
                        f"Removed {removed_count} chunks from keyword index for document {doc_id[:8]}"
                    )
                except Exception as e:
                    logger.error(f"Failed to remove from keyword index: {e}")
                    success = False

            # Update registry
            if success:
                self.registry.remove_document(doc_id)
            else:
                self.registry.update_document_state(
                    doc_id, DocumentState.CORRUPTED, "Failed to remove from indexes"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to remove document {doc_id}: {e}")
            return False

    def _keyword_remove_document(self, doc_id: str) -> int:
        """Remove document from keyword index using either adapter or legacy SQLite."""
        if self.keyword_index:
            # Use DatabaseFactory adapter
            try:
                # Assuming adapter has a remove_document method
                if hasattr(self.keyword_index, "remove_document"):
                    return self.keyword_index.remove_document(doc_id)
                elif hasattr(self.keyword_index, "delete_document"):
                    return self.keyword_index.delete_document(doc_id)
                else:
                    logger.warning("Keyword index adapter does not support document removal")
                    return 0
            except Exception as e:
                logger.error(f"Failed to remove document with adapter: {e}")
                return 0
        elif self.keyword_conn:
            # Use legacy SQLite
            try:
                cursor = self.keyword_conn.execute(
                    "DELETE FROM keyword_index WHERE doc_id = ?", (doc_id,)
                )
                deleted_count = cursor.rowcount
                self.keyword_conn.commit()
                return deleted_count
            except Exception as e:
                logger.error(f"Failed to remove document with legacy SQLite: {e}")
                return 0
        else:
            return 0

    def get_statistics(self) -> dict[str, Any]:
        """Get comprehensive index statistics."""
        stats = {
            "vector_index": self._get_vector_stats(),
            "keyword_index": self._get_keyword_stats(),
            "total_documents": len(
                {entry.doc_id for entry in self.registry.get_all_index_entries()}
            ),
        }
        return stats

    def _get_vector_stats(self) -> dict[str, Any]:
        """Get vector index statistics."""
        if not self.qdrant_client:
            return {"status": "not_initialized"}

        try:
            collection_info = self.qdrant_client.get_collection(self.config.qdrant.collection_name)
            return {
                "status": "active",
                "vectors_count": collection_info.vectors_count,
                "points_count": collection_info.points_count,
                "indexed_vectors_count": getattr(
                    collection_info, "indexed_vectors_count", "unknown"
                ),
            }
        except Exception as e:
            logger.error(f"Failed to get vector stats: {e}")
            return {"status": "error", "error": str(e)}

    def _get_keyword_stats(self) -> dict[str, Any]:
        """Get keyword index statistics."""
        if self.keyword_index:
            # Use DatabaseFactory adapter
            try:
                if hasattr(self.keyword_index, "get_stats"):
                    return self.keyword_index.get_stats()
                else:
                    return {"status": "adapter_no_stats"}
            except Exception as e:
                logger.error(f"Failed to get stats with adapter: {e}")
                return {"status": "error", "error": str(e)}
        elif self.keyword_conn:
            # Use legacy SQLite
            try:
                cursor = self.keyword_conn.execute("SELECT COUNT(*) FROM keyword_index")
                entry_count = cursor.fetchone()[0]

                cursor = self.keyword_conn.execute(
                    "SELECT COUNT(DISTINCT doc_id) FROM keyword_index"
                )
                doc_count = cursor.fetchone()[0]

                return {
                    "status": "active",
                    "total_entries": entry_count,
                    "unique_documents": doc_count,
                }
            except Exception as e:
                logger.error(f"Failed to get stats with legacy SQLite: {e}")
                return {"status": "error", "error": str(e)}
        else:
            return {"status": "not_initialized"}

    def verify_consistency(self) -> dict[str, Any]:
        """Verify consistency between registry and indexes."""
        report = {
            "consistent": True,
            "issues": [],
            "stats": {
                "registry_documents": 0,
                "vector_documents": set(),
                "keyword_documents": set(),
            },
        }

        # Get all documents from registry
        registry_docs = self.registry.list_documents()
        report["stats"]["registry_documents"] = len(registry_docs)

        # Check each document
        for doc in registry_docs:
            doc_id = doc.doc_id

            # Check vector index
            if doc.vector_indexed:
                if not self._verify_vector_indexed(doc_id):
                    report["consistent"] = False
                    report["issues"].append(
                        f"Document {doc_id} marked as vector indexed but not found in vector store"
                    )
                else:
                    report["stats"]["vector_documents"].add(doc_id)

            # Check keyword index
            if doc.keyword_indexed:
                if not self._verify_keyword_indexed(doc_id):
                    report["consistent"] = False
                    report["issues"].append(
                        f"Document {doc_id} marked as keyword indexed but not found in keyword index"
                    )
                else:
                    report["stats"]["keyword_documents"].add(doc_id)

        # Convert sets to counts for JSON serialization
        report["stats"]["vector_documents"] = len(report["stats"]["vector_documents"])
        report["stats"]["keyword_documents"] = len(report["stats"]["keyword_documents"])

        return report

    def _verify_vector_indexed(self, doc_id: str) -> bool:
        """Verify document exists in vector index."""
        if not self.qdrant_client:
            return False

        try:
            # Search for points with this doc_id
            results = self.qdrant_client.scroll(
                collection_name=self.config.qdrant.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id),
                        )
                    ]
                ),
                limit=1,
            )

            return len(results[0]) > 0

        except Exception as e:
            logger.error(f"Failed to verify vector index for {doc_id}: {e}")
            return False

    def _verify_keyword_indexed(self, doc_id: str) -> bool:
        """Verify document exists in keyword index."""
        if self.keyword_index:
            # Use DatabaseFactory adapter
            try:
                results = self.keyword_index.search("*", top_k=1, filters={"doc_id": doc_id})
                return len(results) > 0
            except Exception:
                return False
        elif self.keyword_conn:
            # Use legacy SQLite
            try:
                cursor = self.keyword_conn.execute(
                    "SELECT COUNT(*) FROM keyword_index WHERE doc_id = ?", (doc_id,)
                )
                count = cursor.fetchone()[0]
                return count > 0
            except Exception:
                return False
        else:
            return False

    def repair_consistency(self, dry_run: bool = True) -> dict[str, Any]:
        """Repair consistency issues between registry and indexes."""
        report = self.verify_consistency()

        if report["consistent"]:
            return {"status": "no_issues", "report": report}

        repairs = {
            "dry_run": dry_run,
            "actions": [],
        }

        # For now, just report what would be done
        for issue in report["issues"]:
            if "not found in vector store" in issue:
                doc_id = issue.split()[1]
                action = f"Would mark document {doc_id} as not vector indexed"
                repairs["actions"].append(action)

                if not dry_run:
                    # Actually update the registry
                    self.registry.update_index_status(doc_id, IndexType.VECTOR, False)

            elif "not found in keyword index" in issue:
                doc_id = issue.split()[1]
                action = f"Would mark document {doc_id} as not keyword indexed"
                repairs["actions"].append(action)

                if not dry_run:
                    # Actually update the registry
                    self.registry.update_index_status(doc_id, IndexType.KEYWORD, False)

        return repairs
