"""
Index Manager - Phase 2 Implementation

Advanced index lifecycle management with CRUD operations for vector and keyword indexes.
Provides consistent operations across Qdrant vector store and SQLite BM25 keyword index.
"""

import asyncio
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

try:
    from llama_index.core import Document, VectorStoreIndex, StorageContext, Settings
    from llama_index.core.node_parser import SentenceSplitter
    from llama_index.core.schema import TextNode
    from llama_index.embeddings.openai import OpenAIEmbedding
    from llama_index.vector_stores.qdrant import QdrantVectorStore
    import qdrant_client
    LLAMA_INDEX_AVAILABLE = True
except ImportError:
    LLAMA_INDEX_AVAILABLE = False

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from core.registry import DocumentRegistry, DocumentState, IndexType, IndexRecord
from utils.common_utils import logger
from utils.config import PipelineConfig


class IndexManager:
    """Advanced index lifecycle management for vector and keyword indexes."""
    
    def __init__(self, config: Optional[PipelineConfig] = None, registry: Optional[DocumentRegistry] = None):
        """Initialize index manager with configuration."""
        self.config = config or PipelineConfig()
        
        # Use provided registry or create new one
        self.registry = registry or DocumentRegistry(config)
        
        # Storage paths
        self.qdrant_path = self.config.qdrant.path
        self.keyword_db_path = self.config.storage.keyword_db_path
        
        # Initialize components
        self._init_qdrant()
        self._init_keyword_index()
        self._init_embeddings()
        self._init_text_splitter()
        
        logger.info(f"IndexManager initialized with Qdrant: {self.qdrant_path}")
    
    def _init_qdrant(self) -> None:
        """Initialize Qdrant vector store."""
        if not LLAMA_INDEX_AVAILABLE:
            logger.warning("LlamaIndex not available - vector operations disabled")
            self.qdrant_client = None
            self.vector_store = None
            return
        
        try:
            # Create Qdrant client
            self.qdrant_client = qdrant_client.QdrantClient(path=self.qdrant_path)
            
            # Initialize vector store
            self.vector_store = QdrantVectorStore(
                client=self.qdrant_client,
                collection_name=self.config.qdrant.collection_name,
                enable_hybrid=False
            )
            
            logger.info(f"Qdrant vector store initialized: {self.config.qdrant.collection_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant: {e}")
            self.qdrant_client = None
            self.vector_store = None
    
    def _init_keyword_index(self) -> None:
        """Initialize SQLite-based keyword index."""
        try:
            Path(self.keyword_db_path).parent.mkdir(parents=True, exist_ok=True)
            
            self.keyword_conn = sqlite3.connect(self.keyword_db_path)
            
            # Create keyword index table with FTS5
            self.keyword_conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS keyword_index 
                USING fts5(
                    doc_id UNINDEXED,
                    node_id UNINDEXED,
                    chunk_index UNINDEXED,
                    content,
                    metadata UNINDEXED,
                    content_hash UNINDEXED
                )
            """)
            
            self.keyword_conn.commit()
            logger.info(f"Keyword index initialized: {self.keyword_db_path}")
            
        except Exception as e:
            logger.error(f"Failed to initialize keyword index: {e}")
            self.keyword_conn = None
    
    def _init_embeddings(self) -> None:
        """Initialize OpenAI embeddings."""
        if not LLAMA_INDEX_AVAILABLE:
            self.embedding_model = None
            return
        
        try:
            self.embedding_model = OpenAIEmbedding(
                model=self.config.openai.embedding_model,
                dimensions=self.config.openai.dimensions
            )
            
            # Set the embedding model in global Settings
            Settings.embed_model = self.embedding_model
            
            logger.info(f"Embeddings initialized: {self.config.openai.embedding_model}")
            
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            self.embedding_model = None
    
    def _init_text_splitter(self) -> None:
        """Initialize text splitter for chunking."""
        if not LLAMA_INDEX_AVAILABLE:
            self.text_splitter = None
            return
        
        try:
            self.text_splitter = SentenceSplitter(
                chunk_size=self.config.chunking.chunk_size,
                chunk_overlap=self.config.chunking.chunk_overlap
            )
            logger.info(f"Text splitter initialized: {self.config.chunking.chunk_size} chars")
            
        except Exception as e:
            logger.error(f"Failed to initialize text splitter: {e}")
            self.text_splitter = None
    
    def add_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        index_types: IndexType = IndexType.BOTH
    ) -> bool:
        """Add document to specified indexes."""
        try:
            if not LLAMA_INDEX_AVAILABLE:
                logger.error("LlamaIndex not available - cannot add document")
                return False
            
            # Create document
            doc = Document(
                text=content,
                doc_id=doc_id,
                metadata=metadata or {}
            )
            
            # Split into chunks
            nodes = self.text_splitter.get_nodes_from_documents([doc])
            
            success = True
            
            # Add to vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.vector_store:
                try:
                    # Create storage context with the vector store
                    storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
                    
                    # Index nodes - this generates embeddings and stores them
                    index = VectorStoreIndex(nodes, storage_context=storage_context)
                    
                    # Register index entries
                    for i, node in enumerate(nodes):
                        logger.debug(f"Registering vector index entry: doc_id={doc_id}, node_id={node.node_id}")
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.VECTOR,
                            node_id=node.node_id,
                            chunk_index=i,
                            content_hash=node.hash,
                            metadata=node.metadata
                        )
                    
                    logger.info(f"Added document {doc_id[:8]} to vector index ({len(nodes)} chunks)")
                    
                except Exception as e:
                    logger.error(f"Failed to add to vector index: {e}")
                    success = False
            
            # Add to keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH] and self.keyword_conn:
                try:
                    for i, node in enumerate(nodes):
                        self.keyword_conn.execute("""
                            INSERT INTO keyword_index 
                            (doc_id, node_id, chunk_index, content, metadata, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            doc_id,
                            node.node_id,
                            i,
                            node.text,
                            str(node.metadata),
                            node.hash
                        ))
                        
                        # Register index entry
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.KEYWORD,
                            node_id=node.node_id,
                            chunk_index=i,
                            content_hash=node.hash,
                            metadata=node.metadata
                        )
                    
                    self.keyword_conn.commit()
                    logger.info(f"Added document {doc_id[:8]} to keyword index ({len(nodes)} chunks)")
                    
                except Exception as e:
                    logger.error(f"Failed to add to keyword index: {e}")
                    success = False
            
            # Update registry if successful
            if success:
                self.registry.mark_indexed(doc_id, index_types, len(nodes))
            else:
                self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, "Failed to index")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to add document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False
    
    def add_nodes(
        self,
        doc_id: str,
        nodes: List[TextNode],
        index_types: IndexType = IndexType.BOTH
    ) -> bool:
        """Add pre-processed nodes to specified indexes.
        
        This method is used when nodes have already been processed with
        keyword enhancement or other transformations.
        
        Args:
            doc_id: Document identifier
            nodes: Pre-processed TextNode objects
            index_types: Which indexes to update
            
        Returns:
            Success status
        """
        try:
            if not LLAMA_INDEX_AVAILABLE:
                logger.error("LlamaIndex not available - cannot add nodes")
                return False
            
            if not nodes:
                logger.warning(f"No nodes provided for document {doc_id}")
                return False
            
            success = True
            
            # Add to vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.vector_store:
                try:
                    # Create storage context with the vector store
                    storage_context = StorageContext.from_defaults(vector_store=self.vector_store)
                    
                    # Index nodes - this generates embeddings and stores them
                    index = VectorStoreIndex(nodes, storage_context=storage_context)
                    
                    # Register index entries
                    for i, node in enumerate(nodes):
                        logger.debug(f"Registering vector index entry: doc_id={doc_id}, node_id={node.node_id}")
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.VECTOR,
                            node_id=node.node_id,
                            chunk_index=i,
                            content_hash=node.hash,
                            metadata=node.metadata
                        )
                    
                    logger.info(f"Added document {doc_id[:8]} to vector index ({len(nodes)} chunks)")
                    
                except Exception as e:
                    logger.error(f"Failed to add nodes to vector index: {e}")
                    success = False
            
            # Add to keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH] and self.keyword_conn:
                try:
                    for i, node in enumerate(nodes):
                        self.keyword_conn.execute("""
                            INSERT INTO keyword_index 
                            (doc_id, node_id, chunk_index, content, metadata, content_hash)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            doc_id,
                            node.node_id,
                            i,
                            node.text,
                            str(node.metadata),
                            node.hash
                        ))
                        
                        # Register index entry
                        self.registry.register_index_entry(
                            doc_id=doc_id,
                            index_type=IndexType.KEYWORD,
                            node_id=node.node_id,
                            chunk_index=i,
                            content_hash=node.hash,
                            metadata=node.metadata
                        )
                    
                    self.keyword_conn.commit()
                    logger.info(f"Added document {doc_id[:8]} to keyword index ({len(nodes)} chunks)")
                    
                except Exception as e:
                    logger.error(f"Failed to add nodes to keyword index: {e}")
                    success = False
            
            # Update registry if successful
            if success:
                self.registry.mark_indexed(doc_id, index_types, len(nodes))
            else:
                self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, "Failed to index nodes")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to add nodes for document {doc_id}: {e}")
            self.registry.update_document_state(doc_id, DocumentState.CORRUPTED, str(e))
            return False
    
    def update_document(
        self,
        doc_id: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        index_types: IndexType = IndexType.BOTH
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
    
    def remove_document(
        self,
        doc_id: str,
        index_types: IndexType = IndexType.BOTH
    ) -> bool:
        """Remove document from specified indexes."""
        try:
            success = True
            
            # Get existing index entries
            entries = self.registry.get_index_entries(doc_id)
            
            # Remove from vector index
            if index_types in [IndexType.VECTOR, IndexType.BOTH] and self.vector_store:
                try:
                    vector_entries = [e for e in entries if e.index_type == IndexType.VECTOR.value]
                    if vector_entries:
                        node_ids = [e.node_id for e in vector_entries]
                        self.vector_store.delete(node_ids)
                        logger.info(f"Removed {len(node_ids)} vector entries for document {doc_id[:8]}")
                    
                except Exception as e:
                    logger.error(f"Failed to remove from vector index: {e}")
                    success = False
            
            # Remove from keyword index
            if index_types in [IndexType.KEYWORD, IndexType.BOTH] and self.keyword_conn:
                try:
                    cursor = self.keyword_conn.execute("""
                        DELETE FROM keyword_index WHERE doc_id = ?
                    """, (doc_id,))
                    
                    deleted_count = cursor.rowcount
                    self.keyword_conn.commit()
                    
                    if deleted_count > 0:
                        logger.info(f"Removed {deleted_count} keyword entries for document {doc_id[:8]}")
                    
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
        self,
        doc_id: str,
        index_type: IndexType = IndexType.VECTOR
    ) -> List[Dict[str, Any]]:
        """Get document chunks from specified index."""
        chunks = []
        
        try:
            if index_type == IndexType.VECTOR and self.vector_store:
                # Get from vector index via registry
                entries = self.registry.get_index_entries(doc_id, IndexType.VECTOR)
                
                for entry in entries:
                    # Note: Qdrant doesn't provide easy content retrieval by node_id
                    # This would need enhancement for full content retrieval
                    chunks.append({
                        "node_id": entry.node_id,
                        "chunk_index": entry.chunk_index,
                        "content_hash": entry.content_hash,
                        "metadata": entry.metadata,
                        "source": "vector"
                    })
                    
            elif index_type == IndexType.KEYWORD and self.keyword_conn:
                cursor = self.keyword_conn.execute("""
                    SELECT node_id, chunk_index, content, metadata, content_hash
                    FROM keyword_index WHERE doc_id = ?
                    ORDER BY chunk_index
                """, (doc_id,))
                
                for row in cursor.fetchall():
                    chunks.append({
                        "node_id": row[0],
                        "chunk_index": row[1],
                        "content": row[2],
                        "metadata": row[3],
                        "content_hash": row[4],
                        "source": "keyword"
                    })
            
        except Exception as e:
            logger.error(f"Failed to get chunks for document {doc_id}: {e}")
        
        return chunks
    
    def search_vector(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Search vector index."""
        if not self.vector_store or not self.embedding_model:
            logger.error("Vector search not available")
            return []
        
        try:
            # Create query embedding
            query_embedding = self.embedding_model.get_text_embedding(query)
            
            # Search vector store
            results = self.vector_store.query(
                query_embedding,
                similarity_top_k=top_k,
                filters=filters
            )
            
            search_results = []
            for result in results.nodes:
                search_results.append({
                    "node_id": result.node_id,
                    "score": getattr(result, 'score', 0.0),
                    "content": result.text,
                    "metadata": result.metadata,
                    "doc_id": result.metadata.get('doc_id')
                })
            
            return search_results
            
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []
    
    def search_keyword(
        self,
        query: str,
        top_k: int = 10,
        doc_filter: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search keyword index."""
        if not self.keyword_conn:
            logger.error("Keyword search not available")
            return []
        
        try:
            # Build query
            sql_query = """
                SELECT doc_id, node_id, chunk_index, content, metadata, 
                       bm25(keyword_index) as score
                FROM keyword_index 
                WHERE keyword_index MATCH ?
            """
            params = [query]
            
            # Add document filter if provided
            if doc_filter:
                placeholders = ",".join("?" * len(doc_filter))
                sql_query += f" AND doc_id IN ({placeholders})"
                params.extend(doc_filter)
            
            sql_query += " ORDER BY score LIMIT ?"
            params.append(top_k)
            
            cursor = self.keyword_conn.execute(sql_query, params)
            
            results = []
            for row in cursor.fetchall():
                results.append({
                    "doc_id": row[0],
                    "node_id": row[1],
                    "chunk_index": row[2],
                    "content": row[3],
                    "metadata": row[4],
                    "score": row[5]
                })
            
            return results
            
        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []
    
    def hybrid_search(
        self,
        query: str,
        top_k: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3
    ) -> List[Dict[str, Any]]:
        """Perform hybrid search combining vector and keyword results."""
        try:
            # Get results from both indexes
            vector_results = self.search_vector(query, top_k * 2)
            keyword_results = self.search_keyword(query, top_k * 2)
            
            # Normalize scores
            if vector_results:
                max_vector_score = max(r.get('score', 0) for r in vector_results)
                for result in vector_results:
                    result['normalized_score'] = (result.get('score', 0) / max_vector_score) * vector_weight
            
            if keyword_results:
                max_keyword_score = max(r.get('score', 0) for r in keyword_results)
                for result in keyword_results:
                    result['normalized_score'] = (result.get('score', 0) / max_keyword_score) * keyword_weight
            
            # Combine and deduplicate by node_id
            combined = {}
            
            for result in vector_results:
                node_id = result['node_id']
                combined[node_id] = result
                combined[node_id]['search_type'] = 'vector'
            
            for result in keyword_results:
                node_id = result['node_id']
                if node_id in combined:
                    # Combine scores
                    combined[node_id]['normalized_score'] += result['normalized_score']
                    combined[node_id]['search_type'] = 'hybrid'
                else:
                    combined[node_id] = result
                    combined[node_id]['search_type'] = 'keyword'
            
            # Sort by combined score and return top_k
            sorted_results = sorted(
                combined.values(),
                key=lambda x: x['normalized_score'],
                reverse=True
            )[:top_k]
            
            return sorted_results
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            return []
    
    def verify_consistency(self) -> Dict[str, Any]:
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
                vector_consistency.get('missing_nodes', 0) +
                vector_consistency.get('extra_nodes', 0) +
                keyword_consistency.get('missing_entries', 0) +
                keyword_consistency.get('extra_entries', 0) +
                registry_stats['consistency']['inconsistent_documents'] +
                registry_stats['consistency']['orphaned_entries']
            )
            
            health_score = max(0, 100 - (total_issues * 5))
            
            return {
                "registry": registry_stats,
                "vector_index": vector_consistency,
                "keyword_index": keyword_consistency,
                "overall_health": {
                    "score": health_score,
                    "total_issues": total_issues,
                    "status": "healthy" if health_score >= 90 else "degraded" if health_score >= 70 else "unhealthy"
                },
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Consistency check failed: {e}")
            return {"error": str(e)}
    
    def _check_vector_consistency(self) -> Dict[str, Any]:
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
                "consistent": vector_count == registry_count
            }
            
        except Exception as e:
            logger.error(f"Vector consistency check failed: {e}")
            return {"error": str(e)}
    
    def _check_keyword_consistency(self) -> Dict[str, Any]:
        """Check keyword index consistency."""
        try:
            if not self.keyword_conn:
                return {"error": "Keyword index not available"}
            
            # Get keyword index count
            cursor = self.keyword_conn.execute("SELECT COUNT(*) FROM keyword_index")
            keyword_count = cursor.fetchone()[0]
            
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
                "consistent": keyword_count == registry_count
            }
            
        except Exception as e:
            logger.error(f"Keyword consistency check failed: {e}")
            return {"error": str(e)}
    
    def repair_indexes(self) -> Dict[str, Any]:
        """Repair index inconsistencies."""
        try:
            repair_results = {
                "registry_cleanup": 0,
                "vector_repairs": 0,
                "keyword_repairs": 0,
                "errors": []
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
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get comprehensive index statistics."""
        try:
            stats = {
                "registry": self.registry.get_statistics(),
                "timestamp": time.time()
            }
            
            # Vector index stats
            if self.qdrant_client:
                try:
                    collection_info = self.qdrant_client.get_collection(self.config.qdrant.collection_name)
                    stats["vector_index"] = {
                        "points_count": collection_info.points_count,
                        "collection_name": self.config.qdrant.collection_name,
                        "status": "available"
                    }
                except Exception as e:
                    stats["vector_index"] = {"status": "error", "error": str(e)}
            else:
                stats["vector_index"] = {"status": "unavailable"}
            
            # Keyword index stats
            if self.keyword_conn:
                try:
                    cursor = self.keyword_conn.execute("SELECT COUNT(*) FROM keyword_index")
                    entry_count = cursor.fetchone()[0]
                    
                    cursor = self.keyword_conn.execute("SELECT COUNT(DISTINCT doc_id) FROM keyword_index")
                    doc_count = cursor.fetchone()[0]
                    
                    stats["keyword_index"] = {
                        "entry_count": entry_count,
                        "document_count": doc_count,
                        "status": "available"
                    }
                except Exception as e:
                    stats["keyword_index"] = {"status": "error", "error": str(e)}
            else:
                stats["keyword_index"] = {"status": "unavailable"}
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {"error": str(e)}
    
    def close(self) -> None:
        """Close database connections."""
        if hasattr(self, 'keyword_conn') and self.keyword_conn:
            self.keyword_conn.close()
            logger.debug("Keyword index connection closed")
        
        if hasattr(self, 'registry'):
            self.registry.close()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()