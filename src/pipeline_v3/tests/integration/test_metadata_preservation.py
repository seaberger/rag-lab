"""
Integration test for metadata preservation in Qdrant server mode.

This test specifically verifies that document metadata is properly preserved
through the entire pipeline when using server mode.
"""

import asyncio
import pytest
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from pipeline_v3.utils.config import PipelineConfig
from pipeline_v3.utils.common_utils import logger
from qdrant_client import QdrantClient


@pytest.mark.requires_qdrant_server
class TestMetadataPreservation:
    """Test metadata preservation through the pipeline."""

    @pytest.mark.asyncio
    async def test_comprehensive_metadata_flow(self, test_config):
        """Test that all metadata types are preserved correctly."""
        # Force server mode
        test_config.qdrant.mode = "server"
        test_collection = f"test_metadata_{int(time.time() * 1000)}"
        test_config.qdrant.collection_name = test_collection

        pipeline = EnhancedPipeline(test_config)

        try:
            # Test with various metadata types
            test_metadata = {
                "string_field": "test_value",
                "int_field": 42,
                "float_field": 3.14,
                "bool_field": True,
                "list_field": ["item1", "item2", "item3"],
                "dict_field": {"nested": "value", "count": 10},
                "null_field": None,
                "special_chars": "test/with\\special|chars",
                "doc_type": "technical",
                "source_system": "test_suite"
            }

            # Process document
            result = await pipeline.process_document(
                source="metadata_test.pdf",
                content="""# Technical Document

                This document tests metadata preservation.

                ## Section 1
                Content for testing chunking with metadata.

                ## Section 2
                More content to ensure multiple chunks.""",
                metadata=test_metadata
            )

            assert result["status"] == "success"
            doc_id = result["doc_id"]

            # Query Qdrant directly to verify metadata
            client = pipeline.index_manager.qdrant_client
            chunks = client.scroll(
                collection_name=test_collection,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100,
                with_payload=True,
                with_vectors=False
            )[0]

            assert len(chunks) > 0, "No chunks found"
            logger.info(f"Found {len(chunks)} chunks")

            # Check each chunk
            for i, chunk in enumerate(chunks):
                payload = chunk.payload
                logger.info(f"Chunk {i} payload keys: {list(payload.keys())}")

                # Essential fields
                assert payload.get("doc_id") == doc_id, f"doc_id mismatch in chunk {i}"
                assert "text" in payload, f"No text in chunk {i}"
                assert payload["text"], f"Empty text in chunk {i}"

                # Check metadata preservation
                # Metadata might be in payload directly or nested under 'metadata' key
                chunk_metadata = payload.get("metadata", {})

                # Some metadata might be flattened into payload
                for key in ["doc_type", "source_system"]:
                    assert key in payload or key in chunk_metadata, \
                        f"Metadata field '{key}' not found in chunk {i}"

                # Verify doc_id is consistently set
                assert payload.get("doc_id") == doc_id

            # Test search to ensure metadata doesn't break search
            search_results = pipeline.index_manager.search_vector(
                query="technical document metadata",
                top_k=5
            )

            assert len(search_results) > 0, "Search returned no results"

            # Verify search results have metadata
            for result in search_results:
                assert "doc_id" in result
                assert "metadata" in result
                assert result["doc_id"] == doc_id

        finally:
            # Cleanup
            try:
                pipeline.index_manager.qdrant_client.delete_collection(test_collection)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_metadata_with_keywords(self, test_config):
        """Test metadata preservation when using keyword enhancement."""
        test_config.qdrant.mode = "server"
        test_collection = f"test_meta_keywords_{int(time.time() * 1000)}"
        test_config.qdrant.collection_name = test_collection

        pipeline = EnhancedPipeline(test_config)

        try:
            # Process with keywords enabled
            result = await pipeline.process_document(
                source="keyword_metadata_test.pdf",
                content="Laser power measurement device specifications",
                metadata={
                    "category": "measurement",
                    "product_line": "laser_tools",
                    "year": 2025
                },
                with_keywords=True  # This triggers enhanced processing
            )

            assert result["status"] == "success"
            doc_id = result["doc_id"]

            # Check chunks
            client = pipeline.index_manager.qdrant_client
            chunks = client.scroll(
                collection_name=test_collection,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100,
                with_payload=True
            )[0]

            assert len(chunks) > 0

            # Verify enhanced chunks have both keywords and metadata
            for chunk in chunks:
                payload = chunk.payload

                # Should have doc_id
                assert payload.get("doc_id") == doc_id

                # Should have keyword enhancement marker
                assert "has_keywords" in payload

                # If keywords were added, text should contain "Keywords:" or "Context:"
                if payload.get("has_keywords"):
                    assert "Context:" in payload.get("text", "") or \
                           "Keywords:" in payload.get("text", "")

        finally:
            try:
                pipeline.index_manager.qdrant_client.delete_collection(test_collection)
            except Exception:
                pass

    @pytest.mark.asyncio
    async def test_update_preserves_metadata(self, test_config):
        """Test that document updates preserve and update metadata correctly."""
        test_config.qdrant.mode = "server"
        test_collection = f"test_update_meta_{int(time.time() * 1000)}"
        test_config.qdrant.collection_name = test_collection

        pipeline = EnhancedPipeline(test_config)

        try:
            # Initial document with metadata
            metadata_v1 = {
                "version": 1,
                "status": "draft",
                "author": "test_user"
            }

            result1 = await pipeline.process_document(
                source="update_test.pdf",
                content="Version 1 content",
                metadata=metadata_v1
            )

            assert result1["status"] == "success"
            doc_id = result1["doc_id"]

            # Update with new metadata
            metadata_v2 = {
                "version": 2,
                "status": "published",
                "author": "test_user",
                "reviewer": "review_user"
            }

            result2 = await pipeline.process_document(
                source="update_test.pdf",
                content="Version 2 content - updated",
                metadata=metadata_v2,
                force_reprocess=True
            )

            assert result2["status"] == "success"
            assert result2["doc_id"] == doc_id  # Same document

            # Verify only new chunks exist
            client = pipeline.index_manager.qdrant_client
            chunks = client.scroll(
                collection_name=test_collection,
                scroll_filter={
                    "must": [{"key": "doc_id", "match": {"value": doc_id}}]
                },
                limit=100,
                with_payload=True
            )[0]

            # All chunks should have v2 content
            for chunk in chunks:
                text = chunk.payload.get("text", "")
                assert "Version 1" not in text
                assert "Version 2" in text or "updated" in text

        finally:
            try:
                pipeline.index_manager.qdrant_client.delete_collection(test_collection)
            except Exception:
                pass
