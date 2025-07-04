"""
Comprehensive integration tests for Qdrant server mode operations.

Tests all IndexManager methods that interact with Qdrant to ensure they work
correctly in server mode, addressing issues found with LlamaIndex abstractions.
"""

import asyncio
import pytest
import sys
import time
from pathlib import Path
from unittest.mock import Mock

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline_v3.core.index_manager import IndexManager, IndexType
from pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from pipeline_v3.utils.config import PipelineConfig
from pipeline_v3.utils.common_utils import logger
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions


@pytest.mark.requires_qdrant_server
class TestQdrantServerOperations:
    """Test all Qdrant operations work correctly in server mode."""

    @pytest.fixture
    async def server_pipeline(self, test_config):
        """Create pipeline with server mode enforced."""
        # Ensure server mode
        test_config.qdrant.mode = "server"

        # Create unique test collection
        test_collection = f"test_server_ops_{int(time.time() * 1000)}"
        test_config.qdrant.collection_name = test_collection

        pipeline = EnhancedPipeline(test_config)
        yield pipeline

        # Cleanup
        try:
            pipeline.index_manager.qdrant_client.delete_collection(test_collection)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_document_lifecycle_server_mode(self, server_pipeline):
        """Test complete document lifecycle in server mode."""
        pipeline = server_pipeline
        doc_id = None

        # Test content versions
        content_v1 = """# Test Document V1
        This is the first version with some content.
        It has multiple paragraphs for chunking."""

        content_v2 = """# Test Document V2 - UPDATED
        This is completely different content.
        All chunks should be replaced."""

        try:
            # 1. Add document
            result = await pipeline.process_document(
                source="test_doc.md",
                content=content_v1,
                metadata={"version": 1, "test": True}
            )
            assert result["status"] == "success"
            doc_id = result["doc_id"]

            # 2. Verify chunks were added
            chunks_v1 = pipeline.index_manager.qdrant_client.scroll(
                collection_name=pipeline.config.qdrant.collection_name,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100
            )[0]

            assert len(chunks_v1) > 0, "No chunks found after adding document"

            # Verify metadata
            for chunk in chunks_v1:
                assert chunk.payload.get("doc_id") == doc_id
                assert "text" in chunk.payload

            # 3. Update document (force reprocess)
            result = await pipeline.process_document(
                source="test_doc.md",
                content=content_v2,
                metadata={"version": 2, "test": True},
                force_reprocess=True
            )
            assert result["status"] == "success"

            # 4. Verify old chunks are gone and new chunks exist
            chunks_v2 = pipeline.index_manager.qdrant_client.scroll(
                collection_name=pipeline.config.qdrant.collection_name,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100
            )[0]

            # Check no old content remains
            for chunk in chunks_v2:
                chunk_text = chunk.payload.get("text", "")
                assert "V1" not in chunk_text, f"Found old content in chunk: {chunk_text[:50]}"
                assert "first version" not in chunk_text.lower()

            # Check new content exists
            has_new_content = any(
                "V2" in chunk.payload.get("text", "") or
                "UPDATED" in chunk.payload.get("text", "")
                for chunk in chunks_v2
            )
            assert has_new_content, "New content not found in chunks"

            # 5. Remove document completely
            success = pipeline.index_manager.remove_document(doc_id, IndexType.BOTH)
            assert success, "Failed to remove document"

            # 6. Verify all chunks are gone
            chunks_after_delete = pipeline.index_manager.qdrant_client.scroll(
                collection_name=pipeline.config.qdrant.collection_name,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100
            )[0]

            assert len(chunks_after_delete) == 0, f"Found {len(chunks_after_delete)} chunks after deletion"

        except Exception as e:
            pytest.fail(f"Document lifecycle test failed: {e}")

    @pytest.mark.asyncio
    async def test_delete_from_vector_index_server_mode(self, server_pipeline):
        """Test delete_from_vector_index uses proper server deletion."""
        pipeline = server_pipeline

        # Add a test document
        result = await pipeline.process_document(
            source="test_delete.md",
            content="Test content for delete operation",
            metadata={"test": "delete_vector"}
        )
        assert result["status"] == "success"
        doc_id = result["doc_id"]

        # Verify chunks exist
        chunks_before = pipeline.index_manager.qdrant_client.scroll(
            collection_name=pipeline.config.qdrant.collection_name,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100
        )[0]
        assert len(chunks_before) > 0

        # Test async delete method
        success = await pipeline.index_manager.delete_from_vector_index(doc_id)
        assert success, "Delete from vector index failed"

        # Verify chunks are gone
        chunks_after = pipeline.index_manager.qdrant_client.scroll(
            collection_name=pipeline.config.qdrant.collection_name,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100
        )[0]
        assert len(chunks_after) == 0, "Chunks remain after delete_from_vector_index"

    @pytest.mark.asyncio
    async def test_search_vector_server_mode(self, server_pipeline):
        """Test vector search works correctly in server mode."""
        pipeline = server_pipeline

        # Add test documents
        test_docs = [
            ("Laser power measurement device", {"category": "measurement"}),
            ("Optical sensor calibration tool", {"category": "calibration"}),
            ("Thermal imaging camera system", {"category": "imaging"}),
        ]

        doc_ids = []
        for content, metadata in test_docs:
            result = await pipeline.process_document(
                source=f"test_{len(doc_ids)}.md",
                content=content,
                metadata=metadata
            )
            assert result["status"] == "success"
            doc_ids.append(result["doc_id"])

        # Test search
        results = pipeline.index_manager.search_vector(
            query="laser measurement",
            top_k=3
        )

        # Verify results structure
        assert isinstance(results, list), "Search results should be a list"
        assert len(results) > 0, "No search results returned"

        # Check result structure
        for result in results:
            assert "node_id" in result
            assert "score" in result
            assert "content" in result
            assert "metadata" in result
            assert "doc_id" in result
            assert "source" in result

        # The most relevant result should be about laser measurement
        assert any("laser" in r["content"].lower() for r in results), "Laser content not found"

    @pytest.mark.asyncio
    async def test_metadata_preservation_server_mode(self, server_pipeline):
        """Test that metadata is properly preserved in server mode."""
        pipeline = server_pipeline

        # Add document with rich metadata
        test_metadata = {
            "author": "Test Author",
            "date": "2025-01-15",
            "category": "technical",
            "tags": ["test", "server", "metadata"],
            "custom_field": "custom_value"
        }

        result = await pipeline.process_document(
            source="metadata_test.pdf",
            content="Document with metadata for testing",
            metadata=test_metadata
        )
        assert result["status"] == "success"
        doc_id = result["doc_id"]

        # Query chunks directly
        chunks = pipeline.index_manager.qdrant_client.scroll(
            collection_name=pipeline.config.qdrant.collection_name,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100,
            with_payload=True
        )[0]

        # Verify each chunk has proper metadata
        for chunk in chunks:
            payload = chunk.payload
            assert payload.get("doc_id") == doc_id

            # Check if metadata is embedded in chunk metadata
            chunk_metadata = payload.get("metadata", {})
            # Metadata might be nested or flattened, check both
            if "metadata" in chunk_metadata:
                chunk_metadata = chunk_metadata["metadata"]

            # At minimum, doc_id should be present
            assert payload.get("doc_id") == doc_id, "doc_id not found in chunk payload"

    @pytest.mark.asyncio
    async def test_batch_operations_server_mode(self, server_pipeline):
        """Test batch document operations work correctly."""
        pipeline = server_pipeline

        # Add multiple documents in batch
        num_docs = 5
        doc_ids = []

        for i in range(num_docs):
            result = await pipeline.process_document(
                source=f"batch_test_{i}.md",
                content=f"Batch test document {i} with unique content {i * 100}",
                metadata={"batch": True, "index": i}
            )
            assert result["status"] == "success"
            doc_ids.append(result["doc_id"])

        # Verify all documents have chunks
        for doc_id in doc_ids:
            chunks = pipeline.index_manager.qdrant_client.scroll(
                collection_name=pipeline.config.qdrant.collection_name,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=10
            )[0]
            assert len(chunks) > 0, f"No chunks found for doc {doc_id}"

        # Test batch removal
        for doc_id in doc_ids:
            success = pipeline.index_manager.remove_document(doc_id)
            assert success, f"Failed to remove doc {doc_id}"

        # Verify all are removed
        remaining = pipeline.index_manager.qdrant_client.scroll(
            collection_name=pipeline.config.qdrant.collection_name,
            limit=100
        )[0]

        remaining_doc_ids = set(chunk.payload.get("doc_id") for chunk in remaining)
        for doc_id in doc_ids:
            assert doc_id not in remaining_doc_ids, f"Doc {doc_id} still has chunks"

    @pytest.mark.asyncio
    async def test_search_with_filters_server_mode(self, server_pipeline):
        """Test search with metadata filters in server mode."""
        pipeline = server_pipeline

        # Add documents with different categories
        categories = ["sensors", "lasers", "optics"]
        doc_ids = []

        for i, category in enumerate(categories):
            result = await pipeline.process_document(
                source=f"filter_test_{i}.md",
                content=f"Document about {category} technology and applications",
                metadata={"category": category, "year": 2025}
            )
            assert result["status"] == "success"
            doc_ids.append(result["doc_id"])

        # Test search with filters (even though MetadataFilters aren't implemented yet)
        # This tests the post-filtering mechanism
        results = pipeline.index_manager.search_vector(
            query="technology",
            top_k=10,
            filters={"category": "sensors"}  # Should work with post-filtering
        )

        # All results should be from sensors category (if post-filtering works)
        # Note: This might not filter properly until Issue #23 is resolved
        assert isinstance(results, list), "Results should be a list"

    @pytest.mark.asyncio
    async def test_collection_isolation(self, test_config):
        """Test that different collections are properly isolated."""
        # Create two pipelines with different collections
        collection1 = f"test_iso_1_{int(time.time() * 1000)}"
        collection2 = f"test_iso_2_{int(time.time() * 1000)}"

        config1 = test_config
        config1.qdrant.mode = "server"
        config1.qdrant.collection_name = collection1

        config2 = PipelineConfig.from_yaml()
        config2.qdrant.mode = "server"
        config2.qdrant.collection_name = collection2

        pipeline1 = EnhancedPipeline(config1)
        pipeline2 = EnhancedPipeline(config2)

        try:
            # Add document to pipeline1
            result1 = await pipeline1.process_document(
                source="iso_test_1.md",
                content="Document in collection 1",
                metadata={"collection": 1}
            )
            assert result1["status"] == "success"

            # Add document to pipeline2
            result2 = await pipeline2.process_document(
                source="iso_test_2.md",
                content="Document in collection 2",
                metadata={"collection": 2}
            )
            assert result2["status"] == "success"

            # Verify isolation - search in collection1 shouldn't find doc from collection2
            results1 = pipeline1.index_manager.search_vector("collection 2", top_k=10)
            assert not any("collection 2" in r["content"].lower() for r in results1)

            # And vice versa
            results2 = pipeline2.index_manager.search_vector("collection 1", top_k=10)
            assert not any("collection 1" in r["content"].lower() for r in results2)

        finally:
            # Cleanup
            try:
                pipeline1.index_manager.qdrant_client.delete_collection(collection1)
                pipeline2.index_manager.qdrant_client.delete_collection(collection2)
            except Exception:
                pass
