"""
Unit tests for backend-aware LlamaIndex helpers.

Tests the BackendAwareNodeFactory and BackendAwareQueryProcessor
to ensure proper metadata handling for both SQLite and PostgreSQL backends.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from llama_index.core.schema import TextNode, Document
from llama_index.core.vector_stores import VectorStoreQuery

from core.llama_index_helpers import BackendAwareNodeFactory, create_backend_aware_nodes
from core.query_helpers import BackendAwareQueryProcessor
from utils.config import PipelineConfig


class TestBackendAwareNodeFactory:
    """Test the BackendAwareNodeFactory class."""

    def test_init_sqlite_backend(self, test_config):
        """Test initialization with SQLite backend."""
        test_config.database.backend = "sqlite"
        factory = BackendAwareNodeFactory(test_config)

        assert factory.backend == "sqlite"
        assert not factory.is_postgresql
        assert factory.tenant_id is None

    def test_init_postgresql_backend(self, test_config):
        """Test initialization with PostgreSQL backend."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "test-tenant-123"

        factory = BackendAwareNodeFactory(test_config)

        assert factory.backend == "postgresql"
        assert factory.is_postgresql
        assert factory.tenant_id == "test-tenant-123"

    def test_create_document_sqlite(self, test_config):
        """Test creating a document with SQLite backend."""
        test_config.database.backend = "sqlite"
        factory = BackendAwareNodeFactory(test_config)

        doc = factory.create_document(
            text="Test content",
            doc_id="doc123",
            metadata={"author": "test"}
        )

        assert isinstance(doc, Document)
        assert doc.text == "Test content"
        assert doc.doc_id == "doc123"
        assert doc.metadata["doc_id"] == "doc123"
        assert doc.metadata["author"] == "test"
        assert doc.metadata["backend"] == "sqlite"
        assert "tenant_id" not in doc.metadata

    def test_create_document_postgresql(self, test_config):
        """Test creating a document with PostgreSQL backend."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "tenant-456"

        factory = BackendAwareNodeFactory(test_config)

        doc = factory.create_document(
            text="Test content",
            doc_id="doc456",
            metadata={"category": "datasheet"}
        )

        assert isinstance(doc, Document)
        assert doc.metadata["doc_id"] == "doc456"
        assert doc.metadata["backend"] == "postgresql"
        assert doc.metadata["tenant_id"] == "tenant-456"
        assert doc.metadata["category"] == "datasheet"

    def test_create_text_node(self, test_config):
        """Test creating a single text node."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "tenant-789"

        factory = BackendAwareNodeFactory(test_config)

        node = factory.create_text_node(
            text="Node content",
            node_id="node123",
            metadata={"chunk_index": 0}
        )

        assert isinstance(node, TextNode)
        assert node.text == "Node content"
        assert node.id_ == "node123"
        assert node.metadata["backend"] == "postgresql"
        assert node.metadata["tenant_id"] == "tenant-789"
        assert node.metadata["chunk_index"] == 0

    def test_create_nodes_from_document(self, test_config):
        """Test creating nodes from a document."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "tenant-abc"

        factory = BackendAwareNodeFactory(test_config)

        # Create a custom text splitter that returns nodes with empty metadata
        mock_splitter = Mock()
        mock_node1 = TextNode(text="Node 1", id_="n1", metadata={})
        mock_node2 = TextNode(text="Node 2", id_="n2", metadata={})
        mock_splitter.get_nodes_from_documents.return_value = [mock_node1, mock_node2]

        doc = Document(
            text="Document content",
            doc_id="doc789",
            metadata={"source": "test.pdf", "doc_id": "doc789"}
        )

        # Use the custom splitter
        nodes = factory.create_nodes_from_document(doc, text_splitter=mock_splitter)

        # Verify nodes were enhanced with backend metadata
        assert len(nodes) == 2
        assert all(node.metadata["backend"] == "postgresql" for node in nodes)
        assert all(node.metadata["tenant_id"] == "tenant-abc" for node in nodes)
        # doc_id should be inherited from document metadata
        assert all(node.metadata.get("doc_id") == "doc789" for node in nodes)
        assert all(node.metadata["source"] == "test.pdf" for node in nodes)

    def test_enhance_node_metadata(self, test_config):
        """Test enhancing node metadata."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "tenant-xyz"

        factory = BackendAwareNodeFactory(test_config)

        node = TextNode(text="Test", id_="node1")
        parent_metadata = {
            "doc_id": "doc999",
            "source": "enhanced.pdf",
            "custom": "value"
        }

        factory.enhance_node_metadata(node, parent_metadata)

        assert node.metadata["doc_id"] == "doc999"
        assert node.metadata["source"] == "enhanced.pdf"
        assert node.metadata["backend"] == "postgresql"
        assert node.metadata["tenant_id"] == "tenant-xyz"
        assert "custom" not in node.metadata  # Only specific fields inherited

    def test_prepare_nodes_for_indexing(self, test_config):
        """Test preparing nodes for indexing."""
        test_config.database.backend = "sqlite"
        factory = BackendAwareNodeFactory(test_config)

        nodes = [
            TextNode(text="Node 1", id_="n1"),
            TextNode(text="Node 2", id_="n2", metadata={"existing": "data"}),
        ]

        prepared = factory.prepare_nodes_for_indexing(
            nodes,
            doc_id="doc321",
            source="prepared.pdf"
        )

        assert len(prepared) == 2
        assert prepared[0].metadata["doc_id"] == "doc321"
        assert prepared[0].metadata["source"] == "prepared.pdf"
        assert prepared[0].metadata["chunk_index"] == 0
        assert prepared[1].metadata["chunk_index"] == 1
        assert prepared[1].metadata["existing"] == "data"
        assert all(node.metadata["backend"] == "sqlite" for node in prepared)


