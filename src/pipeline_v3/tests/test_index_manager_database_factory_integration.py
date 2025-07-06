"""
Test IndexManager DatabaseFactory Integration - Phase 4.2.1c
Tests that IndexManager properly uses DatabaseFactory keyword index adapter.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with proper module path handling
try:
    from core.index_manager import IndexManager
    from core.registry import IndexType
    from utils.config import PipelineConfig
except ImportError:
    # If direct import fails, try absolute import from project root
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.pipeline_v3.core.index_manager import IndexManager
    from src.pipeline_v3.core.registry import IndexType
    from src.pipeline_v3.utils.config import PipelineConfig


class TestIndexManagerIntegration:
    """Test IndexManager integration with DatabaseFactory keyword index adapter."""

    @pytest.fixture
    def sqlite_config(self):
        """Create test config with SQLite backend."""
        config = PipelineConfig()
        config.database.backend = "sqlite"
        return config

    @pytest.fixture
    def mock_keyword_index(self):
        """Create mock keyword index adapter that matches expected interfaces."""
        mock_keyword_index = MagicMock()
        mock_keyword_index.index_nodes = MagicMock()
        mock_keyword_index.search = MagicMock(return_value=[
            {
                "node_id": "node123",
                "text": "test content",
                "score": 0.95,
                "metadata": {"doc_id": "doc123"},
            }
        ])
        mock_keyword_index.remove_document = MagicMock(return_value=5)
        mock_keyword_index.get_stats = MagicMock(return_value={
            "total_entries": 100,
            "unique_documents": 10,
        })
        mock_keyword_index.close = MagicMock()
        return mock_keyword_index

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry."""
        mock_registry = MagicMock()
        mock_registry.register_index_entry = MagicMock()
        mock_registry.get_statistics = MagicMock(return_value={})
        mock_registry.close = MagicMock()
        return mock_registry

    def test_index_manager_uses_keyword_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test IndexManager uses provided keyword index adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            # Initialize IndexManager with keyword adapter
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Verify adapter was used
            assert index_manager.keyword_index == mock_keyword_index
            assert index_manager.keyword_conn is None

    def test_index_manager_falls_back_to_legacy_sqlite(self, sqlite_config, mock_registry):
        """Test IndexManager falls back to legacy SQLite without adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False), \
             patch('core.index_manager.sqlite3') as mock_sqlite:

            mock_conn = MagicMock()
            mock_sqlite.connect.return_value = mock_conn

            # Initialize IndexManager without keyword adapter
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry
            )

            # Verify legacy SQLite was used
            assert index_manager.keyword_index is None
            assert index_manager.keyword_conn == mock_conn

    def test_index_manager_logs_adapter_usage(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test IndexManager logs which keyword index approach was used."""
        with patch('core.index_manager.logger') as mock_logger, \
             patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):

            # Test with adapter
            IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Verify adapter logging
            mock_logger.info.assert_any_call("IndexManager using DatabaseFactory keyword index adapter")

            # Reset mock
            mock_logger.reset_mock()

            # Test without adapter
            with patch('core.index_manager.sqlite3'):
                IndexManager(
                    config=sqlite_config,
                    registry=mock_registry
                )

                # Verify legacy logging
                mock_logger.info.assert_any_call("IndexManager using legacy SQLite keyword index")

    def test_keyword_index_nodes_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test keyword indexing works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Create mock nodes
            mock_nodes = [MagicMock(), MagicMock()]
            for i, node in enumerate(mock_nodes):
                node.node_id = f"node{i}"
                node.text = f"content{i}"
                node.hash = f"hash{i}"
                node.metadata = {}

            # Test keyword indexing
            result = index_manager._keyword_index_nodes(mock_nodes)

            # Verify adapter was called
            assert result is True
            mock_keyword_index.index_nodes.assert_called_once_with(mock_nodes)

    def test_keyword_search_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test keyword search works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test search
            results = index_manager._keyword_search("test query", 10, {"doc_id": "doc123"})

            # Verify adapter was called
            mock_keyword_index.search.assert_called_once_with(
                "test query", 10, filters={"doc_id": "doc123"}
            )
            assert len(results) == 1
            assert results[0]["node_id"] == "node123"

    def test_keyword_remove_document_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test document removal works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test document removal
            deleted_count = index_manager._keyword_remove_document("doc123")

            # Verify adapter was called
            mock_keyword_index.remove_document.assert_called_once_with("doc123")
            assert deleted_count == 5

    def test_keyword_get_stats_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test stats retrieval works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test stats retrieval
            stats = index_manager._keyword_get_stats()

            # Verify adapter was called
            mock_keyword_index.get_stats.assert_called_once()
            assert stats["total_entries"] == 100
            assert stats["unique_documents"] == 10

    def test_search_keyword_method_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test high-level search_keyword method works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False), \
             patch.object(IndexManager, '_get_document_source', return_value="test.pdf"):

            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test high-level search
            results = index_manager.search_keyword("test query", top_k=5)

            # Verify results format
            assert len(results) == 1
            result = results[0]
            assert result["doc_id"] == "doc123"
            assert result["node_id"] == "node123"
            assert result["content"] == "test content"
            assert result["score"] == 0.95
            assert result["source"] == "test.pdf"

    def test_get_statistics_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test get_statistics works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test statistics
            stats = index_manager.get_statistics()

            # Verify adapter stats are included
            assert "keyword_index" in stats
            keyword_stats = stats["keyword_index"]
            assert keyword_stats["entry_count"] == 100
            assert keyword_stats["document_count"] == 10
            assert keyword_stats["status"] == "available"
            assert keyword_stats["backend"] == "adapter"

    def test_remove_document_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test remove_document works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            # Setup mock registry
            mock_registry.get_index_entries.return_value = []
            mock_registry.remove_index_entries.return_value = None

            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test document removal
            result = index_manager.remove_document("doc123", IndexType.KEYWORD)

            # Verify adapter was used
            mock_keyword_index.remove_document.assert_called_once_with("doc123")
            assert result is True

    @pytest.mark.asyncio
    async def test_verify_keyword_index_state_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test verify_keyword_index_state works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            # Setup adapter to return search results (indicating document exists)
            mock_keyword_index.search.return_value = [{"node_id": "node123"}]

            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test verification
            result = await index_manager.verify_keyword_index_state("doc123")

            # Verify results
            assert result["exists"] is True
            assert result["count"] == 1

    def test_close_with_adapter(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test close method works with adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test close
            index_manager.close()

            # Verify adapter close was called
            mock_keyword_index.close.assert_called_once()

    def test_backwards_compatibility_without_adapter(self, sqlite_config, mock_registry):
        """Test IndexManager maintains backwards compatibility without adapter."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False), \
             patch('core.index_manager.sqlite3') as mock_sqlite:

            mock_conn = MagicMock()
            mock_sqlite.connect.return_value = mock_conn

            # Initialize without adapter (legacy mode)
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry
            )

            # Verify legacy behavior
            assert index_manager.keyword_index is None
            assert index_manager.keyword_conn == mock_conn

            # Test that legacy methods would work
            stats = index_manager._keyword_get_stats()
            assert "total_entries" in stats

    def test_error_handling_with_adapter(self, sqlite_config, mock_registry):
        """Test error handling when adapter methods fail."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False):
            # Create faulty adapter
            mock_keyword_index = MagicMock()
            mock_keyword_index.index_nodes.side_effect = Exception("Adapter error")
            mock_keyword_index.search.side_effect = Exception("Search error")
            mock_keyword_index.get_stats.side_effect = Exception("Stats error")

            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Test error handling in various methods
            result = index_manager._keyword_index_nodes([])
            assert result is False

            results = index_manager._keyword_search("test", 10)
            assert results == []

            stats = index_manager._keyword_get_stats()
            assert stats["total_entries"] == 0

    def test_mixed_usage_adapter_and_legacy(self, sqlite_config, mock_registry, mock_keyword_index):
        """Test that adapter takes precedence over legacy SQLite when both are available."""
        with patch('core.index_manager.LLAMA_INDEX_AVAILABLE', False), \
             patch('core.index_manager.sqlite3'):

            # Initialize with adapter (legacy SQLite init will also happen)
            index_manager = IndexManager(
                config=sqlite_config,
                registry=mock_registry,
                keyword_index=mock_keyword_index
            )

            # Verify adapter takes precedence
            assert index_manager.keyword_index == mock_keyword_index

            # Test that adapter methods are used
            result = index_manager._keyword_index_nodes([])
            mock_keyword_index.index_nodes.assert_called_once()

            results = index_manager._keyword_search("test", 10)
            mock_keyword_index.search.assert_called_once()
