"""
Search Integration Tests for Pipeline v3

Comprehensive tests for vector, keyword, and hybrid search functionality
to ensure search quality and boost coverage of search-related modules.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from search.hybrid import HybridSearch
from core.index_manager import IndexManager
from storage.keyword_index import BM25Index as KeywordIndex
# Vector storage is handled by Qdrant directly through IndexManager
from utils.config import PipelineConfig


class TestSearchIntegration:
    """Integration tests for search functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def test_config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        config.storage.base_dir = temp_dir
        config.storage.keyword_db_path = os.path.join(temp_dir, "keyword.db")
        config.qdrant.path = os.path.join(temp_dir, "qdrant")
        return config

    @pytest.fixture
    def search_components(self, test_config):
        """Initialize search components."""
        # Initialize components
        from qdrant_client import QdrantClient

        # Create Qdrant client
        qdrant_client = QdrantClient(path=test_config.qdrant.path)

        keyword_index = KeywordIndex(config=test_config)
        index_manager = IndexManager(config=test_config)
        hybrid_searcher = HybridSearch(
            vector_store=qdrant_client,
            keyword_index=keyword_index,
            alpha=0.5,
            collection_name=test_config.qdrant.collection_name
        )

        return {
            "qdrant_client": qdrant_client,
            "keyword_index": keyword_index,
            "index_manager": index_manager,
            "hybrid_searcher": hybrid_searcher
        }

    @pytest.fixture
    def mock_embeddings(self):
        """Mock embedding generation."""
        with patch("openai.OpenAI") as mock_openai_class:
            instance = MagicMock()
            mock_openai_class.return_value = instance

            # Generate consistent embeddings based on text
            async def generate_embedding(text):
                # Simple hash-based embedding for consistency
                hash_val = hash(text) % 1000
                base_embedding = [0.001] * 1536
                # Make it somewhat unique based on text
                for i in range(min(len(text), 100)):
                    base_embedding[i] = (ord(text[i]) / 255.0) * 0.1
                base_embedding[0] = hash_val / 1000.0
                return base_embedding

            instance.get_embeddings = AsyncMock(side_effect=generate_embedding)
            yield instance

    async def add_test_documents(self, search_components, mock_embeddings):
        """Helper to add test documents to indexes."""
        test_docs = [
            {
                "doc_id": "doc1",
                "content": "High-precision laser power meter with USB interface and real-time monitoring",
                "metadata": {
                    "source": "laser_meter.pdf",
                    "product": "PM100USB",
                    "category": "power_meters"
                },
                "keywords": ["laser", "power", "meter", "USB", "monitoring"]
            },
            {
                "doc_id": "doc2",
                "content": "Thermopile sensors for accurate temperature measurement in industrial applications",
                "metadata": {
                    "source": "thermopile.pdf",
                    "product": "TP-500",
                    "category": "sensors"
                },
                "keywords": ["thermopile", "temperature", "sensor", "industrial", "measurement"]
            },
            {
                "doc_id": "doc3",
                "content": "Advanced optical power measurement system with wavelength calibration",
                "metadata": {
                    "source": "optical_system.pdf",
                    "product": "OPM-2000",
                    "category": "optical_systems"
                },
                "keywords": ["optical", "power", "measurement", "wavelength", "calibration"]
            },
            {
                "doc_id": "doc4",
                "content": "USB-powered energy sensor for pulsed laser applications",
                "metadata": {
                    "source": "energy_sensor.pdf",
                    "product": "ES-USB",
                    "category": "sensors"
                },
                "keywords": ["USB", "energy", "sensor", "pulsed", "laser"]
            },
            {
                "doc_id": "doc5",
                "content": "Portable field measurement device with touchscreen interface",
                "metadata": {
                    "source": "field_device.pdf",
                    "product": "FM-Touch",
                    "category": "portable_devices"
                },
                "keywords": ["portable", "field", "measurement", "touchscreen", "device"]
            }
        ]

        # Add documents to both indexes
        for doc in test_docs:
            # Generate embedding
            embedding = await mock_embeddings.get_embeddings(doc["content"])

            # Add document to both indexes using IndexManager.add_document
            from core.registry import IndexType

            # Add to both vector and keyword indexes
            search_components["index_manager"].add_document(
                doc_id=doc["doc_id"],
                content=doc["content"],
                metadata=doc["metadata"],
                index_types=IndexType.BOTH
            )

    @pytest.mark.asyncio
    async def test_vector_search_accuracy(self, search_components, mock_embeddings):
        """Test vector search relevance and accuracy."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Test semantic search
        queries = [
            ("laser measurement device", ["doc1", "doc3", "doc4"]),  # Should find laser-related
            ("temperature sensor", ["doc2"]),  # Should find thermopile
            ("USB interface", ["doc1", "doc4"]),  # Should find USB devices
            ("portable measurement", ["doc5"]),  # Should find field device
        ]

        for query, expected_docs in queries:
            results = search_components["index_manager"].search_vector(
                query=query,
                top_k=3
            )

            # Check if expected docs appear in results
            result_ids = [r["doc_id"] for r in results]
            for expected_id in expected_docs[:2]:  # At least top 2 should match
                assert expected_id in result_ids, f"Expected {expected_id} in results for query '{query}'"

    @pytest.mark.asyncio
    async def test_keyword_search_precision(self, search_components, mock_embeddings):
        """Test keyword search with exact and fuzzy matching."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Test exact keyword matching
        exact_queries = [
            ("USB", ["doc1", "doc4"]),
            ("thermopile", ["doc2"]),
            ("wavelength", ["doc3"]),
            ("touchscreen", ["doc5"])
        ]

        for query, expected_docs in exact_queries:
            results = search_components["index_manager"].search_keyword(
                query=query,
                top_k=5
            )

            result_ids = [r["doc_id"] for r in results]
            for expected_id in expected_docs:
                assert expected_id in result_ids, f"Expected {expected_id} for keyword '{query}'"

        # Test phrase search
        phrase_results = search_components["index_manager"].search_keyword(
            query="power meter",
            top_k=3
        )
        assert len(phrase_results) > 0
        assert "doc1" in [r["doc_id"] for r in phrase_results]

    @pytest.mark.asyncio
    async def test_hybrid_search_fusion(self, search_components, mock_embeddings):
        """Test hybrid search with different fusion methods."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Test query that benefits from both vector and keyword
        query = "USB laser sensor"
        query_embedding = await mock_embeddings.get_embeddings(query)

        # Test RRF fusion
        rrf_results = await search_components["index_manager"].hybrid_search(
            query=query,
            query_embedding=query_embedding,
            top_k=5,
            fusion_method="rrf",
            keyword_weight=0.5
        )

        assert len(rrf_results) > 0
        # USB laser products should rank high
        top_ids = [r["doc_id"] for r in rrf_results[:2]]
        assert "doc1" in top_ids or "doc4" in top_ids

        # Test weighted fusion
        weighted_results = await search_components["index_manager"].hybrid_search(
            query=query,
            query_embedding=query_embedding,
            top_k=5,
            fusion_method="weighted",
            keyword_weight=0.7  # Favor keywords
        )

        assert len(weighted_results) > 0
        # Results might differ based on weighting
        assert weighted_results[0]["score"] > 0

    @pytest.mark.asyncio
    async def test_search_with_filters(self, search_components, mock_embeddings):
        """Test search with metadata filters."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Test category filter
        query_embedding = await mock_embeddings.get_embeddings("measurement device")

        # Filter by category using Qdrant's Filter
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        category_filter = Filter(
            must=[
                FieldCondition(
                    key="category",
                    match=MatchValue(value="sensors")
                )
            ]
        )

        filtered_results = await search_components["vector_store"].search(
            query_embedding=query_embedding,
            top_k=10,
            filters=category_filter
        )

        # Should only return sensors
        for result in filtered_results:
            assert result.payload.get("category") == "sensors"

    @pytest.mark.asyncio
    async def test_search_result_scoring(self, search_components, mock_embeddings):
        """Test search result scoring and normalization."""
        await self.add_test_documents(search_components, mock_embeddings)

        query = "laser power measurement"
        query_embedding = await mock_embeddings.get_embeddings(query)

        # Get results from different search types
        vector_results = search_components["index_manager"].search_vector(
            query_embedding=query_embedding,
            top_k=5
        )

        keyword_results = search_components["index_manager"].search_keyword(
            query=query,
            top_k=5
        )

        hybrid_results = await search_components["index_manager"].hybrid_search(
            query=query,
            query_embedding=query_embedding,
            top_k=5
        )

        # Verify scoring
        for results in [vector_results, keyword_results, hybrid_results]:
            assert len(results) > 0
            # Scores should be normalized between 0 and 1
            for result in results:
                assert 0 <= result["score"] <= 1
            # Results should be sorted by score (descending)
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_empty_index_handling(self, search_components, mock_embeddings):
        """Test search behavior with empty indexes."""
        query = "test query"
        query_embedding = await mock_embeddings.get_embeddings(query)

        # Search empty indexes
        vector_results = search_components["index_manager"].search_vector(
            query_embedding=query_embedding,
            top_k=5
        )

        keyword_results = search_components["index_manager"].search_keyword(
            query=query,
            top_k=5
        )

        # Should return empty lists, not errors
        assert vector_results == []
        assert keyword_results == []

    @pytest.mark.asyncio
    async def test_search_pagination(self, search_components, mock_embeddings):
        """Test search with different top_k values."""
        await self.add_test_documents(search_components, mock_embeddings)

        query = "measurement"
        query_embedding = await mock_embeddings.get_embeddings(query)

        # Test different page sizes
        for top_k in [1, 3, 5, 10]:
            results = await search_components["index_manager"].vector_search(
                query_embedding=query_embedding,
                top_k=top_k
            )

            # Should return at most top_k results
            assert len(results) <= top_k
            # But should return all available if less than top_k
            if top_k > 5:  # We have 5 docs
                assert len(results) == 5

    @pytest.mark.asyncio
    async def test_concurrent_searches(self, search_components, mock_embeddings):
        """Test concurrent search operations."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Create multiple search queries
        queries = [
            "laser power",
            "temperature sensor",
            "USB interface",
            "optical measurement",
            "portable device"
        ]

        # Execute searches concurrently
        tasks = []
        for query in queries:
            query_embedding = await mock_embeddings.get_embeddings(query)
            task = search_components["index_manager"].hybrid_search(
                query=query,
                query_embedding=query_embedding,
                top_k=3
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # All searches should complete successfully
        assert len(results) == len(queries)
        for result in results:
            assert isinstance(result, list)
            assert len(result) > 0

    @pytest.mark.asyncio
    async def test_search_error_recovery(self, search_components, mock_embeddings):
        """Test search error handling and recovery."""
        # Test with invalid query embedding
        invalid_embedding = [0.1] * 100  # Wrong dimension

        with pytest.raises(Exception):
            await search_components["vector_store"].search(
                query_embedding=invalid_embedding,
                top_k=5
            )

        # Test with extremely long query (keyword search)
        very_long_query = " ".join(["word"] * 1000)
        results = search_components["index_manager"].search_keyword(
            query=very_long_query,
            top_k=5
        )

        # Should handle gracefully
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_special_characters(self, search_components, mock_embeddings):
        """Test search with special characters and edge cases."""
        await self.add_test_documents(search_components, mock_embeddings)

        # Test queries with special characters
        special_queries = [
            "PM-100",
            "USB/RS232",
            "measurement & calibration",
            "laser (power)",
            "temp.*sensor"
        ]

        for query in special_queries:
            # Should not crash
            results = search_components["index_manager"].search_keyword(
                query=query,
                top_k=3
            )
            assert isinstance(results, list)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
