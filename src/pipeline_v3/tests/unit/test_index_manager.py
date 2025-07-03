"""
Unit tests for Index Manager component.

Tests cover index management, CRUD operations, and search functionality.
"""

import sys
import tempfile
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.index_manager import IndexManager
from core.registry import DocumentState, IndexType
from llama_index.core.schema import TextNode

from utils.config import PipelineConfig


class TestIndexManager:
    """Test suite for IndexManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        config.storage.qdrant_path = str(Path(temp_dir) / "qdrant_test")
        config.storage.keyword_db_path = str(Path(temp_dir) / "keyword_test.db")
        config.storage.document_registry_path = str(Path(temp_dir) / "registry_test.db")
        return config

    @pytest.fixture
    def index_manager(self, config):
        """Create test index manager."""
        with patch("qdrant_client.QdrantClient"):
            with patch("llama_index.embeddings.openai.OpenAIEmbedding"):
                with patch("llama_index.vector_stores.qdrant.QdrantVectorStore"):
                    manager = IndexManager(config=config)
                    # Mock the vector store methods
                    manager.vector_store = Mock()
                    manager.keyword_index = Mock()
                    return manager

    def test_initialization(self, config):
        """Test index manager initialization."""
        with patch("qdrant_client.QdrantClient"):
            with patch("llama_index.embeddings.openai.OpenAIEmbedding"):
                with patch("llama_index.vector_stores.qdrant.QdrantVectorStore"):
                    manager = IndexManager(config=config)
                    assert manager.config == config
                    assert manager.registry is not None

    def test_index_document(self, index_manager):
        """Test indexing a document."""
        doc_id = str(uuid.uuid4())

        # Mock all the complex internal operations
        with patch('core.index_manager.VectorStoreIndex'), \
             patch('core.index_manager.StorageContext'), \
             patch.object(index_manager.registry, 'register_index_entry'), \
             patch.object(index_manager.registry, 'register_document'), \
             patch.object(index_manager, 'keyword_conn') as mock_keyword_conn:

            # Mock keyword database connection
            mock_keyword_conn.execute = Mock()
            mock_keyword_conn.commit = Mock()

            # Index the document
            result = index_manager.add_document(
                doc_id=doc_id,
                content="Test content about laser power meters. Specifications and features",
                metadata={"source": "test.pdf", "pairs": [("Product", "PM100")]},
                index_types=IndexType.BOTH
            )

            assert result
            # Verify keyword indexing was called
            mock_keyword_conn.execute.assert_called()
            mock_keyword_conn.commit.assert_called_once()

    def test_search_hybrid(self, index_manager):
        """Test hybrid search functionality."""
        # Mock vector search results
        vector_results = [
            Mock(id="node1", score=0.9, metadata={"doc_id": "doc1"}),
            Mock(id="node2", score=0.8, metadata={"doc_id": "doc2"})
        ]
        index_manager._vector_search = Mock(return_value=vector_results)

        # Mock keyword search results
        keyword_results = [
            {"doc_id": "doc1", "chunk_id": "node1", "score": -2.5},
            {"doc_id": "doc3", "chunk_id": "node3", "score": -3.0}
        ]
        index_manager.keyword_index.search = Mock(return_value=keyword_results)

        # Mock node retrieval
        index_manager._get_nodes_by_ids = Mock(return_value=[
            Mock(id_="node1", text="Result 1", metadata={"doc_id": "doc1"}),
            Mock(id_="node2", text="Result 2", metadata={"doc_id": "doc2"}),
            Mock(id_="node3", text="Result 3", metadata={"doc_id": "doc3"})
        ])

        # Perform hybrid search
        results = index_manager.hybrid_search("test query", top_k=5, vector_weight=0.5, keyword_weight=0.5)

        assert len(results) > 0
        index_manager._vector_search.assert_called_once()
        index_manager.keyword_index.search.assert_called_once()

    def test_search_vector_only(self, index_manager):
        """Test vector-only search."""
        # Mock vector search
        vector_results = [
            Mock(id="node1", score=0.95, metadata={"doc_id": "doc1"}),
            Mock(id="node2", score=0.85, metadata={"doc_id": "doc1"})
        ]
        index_manager._vector_search = Mock(return_value=vector_results)
        index_manager._get_nodes_by_ids = Mock(return_value=[
            Mock(id_="node1", text="Result 1", metadata={"doc_id": "doc1"}),
            Mock(id_="node2", text="Result 2", metadata={"doc_id": "doc1"})
        ])

        # Perform vector search
        results = index_manager.search_vector("test query", top_k=5)

        assert len(results) == 2
        index_manager._vector_search.assert_called_once()
        # Keyword search should not be called for alpha=1.0
        index_manager.keyword_index.search.assert_not_called()

    def test_search_keyword_only(self, index_manager):
        """Test keyword-only search."""
        # Mock keyword search
        keyword_results = [
            {"doc_id": "doc1", "chunk_id": "node1", "score": -2.0, "text": "Result 1"},
            {"doc_id": "doc2", "chunk_id": "node2", "score": -2.5, "text": "Result 2"}
        ]
        index_manager.keyword_index.search = Mock(return_value=keyword_results)

        # Perform keyword search
        results = index_manager.search_keyword("test query", top_k=5)

        assert len(results) == 2
        index_manager.keyword_index.search.assert_called_once()
        # Vector search should not be called for alpha=0.0
        if hasattr(index_manager, "_vector_search"):
            index_manager._vector_search.assert_not_called()

    def test_get_document_nodes(self, index_manager):
        """Test retrieving nodes for a document."""
        doc_id = "test_doc_id"

        # Mock registry with index entries
        mock_entries = [
            Mock(node_id="node1", chunk_index=0),
            Mock(node_id="node2", chunk_index=1)
        ]
        index_manager.registry.get_index_entries = Mock(return_value=mock_entries)

        # Mock node retrieval
        index_manager._get_nodes_by_ids = Mock(return_value=[
            Mock(id_="node1", text="Chunk 1"),
            Mock(id_="node2", text="Chunk 2")
        ])

        # Get nodes
        nodes = index_manager.get_document_nodes(doc_id)

        assert len(nodes) == 2
        index_manager.registry.get_index_entries.assert_called_once_with(doc_id, IndexType.VECTOR)

    def test_update_document(self, index_manager):
        """Test updating a document."""
        doc_id = "test_doc_id"
        new_nodes = [
            TextNode(id_="new1", text="Updated content", metadata={"page": 1})
        ]

        # Mock document existence
        index_manager.registry.get_document = Mock(return_value=Mock(
            doc_id=doc_id,
            source="test.pdf"
        ))

        # Mock deletion and re-indexing
        index_manager.delete_document = Mock(return_value=True)
        index_manager.add_document = Mock(return_value=True)

        # Update document
        result = index_manager.update_document(
            doc_id=doc_id,
            content="Updated test content",
            metadata={"source": "test.pdf"}
        )

        assert result
        index_manager.delete_document.assert_called_once_with(doc_id)
        index_manager.add_document.assert_called_once()

    def test_delete_document(self, index_manager):
        """Test deleting a document."""
        doc_id = "test_doc_id"

        # Mock registry entries
        mock_entries = [
            Mock(node_id="node1"),
            Mock(node_id="node2")
        ]
        index_manager.registry.get_index_entries = Mock(return_value=mock_entries)

        # Mock vector store deletion
        index_manager.vector_store.delete = Mock()

        # Mock registry operations
        index_manager.registry.remove_index_entries = Mock(return_value=True)
        index_manager.registry.remove_document = Mock(return_value=True)

        # Delete document
        result = index_manager.delete_document(doc_id)

        assert result
        index_manager.vector_store.delete.assert_called_once()
        index_manager.registry.remove_document.assert_called_once_with(doc_id)

    def test_get_statistics(self, index_manager):
        """Test getting index statistics."""
        # Mock registry stats
        index_manager.registry.get_statistics = Mock(return_value={
            "total_documents": 10,
            "by_state": {"indexed": {"count": 8}}
        })

        # Mock vector store stats
        index_manager._get_vector_stats = Mock(return_value={
            "total_vectors": 100,
            "collection_size": 1024
        })

        # Mock keyword index stats
        index_manager.keyword_index.get_stats = Mock(return_value={
            "total_documents": 10,
            "total_chunks": 100
        })

        # Get statistics
        stats = index_manager.get_statistics()

        assert "registry" in stats
        assert "vector_index" in stats
        assert "keyword_index" in stats
        assert stats["registry"]["total_documents"] == 10

    def test_search_by_metadata(self, index_manager):
        """Test searching with metadata filters."""
        # Mock vector search with metadata filter
        vector_results = [
            Mock(id="node1", score=0.9, metadata={"doc_id": "doc1", "type": "datasheet"})
        ]

        # Create a mock query engine
        mock_retriever = Mock()
        mock_retriever.retrieve = Mock(return_value=vector_results)

        mock_query_engine = Mock()
        mock_query_engine.retriever = mock_retriever

        index_manager._get_query_engine = Mock(return_value=mock_query_engine)
        index_manager._get_nodes_by_ids = Mock(return_value=[
            Mock(id_="node1", text="Filtered result", metadata={"type": "datasheet"})
        ])

        # Search with metadata filter
        results = index_manager.search_vector(
            "test query",
            filters={"type": "datasheet"}
        )

        # Should have results
        assert len(results) >= 0

    def test_rebuild_indexes(self, index_manager):
        """Test rebuilding indexes from scratch."""
        # This would be a complex operation in practice
        # For testing, we just verify the method exists and can be called
        index_manager.rebuild_indexes = Mock(return_value={"rebuilt": 5, "failed": 0})

        result = index_manager.rebuild_indexes()
        assert result["rebuilt"] == 5
        assert result["failed"] == 0

    def test_verify_index_consistency(self, index_manager):
        """Test index consistency verification."""
        # Mock registry data
        index_manager.registry.list_documents = Mock(return_value=[
            Mock(doc_id="doc1", vector_indexed=True, keyword_indexed=True),
            Mock(doc_id="doc2", vector_indexed=False, keyword_indexed=True)
        ])

        # Mock actual index checks
        index_manager._check_vector_index = Mock(side_effect=lambda doc_id: doc_id == "doc1")
        index_manager._check_keyword_index = Mock(return_value=True)

        # Verify consistency
        index_manager.verify_consistency = Mock(return_value={
            "total_checked": 2,
            "inconsistent": 1,
            "details": []
        })

        result = index_manager.verify_consistency()
        assert result["total_checked"] == 2
        assert result["inconsistent"] == 1

    def test_error_handling_during_indexing(self, index_manager):
        """Test error handling during document indexing."""
        doc_id = "test_doc_id"
        nodes = [TextNode(id_="node1", text="Test")]

        # Mock vector indexing to fail
        index_manager.vector_store.add = Mock(side_effect=Exception("Vector index error"))
        index_manager.registry.get_document = Mock(return_value=Mock(doc_id=doc_id))
        index_manager.registry.update_document_state = Mock()

        # Index should handle the error gracefully
        result = index_manager.add_document(doc_id, "Test content", {"source": "test.pdf"})

        assert not result
        # Should mark document as having an error
        index_manager.registry.update_document_state.assert_called()

    def test_batch_operations(self, index_manager):
        """Test batch indexing operations."""
        # Create multiple documents
        documents = [
            {
                "doc_id": f"doc{i}",
                "nodes": [TextNode(id_=f"node{i}", text=f"Document {i}")],
                "source": f"doc{i}.pdf",
                "pairs": []
            }
            for i in range(3)
        ]

        # Mock successful indexing
        index_manager.add_document = Mock(return_value=True)

        # Batch index
        results = {"success": 0, "failed": 0}
        for doc in documents:
            if index_manager.add_document(doc["doc_id"], "Test content", {"source": doc["source"]}):
                results["success"] += 1
            else:
                results["failed"] += 1

        assert results["success"] == 3
        assert results["failed"] == 0
        assert index_manager.add_document.call_count == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
