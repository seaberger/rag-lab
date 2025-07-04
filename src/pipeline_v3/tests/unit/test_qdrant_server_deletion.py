"""
Unit tests for Qdrant server mode chunk deletion.

Tests the fix for proper chunk deletion when documents are updated or removed
in Qdrant server mode.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add parent directories to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))
sys.path.append(str(Path(__file__).parent.parent.parent.parent))

from src.pipeline_v3.core.index_manager import IndexManager, IndexType
from src.pipeline_v3.utils.config import PipelineConfig


class TestQdrantServerDeletion:
    """Test Qdrant server mode deletion functionality."""

    @patch('src.pipeline_v3.core.index_manager.qdrant_client.QdrantClient')
    @patch('src.pipeline_v3.core.index_manager.QdrantVectorStore')
    def test_remove_document_server_mode(self, mock_vector_store_class, mock_qdrant_client_class):
        """Test that remove_document uses proper filter deletion in server mode."""
        # Create config with server mode
        config = PipelineConfig()
        config.qdrant.mode = "server"

        # Mock Qdrant client
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        # Mock vector store
        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create IndexManager
        manager = IndexManager(config)
        manager.qdrant_client = mock_client
        manager.vector_store = mock_vector_store

        # Mock registry entries
        mock_entries = [
            Mock(index_type=IndexType.VECTOR.value, node_id=f"node_{i}")
            for i in range(5)
        ]
        manager.registry.get_index_entries = Mock(return_value=mock_entries)
        manager.registry.remove_index_entries = Mock(return_value=True)

        # Test document removal
        doc_id = "test_doc_123"
        success = manager.remove_document(doc_id, IndexType.VECTOR)

        # Verify direct Qdrant client delete was called with proper filter
        mock_client.delete.assert_called_once_with(
            collection_name=config.qdrant.collection_name,
            points_selector={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                }
            },
        )

        # Verify LlamaIndex delete was NOT called
        mock_vector_store.delete.assert_not_called()

        assert success is True

    @patch('src.pipeline_v3.core.index_manager.qdrant_client.QdrantClient')
    @patch('src.pipeline_v3.core.index_manager.QdrantVectorStore')
    def test_remove_document_local_mode(self, mock_vector_store_class, mock_qdrant_client_class):
        """Test that remove_document uses LlamaIndex delete in local mode."""
        # Create config with local mode
        config = PipelineConfig()
        config.qdrant.mode = "local"

        # Mock Qdrant client
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        # Mock vector store
        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create IndexManager
        manager = IndexManager(config)
        manager.vector_store = mock_vector_store

        # Mock registry entries
        mock_entries = [
            Mock(index_type=IndexType.VECTOR.value, node_id=f"node_{i}")
            for i in range(3)
        ]
        manager.registry.get_index_entries = Mock(return_value=mock_entries)
        manager.registry.remove_index_entries = Mock(return_value=True)

        # Test document removal
        doc_id = "test_doc_456"
        success = manager.remove_document(doc_id, IndexType.VECTOR)

        # Verify LlamaIndex delete was called
        mock_vector_store.delete.assert_called_once_with(doc_id)

        assert success is True

    @patch('src.pipeline_v3.core.index_manager.qdrant_client.QdrantClient')
    @patch('src.pipeline_v3.core.index_manager.QdrantVectorStore')
    def test_remove_document_both_indexes(self, mock_vector_store_class, mock_qdrant_client_class):
        """Test removal from both vector and keyword indexes."""
        # Create config with server mode
        config = PipelineConfig()
        config.qdrant.mode = "server"

        # Mock Qdrant client
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_qdrant_client_class.return_value = mock_client

        # Mock vector store
        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create IndexManager
        manager = IndexManager(config)
        manager.qdrant_client = mock_client
        manager.vector_store = mock_vector_store

        # Mock keyword connection
        mock_keyword_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.rowcount = 3
        mock_keyword_conn.execute.return_value = mock_cursor
        manager.keyword_conn = mock_keyword_conn

        # Mock registry entries
        mock_entries = [
            Mock(index_type=IndexType.VECTOR.value, node_id="node_1"),
            Mock(index_type=IndexType.VECTOR.value, node_id="node_2"),
            Mock(index_type=IndexType.KEYWORD.value, node_id="node_1"),
            Mock(index_type=IndexType.KEYWORD.value, node_id="node_2"),
            Mock(index_type=IndexType.KEYWORD.value, node_id="node_3"),
        ]
        manager.registry.get_index_entries = Mock(return_value=mock_entries)
        manager.registry.remove_index_entries = Mock(return_value=True)

        # Test document removal from both indexes
        doc_id = "test_doc_789"
        success = manager.remove_document(doc_id, IndexType.BOTH)

        # Verify Qdrant deletion
        mock_client.delete.assert_called_once_with(
            collection_name=config.qdrant.collection_name,
            points_selector={
                "filter": {
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                }
            },
        )

        # Verify keyword index deletion
        mock_keyword_conn.execute.assert_called_once()
        sql_call = mock_keyword_conn.execute.call_args[0][0]
        assert "DELETE FROM keyword_index WHERE doc_id = ?" in sql_call
        assert mock_keyword_conn.execute.call_args[0][1] == (doc_id,)
        mock_keyword_conn.commit.assert_called_once()

        assert success is True

    @patch('src.pipeline_v3.core.index_manager.qdrant_client.QdrantClient')
    @patch('src.pipeline_v3.core.index_manager.QdrantVectorStore')
    def test_remove_document_error_handling(self, mock_vector_store_class, mock_qdrant_client_class):
        """Test error handling during document removal."""
        # Create config with server mode
        config = PipelineConfig()
        config.qdrant.mode = "server"

        # Mock Qdrant client that raises an error
        mock_client = Mock()
        mock_collections = Mock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections
        mock_client.delete.side_effect = Exception("Qdrant server error")
        mock_qdrant_client_class.return_value = mock_client

        # Mock vector store
        mock_vector_store = Mock()
        mock_vector_store_class.return_value = mock_vector_store

        # Create IndexManager
        manager = IndexManager(config)
        manager.qdrant_client = mock_client
        manager.vector_store = mock_vector_store

        # Mock registry entries
        mock_entries = [Mock(index_type=IndexType.VECTOR.value)]
        manager.registry.get_index_entries = Mock(return_value=mock_entries)

        # Test document removal with error
        doc_id = "test_doc_error"
        success = manager.remove_document(doc_id, IndexType.VECTOR)

        # Should return False on error
        assert success is False

        # Registry should not be updated on failure
        manager.registry.remove_index_entries.assert_not_called()
