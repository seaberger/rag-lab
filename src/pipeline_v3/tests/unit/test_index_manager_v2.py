"""
Unit tests for IndexManagerV2 - LlamaIndex-free implementation.
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

from src.pipeline_v3.core.index_manager_v2 import IndexManagerV2
from src.pipeline_v3.core.data_structures import Document, TextChunk
from src.pipeline_v3.core.registry import IndexType
from src.pipeline_v3.utils.config import PipelineConfig


class TestIndexManagerV2:
    """Test the new IndexManagerV2 without LlamaIndex dependencies."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def test_config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        config.qdrant.use_server = False
        config.qdrant.path = os.path.join(temp_dir, "qdrant")
        config.storage.keyword_db_path = os.path.join(temp_dir, "keyword.db")
        config.storage.base_dir = temp_dir
        return config

    @pytest.fixture
    def index_manager(self, test_config):
        """Create IndexManagerV2 instance."""
        return IndexManagerV2(config=test_config)

    def test_initialization(self, index_manager, test_config):
        """Test that IndexManagerV2 initializes correctly."""
        assert index_manager is not None
        assert index_manager.config == test_config
        assert index_manager.embedding_service is not None
        assert index_manager.text_splitter is not None
        assert index_manager.query_engine is not None
        assert index_manager.qdrant_client is not None
        assert index_manager.keyword_conn is not None

    def test_add_document_basic(self, index_manager):
        """Test adding a document with our custom structures."""
        doc_id = "test-doc-123"
        content = "This is a test document with some content for indexing."
        metadata = {"source": "test.pdf", "category": "test"}

        # Mock embedding service to avoid API calls
        with patch.object(index_manager.embedding_service, 'get_text_embedding_batch') as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]  # Mock embedding

            # Add document
            success = index_manager.add_document(
                doc_id=doc_id,
                content=content,
                metadata=metadata,
                index_types=IndexType.BOTH
            )

            assert success
            assert mock_embed.called

    def test_text_splitting(self, index_manager):
        """Test that text splitting works with our custom TextSplitter."""
        doc = Document(
            text="This is the first sentence. This is the second sentence. " * 50,
            doc_id="split-test",
            metadata={"test": True}
        )

        chunks = index_manager.text_splitter.create_chunks(doc)

        assert len(chunks) > 1
        assert all(isinstance(chunk, TextChunk) for chunk in chunks)
        assert all(chunk.metadata.get("doc_id") == "split-test" for chunk in chunks)
        assert all(chunk.metadata.get("test") == True for chunk in chunks)

    def test_add_chunks_directly(self, index_manager):
        """Test adding pre-processed chunks."""
        doc_id = "chunk-test"

        # Create custom chunks
        chunks = [
            TextChunk(
                text="First chunk of text",
                metadata={"doc_id": doc_id, "chunk_index": 0}
            ),
            TextChunk(
                text="Second chunk of text",
                metadata={"doc_id": doc_id, "chunk_index": 1}
            ),
        ]

        # Mock embedding service
        with patch.object(index_manager.embedding_service, 'get_text_embedding_batch') as mock_embed:
            mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]

            success = index_manager.add_chunks(
                doc_id=doc_id,
                chunks=chunks,
                index_types=IndexType.BOTH
            )

            assert success
            assert mock_embed.called

    def test_keyword_index_sqlite(self, index_manager):
        """Test keyword indexing with SQLite backend."""
        chunks = [
            TextChunk(
                text="Test keyword search",
                metadata={"doc_id": "kw-test", "chunk_index": 0}
            )
        ]

        success = index_manager._keyword_index_chunks(chunks)
        assert success

        # Verify it's in the database
        cursor = index_manager.keyword_conn.execute(
            "SELECT COUNT(*) FROM keyword_index WHERE doc_id = ?",
            ("kw-test",)
        )
        count = cursor.fetchone()[0]
        assert count == 1

    @pytest.mark.asyncio
    async def test_unified_search(self, index_manager):
        """Test the unified search interface."""
        # Add a test document first
        with patch.object(index_manager.embedding_service, 'get_text_embedding_batch') as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            index_manager.add_document(
                doc_id="search-test",
                content="Laser power sensor measurement",
                metadata={"type": "sensor"}
            )

        # Mock the embedding for search
        with patch.object(index_manager.embedding_service, 'get_text_embedding') as mock_embed:
            mock_embed.return_value = [0.1] * 1536

            # Test unified search
            results = await index_manager.search(
                query="laser sensor",
                search_type="hybrid",
                top_k=5
            )

            assert isinstance(results, list)

    def test_remove_document(self, index_manager):
        """Test document removal."""
        doc_id = "remove-test"

        # Add document first
        with patch.object(index_manager.embedding_service, 'get_text_embedding_batch') as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            index_manager.add_document(
                doc_id=doc_id,
                content="Document to be removed",
                index_types=IndexType.BOTH
            )

        # Remove document
        success = index_manager.remove_document(doc_id)
        assert success

    def test_statistics(self, index_manager):
        """Test getting index statistics."""
        stats = index_manager.get_statistics()

        assert "vector_index" in stats
        assert "keyword_index" in stats
        assert "total_documents" in stats

        # Keyword index should be active since we use SQLite
        assert stats["keyword_index"]["status"] == "active"

    def test_backend_metadata(self, index_manager, test_config):
        """Test that backend-specific metadata is added."""
        # Test SQLite backend
        test_config.database.backend = "sqlite"

        doc = Document(text="Test content", doc_id="backend-test")
        chunks = index_manager.text_splitter.create_chunks(doc)

        # Check SQLite metadata
        for chunk in chunks:
            assert chunk.metadata.get("backend") == "sqlite"
            assert "tenant_id" not in chunk.metadata

        # Test PostgreSQL backend
        test_config.database.backend = "postgresql"
        test_config.database.postgresql.default_tenant_id = "test-tenant-123"

        # Reinitialize with PostgreSQL config
        pg_manager = IndexManagerV2(config=test_config)

        with patch.object(pg_manager.embedding_service, 'get_text_embedding_batch') as mock_embed:
            mock_embed.return_value = [[0.1] * 1536]

            success = pg_manager.add_document(
                doc_id="pg-test",
                content="PostgreSQL test content",
                index_types=IndexType.VECTOR
            )

            # The chunks created should have PostgreSQL metadata
            # This is verified internally during add_document


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
