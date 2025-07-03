"""
Unit tests for DocumentRegistry component.

Tests cover document registration, state tracking, and lifecycle management.
"""

import sys
import tempfile
from pathlib import Path

import pytest
from core.registry import IndexType

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.registry import DocumentRegistry, DocumentState

from utils.config import PipelineConfig


class TestDocumentRegistry:
    """Test suite for DocumentRegistry."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test databases."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def registry(self, temp_dir):
        """Create a test document registry."""
        config = PipelineConfig()
        config.storage.document_registry_path = str(Path(temp_dir) / "test_registry.db")
        return DocumentRegistry(config=config)

    def test_register_document(self, registry):
        """Test basic document registration."""
        # Register a document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890,
            metadata={"type": "datasheet"}
        )

        # Verify document was registered
        assert doc_id is not None
        doc = registry.get_document(doc_id)
        assert doc is not None
        assert doc.source.endswith("test.pdf")  # Registry converts to absolute path
        assert doc.content_hash == "hash123"
        assert doc.size == 1000
        # New documents start in NEW state
        assert doc.state == DocumentState.NEW.value

    def test_update_document_state(self, registry):
        """Test document state transitions."""
        # Register document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Update to updating state
        registry.update_document_state(doc_id, DocumentState.UPDATING)
        doc = registry.get_document(doc_id)
        assert doc.state == DocumentState.UPDATING.value

        # Update to indexed state
        registry.update_document_state(doc_id, DocumentState.INDEXED)
        doc = registry.get_document(doc_id)
        assert doc.state == DocumentState.INDEXED.value

    def test_list_documents(self, registry):
        """Test listing documents with filters."""
        # Register multiple documents
        doc1 = registry.register_document(
            source="doc1.pdf",
            content_hash="hash1",
            size=1000,
            modified_time=1234567890
        )

        doc2 = registry.register_document(
            source="doc2.pdf",
            content_hash="hash2",
            size=2000,
            modified_time=1234567891
        )

        # Update states
        registry.update_document_state(doc1, DocumentState.INDEXED)
        registry.update_document_state(doc2, DocumentState.UPDATING)

        # Test listing all documents
        all_docs = registry.list_documents()
        assert len(all_docs) == 2

        # Test filtering by state
        indexed_docs = registry.list_documents(state=DocumentState.INDEXED)
        assert len(indexed_docs) == 1
        assert indexed_docs[0].doc_id == doc1

        updating_docs = registry.list_documents(state=DocumentState.UPDATING)
        assert len(updating_docs) == 1
        assert updating_docs[0].doc_id == doc2

    def test_get_document_by_source(self, registry):
        """Test retrieving document by source path."""
        # Register document
        doc_id = registry.register_document(
            source="unique/path/test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Get by source (need to use absolute path)
        abs_source = registry.get_document(doc_id).source
        doc = registry.get_document_by_source(abs_source)
        assert doc is not None
        assert doc.doc_id == doc_id

        # Test non-existent source
        doc = registry.get_document_by_source("non/existent.pdf")
        assert doc is None

    def test_update_index_status(self, registry):
        """Test updating document index status."""

        # Register document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Initially not indexed
        doc = registry.get_document(doc_id)
        assert not doc.vector_indexed
        assert not doc.keyword_indexed

        # Update vector index status
        registry.mark_indexed(doc_id, IndexType.VECTOR, chunk_count=5)
        doc = registry.get_document(doc_id)
        assert doc.vector_indexed
        assert not doc.keyword_indexed

        # Update keyword index status
        registry.mark_indexed(doc_id, IndexType.KEYWORD, chunk_count=5)
        doc = registry.get_document(doc_id)
        assert doc.vector_indexed
        assert doc.keyword_indexed

    def test_get_statistics(self, registry):
        """Test registry statistics."""
        # Register multiple documents in different states
        doc1 = registry.register_document(
            source="doc1.pdf",
            content_hash="hash1",
            size=1000,
            modified_time=1234567890
        )

        doc2 = registry.register_document(
            source="doc2.pdf",
            content_hash="hash2",
            size=2000,
            modified_time=1234567891
        )

        doc3 = registry.register_document(
            source="doc3.pdf",
            content_hash="hash3",
            size=3000,
            modified_time=1234567892
        )

        # Update states
        registry.update_document_state(doc1, DocumentState.INDEXED)
        registry.update_document_state(doc2, DocumentState.INDEXED)
        registry.update_document_state(doc3, DocumentState.CORRUPTED)

        # Update index status
        registry.mark_indexed(doc1, IndexType.BOTH, chunk_count=10)
        registry.mark_indexed(doc2, IndexType.VECTOR, chunk_count=5)

        # Get statistics
        stats = registry.get_statistics()

        assert stats["total_documents"] == 3
        assert stats["by_state"]["indexed"]["count"] == 2
        assert stats["by_state"]["corrupted"]["count"] == 1
        assert stats["consistency"]["health_score"] > 0

    def test_duplicate_document_handling(self, registry):
        """Test handling of duplicate documents."""
        # Register document
        registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Try to register same document again
        doc_id2 = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Should return the same document ID (or a new one if duplicates allowed)
        # The behavior depends on the registry implementation
        assert doc_id2 is not None

    def test_content_hash_change_detection(self, registry):
        """Test detection of content changes."""
        # Register document
        doc_id1 = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Register same source with different hash
        doc_id2 = registry.register_document(
            source="test.pdf",
            content_hash="hash456",  # Different hash
            size=1500,
            modified_time=1234567895
        )

        # Should be treated as an update (same ID)
        assert doc_id1 == doc_id2

        # Verify content was updated
        doc = registry.get_document(doc_id1)
        assert doc.content_hash == "hash456"
        assert doc.size == 1500

    def test_metadata_storage(self, registry):
        """Test metadata storage and retrieval."""
        # Register document with complex metadata
        metadata = {
            "type": "datasheet",
            "manufacturer": "Coherent",
            "products": ["PM10", "PM30"],
            "specifications": {
                "power_range": "10W-100W",
                "wavelength": "1064nm"
            }
        }

        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890,
            metadata=metadata
        )

        # Retrieve and verify metadata
        doc = registry.get_document(doc_id)
        assert doc.metadata == metadata
        assert doc.metadata["specifications"]["power_range"] == "10W-100W"

    def test_get_pending_documents(self, registry):
        """Test retrieving pending documents for processing."""
        # Register multiple documents
        docs = []
        for i in range(5):
            doc_id = registry.register_document(
                source=f"doc{i}.pdf",
                content_hash=f"hash{i}",
                size=1000 * (i + 1),
                modified_time=1234567890 + i
            )
            docs.append(doc_id)

        # Update some states
        registry.update_document_state(docs[0], DocumentState.INDEXED)
        registry.update_document_state(docs[1], DocumentState.UPDATING)
        registry.update_document_state(docs[2], DocumentState.CORRUPTED)
        # docs[3] and docs[4] remain in NEW state

        # Get pending documents (NEW state)
        pending = registry.list_documents(state=DocumentState.NEW)
        assert len(pending) == 2
        assert all(doc.state == DocumentState.NEW.value for doc in pending)

    def test_remove_document(self, registry):
        """Test document removal."""
        # Register a document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Remove it
        registry.remove_document(doc_id)

        # Check document is removed
        doc = registry.get_document(doc_id)
        assert doc is None  # Document is deleted after removal

    def test_transaction_handling(self, registry):
        """Test transaction handling in registry operations."""
        # Register a document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )

        # Verify initial state
        doc = registry.get_document(doc_id)
        assert doc.state == DocumentState.NEW.value

        # The registry should handle transactions internally
        # Updates should be atomic
        registry.update_document_state(doc_id, DocumentState.INDEXED)
        registry.mark_indexed(doc_id, IndexType.VECTOR, chunk_count=1)

        # Verify both updates succeeded
        doc = registry.get_document(doc_id)
        assert doc.state == DocumentState.INDEXED.value
        assert doc.vector_indexed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
