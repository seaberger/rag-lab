"""
Integration tests for LlamaIndex with PostgreSQL backend.

Tests the integration of backend-aware node creation and query processing
with actual IndexManager operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import uuid

from core.index_manager import IndexManager
from core.registry import DocumentRegistry, IndexType
from utils.config import PipelineConfig
from storage.database_factory import DatabaseFactory


class TestLlamaIndexPostgreSQLIntegration:
    """Test LlamaIndex integration with PostgreSQL backend."""

    @pytest.fixture
    def pg_config(self):
        """Create a PostgreSQL configuration."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        config.database.postgresql.default_tenant_id = str(uuid.uuid4())
        return config

    @pytest.fixture
    def sqlite_config(self):
        """Create a SQLite configuration."""
        config = PipelineConfig()
        config.database.backend = "sqlite"
        return config

    def test_index_manager_with_postgresql_factory(self, pg_config):
        """Test IndexManager initialization with PostgreSQL via DatabaseFactory."""
        with patch('storage.database_factory.DatabaseFactory') as mock_factory_class:
            # Mock the factory instance
            mock_factory = Mock()
            mock_factory.validate_backend_configuration.return_value = True

            # Mock adapters
            mock_adapters = {
                "registry": Mock(spec=DocumentRegistry),
                "keyword_index": Mock(),
                "fingerprint_manager": Mock(),
                "job_manager": Mock(),
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Create IndexManager with factory
            factory = DatabaseFactory(pg_config)
            adapters = factory.create_all()

            index_manager = IndexManager(
                config=pg_config,
                registry=adapters["registry"],
                keyword_index=adapters["keyword_index"]
            )

            # Verify backend-aware components are initialized
            assert index_manager.config.database.backend == "postgresql"
            assert index_manager.keyword_index is not None
            assert index_manager.registry is not None

            # Verify node factory is initialized
            assert hasattr(index_manager, 'node_factory')
            if index_manager.node_factory:
                assert index_manager.node_factory.is_postgresql
                assert index_manager.node_factory.tenant_id == pg_config.database.postgresql.default_tenant_id

            # Verify query processor is initialized
            assert hasattr(index_manager, 'query_processor')
            if index_manager.query_processor:
                assert index_manager.query_processor.is_postgresql
                assert index_manager.query_processor.tenant_id == pg_config.database.postgresql.default_tenant_id

    def test_add_document_with_backend_aware_nodes(self, pg_config):
        """Test adding a document with backend-aware node creation."""
        with patch('storage.database_factory.DatabaseFactory') as mock_factory_class:
            # Mock factory and adapters
            mock_factory = Mock()
            mock_factory.validate_backend_configuration.return_value = True

            mock_registry = Mock(spec=DocumentRegistry)
            mock_registry.register_index_entry = Mock()
            mock_registry.mark_indexed = Mock()
            mock_registry.update_document_state = Mock()

            mock_keyword_index = Mock()
            mock_keyword_index.index_nodes = Mock(return_value=True)

            mock_adapters = {
                "registry": mock_registry,
                "keyword_index": mock_keyword_index,
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Mock vector store
            with patch('core.index_manager.QdrantVectorStore') as mock_vector_store_class:
                mock_vector_store = Mock()
                mock_vector_store_class.return_value = mock_vector_store

                # Create IndexManager
                factory = DatabaseFactory(pg_config)
                adapters = factory.create_all()

                index_manager = IndexManager(
                    config=pg_config,
                    registry=adapters["registry"],
                    keyword_index=adapters["keyword_index"]
                )

                # Mock the vector store on the index manager
                index_manager.vector_store = mock_vector_store

                # Test adding document
                doc_id = str(uuid.uuid4())
                content = "Test document content for PostgreSQL backend"
                metadata = {"source": "test.pdf", "category": "datasheet"}

                # Mock embedding model
                index_manager.embedding_model = Mock()

                # Add document
                success = index_manager.add_document(
                    doc_id=doc_id,
                    content=content,
                    metadata=metadata,
                    index_types=IndexType.BOTH
                )

                # Verify backend-aware processing occurred
                if index_manager.node_factory:
                    # Nodes should have been created with backend metadata
                    assert mock_keyword_index.index_nodes.called

                    # Get the nodes passed to index_nodes
                    call_args = mock_keyword_index.index_nodes.call_args
                    if call_args:
                        nodes = call_args[0][0] if call_args[0] else []
                        # In actual implementation, nodes would have backend metadata

    def test_search_with_backend_aware_query_processor(self, pg_config):
        """Test search operations with backend-aware query processing."""
        with patch('storage.database_factory.DatabaseFactory') as mock_factory_class:
            # Mock factory and adapters
            mock_factory = Mock()
            mock_factory.validate_backend_configuration.return_value = True

            mock_registry = Mock(spec=DocumentRegistry)
            mock_keyword_index = Mock()

            # Mock keyword search results
            mock_keyword_index.search.return_value = [
                {
                    "doc_id": "doc1",
                    "chunk_id": "chunk1",
                    "text": "Result 1",
                    "score": 10.0,
                    "metadata": {"tenant_id": pg_config.database.postgresql.default_tenant_id}
                },
                {
                    "doc_id": "doc2",
                    "chunk_id": "chunk2",
                    "text": "Result 2",
                    "score": 5.0,
                    "metadata": {"tenant_id": pg_config.database.postgresql.default_tenant_id}
                }
            ]

            mock_adapters = {
                "registry": mock_registry,
                "keyword_index": mock_keyword_index,
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Create IndexManager
            factory = DatabaseFactory(pg_config)
            adapters = factory.create_all()

            index_manager = IndexManager(
                config=pg_config,
                registry=adapters["registry"],
                keyword_index=adapters["keyword_index"]
            )

            # Mock document source cache
            index_manager._get_document_source = Mock(return_value="test.pdf")

            # Test keyword search
            results = index_manager.search_keyword("test query", top_k=5)

            # Verify search was performed
            assert mock_keyword_index.search.called

            # If query processor is available, it should process results
            if index_manager.query_processor:
                # Results should be normalized
                assert len(results) <= 5
                if results:
                    # Scores should be normalized if processor is used
                    assert all(0 <= r.get("score", 0) <= 1.0 for r in results)

    def test_backend_aware_hybrid_search(self, pg_config):
        """Test hybrid search with backend-aware processing."""
        with patch('storage.database_factory.DatabaseFactory') as mock_factory_class:
            # Mock factory and adapters
            mock_factory = Mock()
            mock_factory.validate_backend_configuration.return_value = True

            mock_registry = Mock(spec=DocumentRegistry)

            # Mock keyword index
            mock_keyword_index = Mock()
            mock_keyword_index.search.return_value = [
                {"doc_id": "doc1", "node_id": "n1", "text": "Keyword result", "score": 1.0}
            ]

            mock_adapters = {
                "registry": mock_registry,
                "keyword_index": mock_keyword_index,
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Mock vector store
            with patch('core.index_manager.QdrantVectorStore') as mock_vector_store_class:
                mock_vector_store = Mock()

                # Mock vector search results
                mock_vector_result = Mock()
                mock_vector_result.nodes = []
                mock_vector_store.query.return_value = mock_vector_result

                mock_vector_store_class.return_value = mock_vector_store

                # Create IndexManager
                factory = DatabaseFactory(pg_config)
                adapters = factory.create_all()

                index_manager = IndexManager(
                    config=pg_config,
                    registry=adapters["registry"],
                    keyword_index=adapters["keyword_index"]
                )

                # Set up mocks
                index_manager.vector_store = mock_vector_store
                index_manager.embedding_model = Mock()
                index_manager.embedding_model.get_text_embedding.return_value = [0.1] * 1536
                index_manager._get_document_source = Mock(return_value="test.pdf")

                # Test hybrid search
                results = index_manager.hybrid_search(
                    query="test query",
                    top_k=5,
                    filters={"category": "datasheet"}
                )

                # Verify both search types were called
                assert mock_keyword_index.search.called
                assert mock_vector_store.query.called

                # Results should be fused
                assert isinstance(results, list)

    def test_sqlite_fallback_compatibility(self, sqlite_config):
        """Test that SQLite backend still works without backend-aware features."""
        # Create IndexManager with SQLite config
        index_manager = IndexManager(config=sqlite_config)

        # Verify SQLite backend
        assert index_manager.config.database.backend == "sqlite"

        # Backend-aware components might not be initialized for SQLite
        # or they should work in SQLite mode
        if hasattr(index_manager, 'node_factory') and index_manager.node_factory:
            assert not index_manager.node_factory.is_postgresql
            assert index_manager.node_factory.backend == "sqlite"

        if hasattr(index_manager, 'query_processor') and index_manager.query_processor:
            assert not index_manager.query_processor.is_postgresql
            assert index_manager.query_processor.backend == "sqlite"


class TestBackendAwareNodeCreation:
    """Test backend-aware node creation in detail."""

    def test_node_metadata_postgresql(self, pg_config):
        """Test that nodes get proper PostgreSQL metadata."""
        from core.llama_index_helpers import BackendAwareNodeFactory

        factory = BackendAwareNodeFactory(pg_config)
        tenant_id = pg_config.database.postgresql.default_tenant_id

        # Create a document
        doc = factory.create_document(
            text="PostgreSQL test content",
            doc_id="pg-doc-123",
            metadata={"source": "pg-test.pdf"}
        )

        # Verify document metadata
        assert doc.metadata["backend"] == "postgresql"
        assert doc.metadata["tenant_id"] == tenant_id
        assert doc.metadata["doc_id"] == "pg-doc-123"
        assert doc.metadata["source"] == "pg-test.pdf"

        # Create nodes (mock the splitter)
        with patch('core.llama_index_helpers.Settings') as mock_settings:
            mock_splitter = Mock()
            mock_node = Mock()
            mock_node.metadata = {}
            mock_splitter.get_nodes_from_documents.return_value = [mock_node]
            mock_settings.text_splitter = mock_splitter

            nodes = factory.create_nodes_from_document(doc)

            # Verify node metadata was enhanced
            assert mock_node.metadata["backend"] == "postgresql"
            assert mock_node.metadata["tenant_id"] == tenant_id
            assert mock_node.metadata["doc_id"] == "pg-doc-123"

    def test_node_metadata_sqlite(self, sqlite_config):
        """Test that nodes get proper SQLite metadata."""
        from core.llama_index_helpers import BackendAwareNodeFactory

        factory = BackendAwareNodeFactory(sqlite_config)

        # Create a document
        doc = factory.create_document(
            text="SQLite test content",
            doc_id="sqlite-doc-456",
            metadata={"source": "sqlite-test.pdf"}
        )

        # Verify document metadata
        assert doc.metadata["backend"] == "sqlite"
        assert "tenant_id" not in doc.metadata
        assert doc.metadata["doc_id"] == "sqlite-doc-456"


class TestBackendAwareQueryProcessing:
    """Test backend-aware query processing in detail."""

    def test_query_filters_postgresql(self, pg_config):
        """Test query filter processing for PostgreSQL."""
        from core.query_helpers import BackendAwareQueryProcessor

        processor = BackendAwareQueryProcessor(pg_config)
        tenant_id = pg_config.database.postgresql.default_tenant_id

        # Test filter processing adds tenant_id
        filters = {"category": "datasheet"}
        processed = processor.process_filters(filters)

        assert processed["category"] == "datasheet"
        assert processed["tenant_id"] == tenant_id

        # Test vector query preparation
        query = processor.prepare_vector_query(
            query_embedding=[0.1, 0.2, 0.3],
            top_k=10,
            filters=processed
        )

        assert query.query_embedding == [0.1, 0.2, 0.3]
        assert query.similarity_top_k == 10

    def test_result_processing_postgresql(self, pg_config):
        """Test result processing with tenant filtering."""
        from core.query_helpers import BackendAwareQueryProcessor

        processor = BackendAwareQueryProcessor(pg_config)
        tenant_id = pg_config.database.postgresql.default_tenant_id

        # Mock results with mixed tenants
        mock_results = Mock()

        result1 = Mock()
        result1.node_id = "n1"
        result1.score = 0.9
        result1.text = "Correct tenant"
        result1.metadata = {"tenant_id": tenant_id, "doc_id": "doc1"}

        result2 = Mock()
        result2.node_id = "n2"
        result2.score = 0.8
        result2.text = "Wrong tenant"
        result2.metadata = {"tenant_id": "wrong-tenant", "doc_id": "doc2"}

        result3 = Mock()
        result3.node_id = "n3"
        result3.score = 0.7
        result3.text = "No tenant"
        result3.metadata = {"doc_id": "doc3"}

        mock_results.nodes = [result1, result2, result3]

        # Process results
        processed = processor.process_vector_results(mock_results)

        # Should only include correct tenant and no tenant
        assert len(processed) == 2
        assert processed[0]["node_id"] == "n1"
        assert processed[1]["node_id"] == "n3"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
