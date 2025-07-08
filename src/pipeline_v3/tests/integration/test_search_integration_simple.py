"""
Simple Search Integration Tests for Pipeline v3

Focused tests to ensure search functionality works correctly without complex setup.
Each test is self-contained and tests one specific aspect of search.
"""

import pytest
import time
from pathlib import Path
import sys

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.database_factory import DatabaseFactory
from core.index_manager import IndexManager
from core.registry import IndexType
from utils.config import PipelineConfig


@pytest.mark.requires_qdrant_server
class TestSimpleSearchIntegration:
    """Simplified integration tests for search functionality."""

    @pytest.fixture
    def index_manager(self, test_config):
        """Create a clean IndexManager for each test."""
        # Create database adapters
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()

        # Create index manager with proper adapters
        index_manager = IndexManager(
            config=test_config,
            registry=adapters["registry"],
            keyword_index=adapters["keyword_index"]
        )

        yield index_manager

        # Cleanup is handled by conftest.py

    def test_vector_search_basic(self, index_manager):
        """Test basic vector search functionality."""
        # Add a simple document directly
        doc_id = "test_vec_001"
        content = "This is a test document about laser power measurement devices with USB connectivity"

        # Add document to vector index only
        success = index_manager.add_document(
            doc_id=doc_id,
            content=content,
            metadata={"source": "test_vector.txt", "category": "test"},
            index_types=IndexType.VECTOR
        )
        assert success, "Failed to add document to vector index"

        # Search for related content
        results = index_manager.search_vector("laser measurement USB", top_k=3)

        # Verify we get results
        assert len(results) > 0, "No vector search results found"
        assert results[0]["doc_id"] == doc_id
        assert "score" in results[0]
        assert results[0]["score"] > 0

    def test_keyword_search_basic(self, index_manager):
        """Test basic keyword search functionality."""
        # Add a document with specific keywords
        doc_id = "test_kw_001"
        content = "The LabMax-Touch device provides accurate thermopile sensor measurements"

        # Add document to keyword index only
        success = index_manager.add_document(
            doc_id=doc_id,
            content=content,
            metadata={"source": "test_keyword.txt", "product": "LabMax-Touch"},
            index_types=IndexType.KEYWORD
        )
        assert success, "Failed to add document to keyword index"

        # Search for exact keyword
        results = index_manager.search_keyword("LabMax-Touch", top_k=3)

        # Verify results
        assert len(results) > 0, "No keyword search results found"
        assert results[0]["doc_id"] == doc_id
        assert "labmax-touch" in results[0]["content"].lower()

    def test_hybrid_search_basic(self, index_manager):
        """Test basic hybrid search combining vector and keyword."""
        # Add documents to both indexes
        docs = [
            {
                "id": "hybrid_001",
                "content": "Advanced laser power meter with USB interface for precise measurements",
                "metadata": {"type": "power_meter"}
            },
            {
                "id": "hybrid_002",
                "content": "Temperature sensor with thermopile technology and digital readout",
                "metadata": {"type": "temp_sensor"}
            },
            {
                "id": "hybrid_003",
                "content": "USB-powered measurement device for laboratory use",
                "metadata": {"type": "general"}
            }
        ]

        # Add all documents to both indexes
        for doc in docs:
            success = index_manager.add_document(
                doc_id=doc["id"],
                content=doc["content"],
                metadata=doc["metadata"],
                index_types=IndexType.BOTH
            )
            assert success, f"Failed to add document {doc['id']}"

        # Perform hybrid search
        results = index_manager.hybrid_search("USB laser measurement", top_k=5)

        # Verify we get results from fusion
        assert len(results) > 0, "No hybrid search results found"
        # First result should be most relevant (has USB, laser, and measurement)
        assert results[0]["doc_id"] in ["hybrid_001", "hybrid_003"]

    def test_empty_index_search(self, index_manager):
        """Test searching empty indexes returns empty results gracefully."""
        # Don't add any documents

        # Test all search types with empty index
        vector_results = index_manager.search_vector("test query", top_k=5)
        keyword_results = index_manager.search_keyword("test query", top_k=5)
        hybrid_results = index_manager.hybrid_search("test query", top_k=5)

        # All should return empty lists, not errors
        assert vector_results == []
        assert keyword_results == []
        assert hybrid_results == []

    def test_search_result_limit(self, index_manager):
        """Test that top_k parameter limits results correctly."""
        # Add multiple documents
        for i in range(10):
            success = index_manager.add_document(
                doc_id=f"limit_test_{i:03d}",
                content=f"Test document number {i} about measurement devices",
                metadata={"index": i},
                index_types=IndexType.BOTH
            )
            assert success

        # Test different top_k values
        results_3 = index_manager.search_vector("measurement", top_k=3)
        results_5 = index_manager.search_vector("measurement", top_k=5)
        results_20 = index_manager.search_vector("measurement", top_k=20)

        assert len(results_3) == 3
        assert len(results_5) == 5
        assert len(results_20) == 10  # Only 10 docs available

    def test_document_update_search(self, index_manager):
        """Test that updated documents are searchable with new content."""
        doc_id = "update_test_001"

        # Add initial document
        success = index_manager.add_document(
            doc_id=doc_id,
            content="Original content about temperature sensors",
            metadata={"version": 1},
            index_types=IndexType.BOTH
        )
        assert success

        # Search for original content
        results = index_manager.search_keyword("temperature", top_k=3)
        assert len(results) > 0
        assert "temperature" in results[0]["content"].lower()

        # Update document with new content
        success = index_manager.update_document(
            doc_id=doc_id,
            content="Updated content about laser power meters",
            metadata={"version": 2},
            index_types=IndexType.BOTH
        )
        assert success

        # Search for old content - should not find
        results = index_manager.search_keyword("temperature", top_k=3)
        assert len(results) == 0 or doc_id not in [r["doc_id"] for r in results]

        # Search for new content - should find
        results = index_manager.search_keyword("laser power", top_k=3)
        assert len(results) > 0
        assert results[0]["doc_id"] == doc_id
        assert "laser" in results[0]["content"].lower()

    def test_special_characters_search(self, index_manager):
        """Test search with special characters doesn't crash."""
        # Add document with special characters
        doc_id = "special_001"
        content = "Model PM-100 (USB/RS232) with 50µm wavelength @ 25°C"

        success = index_manager.add_document(
            doc_id=doc_id,
            content=content,
            metadata={"model": "PM-100"},
            index_types=IndexType.KEYWORD
        )
        assert success

        # Test various special character queries
        special_queries = [
            "PM-100",
            "USB/RS232",
            "50µm",
            "@25°C",
            "(USB)"
        ]

        for query in special_queries:
            # Should not crash
            results = index_manager.search_keyword(query, top_k=3)
            assert isinstance(results, list)  # May or may not find results

    @pytest.mark.requires_api
    def test_real_embeddings_search(self, index_manager):
        """Test with real OpenAI embeddings (not mocked)."""
        # This test uses real embeddings to ensure integration works
        docs = [
            {
                "id": "real_001",
                "content": "High-precision laser interferometer for nanometer measurements",
                "topic": "laser"
            },
            {
                "id": "real_002",
                "content": "Thermal imaging camera for temperature distribution analysis",
                "topic": "thermal"
            },
            {
                "id": "real_003",
                "content": "Ultrasonic thickness gauge for material inspection",
                "topic": "ultrasonic"
            }
        ]

        # Add documents with real embeddings
        for doc in docs:
            success = index_manager.add_document(
                doc_id=doc["id"],
                content=doc["content"],
                metadata={"topic": doc["topic"]},
                index_types=IndexType.VECTOR
            )
            assert success, f"Failed to add {doc['id']}"

        # Test semantic search - should find laser document
        results = index_manager.search_vector("optical measurement precision", top_k=3)
        assert len(results) > 0
        # First result should be laser doc (most semantically similar)
        assert results[0]["doc_id"] == "real_001"

        # Test another semantic search - should find thermal document
        results = index_manager.search_vector("heat detection imaging", top_k=3)
        assert len(results) > 0
        assert results[0]["doc_id"] == "real_002"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