class TestBackendAwareQueryProcessor:
    """Test the BackendAwareQueryProcessor class."""

    def test_init_sqlite_backend(self, test_config):
        """Test initialization with SQLite backend."""
        test_config.database.backend = "sqlite"
        processor = BackendAwareQueryProcessor(test_config)

        assert processor.backend == "sqlite"
        assert not processor.is_postgresql
        assert processor.tenant_id is None

    def test_init_postgresql_backend(self, test_config):
        """Test initialization with PostgreSQL backend."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "query-tenant-123"

        processor = BackendAwareQueryProcessor(test_config)

        assert processor.backend == "postgresql"
        assert processor.is_postgresql
        assert processor.tenant_id == "query-tenant-123"

    def test_prepare_vector_query(self, test_config):
        """Test preparing a vector query."""
        test_config.database.backend = "postgresql"
        processor = BackendAwareQueryProcessor(test_config)

        query_embedding = [0.1, 0.2, 0.3]
        filters = {"category": "datasheet"}

        query = processor.prepare_vector_query(
            query_embedding=query_embedding,
            top_k=5,
            filters=filters
        )

        assert isinstance(query, VectorStoreQuery)
        assert query.query_embedding == query_embedding
        assert query.similarity_top_k == 5

    def test_process_filters_postgresql(self, test_config):
        """Test filter processing for PostgreSQL."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "filter-tenant"

        processor = BackendAwareQueryProcessor(test_config)

        # Test adding tenant filter
        filters = {"category": "datasheet"}
        processed = processor.process_filters(filters)

        assert processed["category"] == "datasheet"
        assert processed["tenant_id"] == "filter-tenant"

        # Test preserving existing tenant filter
        filters = {"category": "datasheet", "tenant_id": "custom-tenant"}
        processed = processor.process_filters(filters)

        assert processed["tenant_id"] == "custom-tenant"

    def test_process_vector_results(self, test_config):
        """Test processing vector search results."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "result-tenant"

        processor = BackendAwareQueryProcessor(test_config)

        # Mock results
        mock_result1 = Mock()
        mock_result1.node_id = "node1"
        mock_result1.score = 0.9
        mock_result1.text = "Result 1 text"
        mock_result1.metadata = {"doc_id": "doc1", "tenant_id": "result-tenant"}

        mock_result2 = Mock()
        mock_result2.node_id = "node2"
        mock_result2.score = 0.8
        mock_result2.text = "Result 2 text"
        mock_result2.metadata = {"doc_id": "doc2", "tenant_id": "wrong-tenant"}

        mock_results = Mock()
        mock_results.nodes = [mock_result1, mock_result2]

        processed = processor.process_vector_results(mock_results)

        # Should only include result with matching tenant
        assert len(processed) == 1
        assert processed[0]["node_id"] == "node1"
        assert processed[0]["score"] == 0.9
        assert processed[0]["text"] == "Result 1 text"
        assert processed[0]["doc_id"] == "doc1"

    def test_extract_metadata_qdrant_server_mode(self, test_config):
        """Test extracting metadata from Qdrant server mode results."""
        processor = BackendAwareQueryProcessor(test_config)

        # Mock Qdrant server mode result
        mock_node = Mock(spec=[])  # No metadata attribute
        mock_node.payload = {
            "_node_content": '{"metadata": {"doc_id": "doc123", "source": "test.pdf"}, "text": "content"}',
            "other_field": "value"
        }

        metadata = processor.extract_metadata(mock_node)

        assert metadata["doc_id"] == "doc123"
        assert metadata["source"] == "test.pdf"

    def test_matches_filters(self, test_config):
        """Test filter matching logic."""
        processor = BackendAwareQueryProcessor(test_config)

        metadata = {
            "doc_id": "doc1",
            "category": "datasheet",
            "tenant_id": "tenant1"
        }

        # Test doc_ids filter
        assert processor.matches_filters(metadata, {"doc_ids": ["doc1", "doc2"]})
        assert not processor.matches_filters(metadata, {"doc_ids": ["doc3", "doc4"]})

        # Test direct match
        assert processor.matches_filters(metadata, {"category": "datasheet"})
        assert not processor.matches_filters(metadata, {"category": "manual"})

        # Test multiple filters
        assert processor.matches_filters(metadata, {
            "category": "datasheet",
            "doc_ids": ["doc1"]
        })

    def test_prepare_keyword_query(self, test_config):
        """Test preparing a keyword query."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "keyword-tenant"

        processor = BackendAwareQueryProcessor(test_config)

        params = processor.prepare_keyword_query(
            "test query",
            filters={"category": "manual"}
        )

        assert params["query"] == "test query"
        assert params["filters"]["category"] == "manual"
        assert params["filters"]["tenant_id"] == "keyword-tenant"
        assert params["search_config"] == "english"
        assert params["tenant_id"] == "keyword-tenant"

    def test_process_keyword_results(self, test_config):
        """Test processing keyword search results."""
        processor = BackendAwareQueryProcessor(test_config)

        results = [
            {"text": "Result 1", "score": 10.0},
            {"text": "Result 2", "score": 5.0, "content": "Content 2"},
            {"text": "Result 3", "score": 2.5},
        ]

        processed = processor.process_keyword_results(results, normalize_scores=True)

        assert len(processed) == 3
        assert processed[0]["score"] == 1.0  # Normalized
        assert processed[1]["score"] == 0.5
        assert processed[2]["score"] == 0.25

        # Test content/text consistency
        assert processed[0]["content"] == "Result 1"
        assert processed[1]["text"] == "Result 2"  # Original text preserved
        assert processed[1]["content"] == "Content 2"  # Original content preserved
        assert all(r["backend"] == processor.backend for r in processed)


class TestBackendAwareIntegration:
    """Test integration between factory and processor."""

    def test_create_backend_aware_nodes_function(self, test_config):
        """Test the convenience function for creating backend-aware nodes."""
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "integration-tenant"

        with patch('src.pipeline_v3.core.llama_index_helpers.Settings') as mock_settings:
            # Mock text splitter
            mock_splitter = Mock()
            mock_node = TextNode(text="Split content", id_="split1", metadata={})
            mock_splitter.get_nodes_from_documents.return_value = [mock_node]
            mock_settings.text_splitter = mock_splitter

            nodes = create_backend_aware_nodes(
                config=test_config,
                content="Test document content",
                doc_id="int-doc-123",
                metadata={"type": "test"}
            )

            assert len(nodes) == 1
            assert nodes[0].metadata["doc_id"] == "int-doc-123"
            assert nodes[0].metadata["backend"] == "postgresql"
            assert nodes[0].metadata["tenant_id"] == "integration-tenant"
            # Note: custom metadata like "type" is not automatically inherited to nodes
            assert nodes[0].metadata["chunk_index"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
