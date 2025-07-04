"""
Unit tests for IndexManager server mode compatibility.

Tests all methods that were identified as potentially problematic with
Qdrant server mode to ensure proper operation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
from pathlib import Path
import sys

# Add parent directories to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from core.index_manager import IndexManager, IndexType
from utils.config import PipelineConfig
from llama_index.core.schema import TextNode


class TestIndexManagerServerMode:
    """Test IndexManager methods for server mode compatibility."""

    @pytest.fixture
    def server_config(self):
        """Create config with server mode."""
        config = PipelineConfig()
        config.qdrant.mode = "server"
        config.qdrant.server.host = "localhost"
        config.qdrant.server.port = 6333
        return config

    @pytest.fixture
    def local_config(self):
        """Create config with local mode."""
        config = PipelineConfig()
        config.qdrant.mode = "local"
        return config

    @patch('core.index_manager.qdrant_client.QdrantClient')
    @patch('core.index_manager.QdrantVectorStore')
    def test_delete_from_vector_index_server_mode(self, mock_vector_store_class, mock_qdrant_client_class, server_config):
        """Test delete_from_vector_index uses direct client in server mode."""
        # Mock setup
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create manager
        manager = IndexManager(server_config)
        manager.qdrant_client = mock_client
        manager.vector_store = mock_vector_store

        # Test async delete
        import asyncio
        doc_id = "test_doc_123"
        result = asyncio.run(manager.delete_from_vector_index(doc_id))

        # Verify direct client was used
        from qdrant_client.models import FilterSelector, Filter, FieldCondition, MatchValue
        mock_client.delete.assert_called_once_with(
            collection_name=server_config.qdrant.collection_name,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[
                        FieldCondition(
                            key="doc_id",
                            match=MatchValue(value=doc_id)
                        )
                    ]
                )
            ),
        )

        # Verify LlamaIndex delete was NOT called
        mock_vector_store.delete.assert_not_called()

        assert result is True

    @patch('core.index_manager.qdrant_client.QdrantClient')
    @patch('core.index_manager.QdrantVectorStore')
    def test_delete_from_vector_index_local_mode(self, mock_vector_store_class, mock_qdrant_client_class, local_config):
        """Test delete_from_vector_index uses LlamaIndex in local mode."""
        # Mock setup
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create manager
        manager = IndexManager(local_config)
        manager.vector_store = mock_vector_store

        # Test async delete
        import asyncio
        doc_id = "test_doc_456"
        result = asyncio.run(manager.delete_from_vector_index(doc_id))

        # Verify LlamaIndex delete was called
        mock_vector_store.delete.assert_called_once_with(doc_id)

        assert result is True

    @patch('core.index_manager.OpenAIEmbedding')
    @patch('core.index_manager.VectorStoreIndex')
    @patch('core.index_manager.StorageContext')
    @patch('core.index_manager.qdrant_client.QdrantClient')
    @patch('core.index_manager.QdrantVectorStore')
    def test_add_nodes_metadata_handling(self, mock_vector_store_class, mock_qdrant_client_class,
                                       mock_storage_context, mock_vector_index, mock_embedding, server_config):
        """Test add_nodes properly handles metadata in server mode."""
        # Mock setup
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        mock_storage_context.from_defaults.return_value = Mock()

        # Create manager
        manager = IndexManager(server_config)

        # Create test nodes with metadata
        doc_id = "test_doc_789"
        nodes = [
            TextNode(
                text=f"Test content {i}",
                id_=f"node_{i}",
                metadata={
                    "doc_id": doc_id,
                    "chunk_index": i,
                    "custom": f"value_{i}"
                }
            )
            for i in range(3)
        ]

        # Test add_nodes
        success = manager.add_nodes(doc_id, nodes, IndexType.VECTOR)

        # Verify VectorStoreIndex was called with nodes
        mock_vector_index.assert_called_once()
        index_call_args = mock_vector_index.call_args[0]
        assert len(index_call_args[0]) == 3  # 3 nodes

        # Verify nodes passed have correct metadata
        for i, node in enumerate(index_call_args[0]):
            assert node.metadata.get("doc_id") == doc_id
            assert node.metadata.get("chunk_index") == i

        assert success is True

    @patch('core.index_manager.qdrant_client.QdrantClient')
    @patch('core.index_manager.QdrantVectorStore')
    def test_search_vector_result_handling(self, mock_vector_store_class, mock_qdrant_client_class, server_config):
        """Test search_vector handles different result structures."""
        # Mock setup
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create manager
        manager = IndexManager(server_config)
        manager.vector_store = mock_vector_store

        # Mock embedding model
        mock_embed_model = Mock()
        mock_embed_model.get_text_embedding.return_value = [0.1] * 1536
        manager.embedding_model = mock_embed_model

        # Test Case 1: Results with .nodes attribute
        mock_result_with_nodes = Mock()
        mock_nodes = [
            Mock(
                node_id="node_1",
                score=0.9,
                text="Test content 1",
                metadata={"doc_id": "doc_1"},
                id_="node_1"
            )
        ]
        mock_result_with_nodes.nodes = mock_nodes
        mock_vector_store.query.return_value = mock_result_with_nodes

        results = manager.search_vector("test query", top_k=5)

        assert len(results) == 1
        assert results[0]["node_id"] == "node_1"
        assert results[0]["score"] == 0.9
        assert results[0]["content"] == "Test content 1"

        # Test Case 2: Results as list
        mock_vector_store.query.return_value = mock_nodes

        results = manager.search_vector("test query", top_k=5)

        assert len(results) == 1
        assert results[0]["node_id"] == "node_1"

        # Test Case 3: Unexpected result type
        mock_vector_store.query.return_value = "unexpected"

        results = manager.search_vector("test query", top_k=5)

        assert results == []  # Should return empty list on error

    @patch('core.index_manager.qdrant_client.QdrantClient')
    @patch('core.index_manager.QdrantVectorStore')
    def test_remove_document_both_modes(self, mock_vector_store_class, mock_qdrant_client_class):
        """Test remove_document works correctly in both server and local modes."""
        # Test data
        doc_id = "test_doc_removal"
        mock_entries = [
            Mock(index_type=IndexType.VECTOR.value),
            Mock(index_type=IndexType.KEYWORD.value)
        ]

        # Test server mode
        server_config = PipelineConfig()
        server_config.qdrant.mode = "server"

        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        manager = IndexManager(server_config)
        manager.qdrant_client = mock_client
        manager.vector_store = mock_vector_store
        manager.registry.get_index_entries = Mock(return_value=mock_entries)
        manager.registry.remove_index_entries = Mock(return_value=True)

        # Mock keyword connection
        mock_cursor = Mock()
        mock_cursor.rowcount = 1
        manager.keyword_conn = Mock()
        manager.keyword_conn.execute.return_value = mock_cursor

        # Test removal in server mode
        success = manager.remove_document(doc_id, IndexType.BOTH)

        # Verify server mode uses direct client
        mock_client.delete.assert_called_once()
        mock_vector_store.delete.assert_not_called()

        assert success is True

        # Reset mocks
        mock_client.reset_mock()
        mock_vector_store.reset_mock()

        # Test local mode
        local_config = PipelineConfig()
        local_config.qdrant.mode = "local"

        manager_local = IndexManager(local_config)
        manager_local.vector_store = mock_vector_store
        manager_local.registry.get_index_entries = Mock(return_value=mock_entries)
        manager_local.registry.remove_index_entries = Mock(return_value=True)
        manager_local.keyword_conn = manager.keyword_conn

        # Test removal in local mode
        success = manager_local.remove_document(doc_id, IndexType.BOTH)

        # Verify local mode uses LlamaIndex
        mock_vector_store.delete.assert_called_once_with(doc_id)

        assert success is True

    @patch('src.pipeline_v3.core.index_manager.qdrant_client.QdrantClient')
    def test_get_document_chunks_limitation(self, mock_qdrant_client_class, server_config):
        """Test get_document_chunks acknowledges server mode limitations."""
        # This test verifies the known limitation that content retrieval
        # from vector store is not fully implemented

        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        manager = IndexManager(server_config)

        # Mock registry entries
        mock_entries = [
            Mock(node_id="node_1", chunk_index=0, content_hash="hash1", metadata={}),
            Mock(node_id="node_2", chunk_index=1, content_hash="hash2", metadata={})
        ]
        manager.registry.get_index_entries = Mock(return_value=mock_entries)

        # Get chunks from vector index
        chunks = manager.get_document_chunks("test_doc", IndexType.VECTOR)

        # Verify we get metadata but no actual content
        assert len(chunks) == 2
        for chunk in chunks:
            assert "node_id" in chunk
            assert "content" not in chunk or chunk["content"] == ""  # No content retrieval
            assert chunk["source"] == "vector"
