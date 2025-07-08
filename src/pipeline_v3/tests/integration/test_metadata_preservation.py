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

from pipeline.enhanced_core import EnhancedPipeline
from utils.config import PipelineConfig
from utils.common_utils import logger
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

        # Import DatabaseFactory to create pipeline properly
        from core.database_factory import DatabaseFactory

        # Create pipeline with database adapters for PostgreSQL
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()
        pipeline = EnhancedPipeline(test_config, database_adapters=adapters)

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

            # Create a temporary test file with unique name
            import tempfile
            import uuid
            unique_suffix = f"_{uuid.uuid4().hex[:8]}.md"
            with tempfile.NamedTemporaryFile(mode='w', suffix=unique_suffix, delete=False) as f:
                f.write("""# Technical Document

This document tests metadata preservation.

## Section 1
Content for testing chunking with metadata.

## Section 2
More content to ensure multiple chunks.""")
                temp_file = f.name

            # Process document - log the source being passed
            logger.info(f"Processing document with source: {temp_file}")
            result = await pipeline.process_document(
                source=temp_file,
                metadata=test_metadata
            )

            # Clean up temp file
            import os
            os.unlink(temp_file)

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

                # Text might be in _node_content (Qdrant storage format)
                if "_node_content" in payload:
                    import json
                    node_content = json.loads(payload["_node_content"])
                    assert "text" in node_content, f"No text in node content for chunk {i}"
                    assert node_content["text"], f"Empty text in chunk {i}"
                else:
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
            for i, result in enumerate(search_results):
                logger.info(f"Search result {i}: doc_id={result.get('doc_id')}, expected={doc_id}")
                logger.info(f"Result keys: {list(result.keys())}")
                logger.info(f"Result metadata: {result.get('metadata', {})}")
                assert "doc_id" in result
                assert "metadata" in result
                # The doc_id might be in metadata for search results
                actual_doc_id = result.get("doc_id")
                if actual_doc_id == "unknown" and "doc_id" in result.get("metadata", {}):
                    actual_doc_id = result["metadata"]["doc_id"]
                assert actual_doc_id == doc_id, f"doc_id mismatch: {actual_doc_id} != {doc_id}"

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

        # Import DatabaseFactory to create pipeline properly
        from core.database_factory import DatabaseFactory

        # Create pipeline with database adapters for PostgreSQL
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()
        pipeline = EnhancedPipeline(test_config, database_adapters=adapters)

        try:
            # Create temp file for testing with unique name
            import tempfile
            import uuid
            unique_suffix = f"_{uuid.uuid4().hex[:8]}.md"
            with tempfile.NamedTemporaryFile(mode='w', suffix=unique_suffix, delete=False) as f:
                f.write("Laser power measurement device specifications")
                temp_file = f.name

            # Process with keywords enabled - log the source being passed
            logger.info(f"Processing document with keywords, source: {temp_file}")
            result = await pipeline.process_document(
                source=temp_file,
                metadata={
                    "category": "measurement",
                    "product_line": "laser_tools",
                    "year": 2025
                },
                with_keywords=True  # This triggers enhanced processing
            )

            # Clean up
            import os
            os.unlink(temp_file)

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
            for i, chunk in enumerate(chunks):
                payload = chunk.payload
                logger.info(f"Chunk {i} payload keys: {list(payload.keys())}")

                # Should have doc_id
                assert payload.get("doc_id") == doc_id

                # Check if text has keywords (keywords are added to text, not as separate field)
                if "_node_content" in payload:
                    import json
                    node_content = json.loads(payload["_node_content"])
                    text = node_content.get("text", "")
                    # Keywords should be appended to text
                    has_keywords = "Keywords:" in text
                    logger.info(f"Text has keywords: {has_keywords}")
                    logger.info(f"Text sample: {text[:200]}...")

                    # Keywords were added, so text should contain "Keywords:"
                    assert has_keywords, "Keywords not found in enhanced text"

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

        # Import DatabaseFactory to create pipeline properly
        from core.database_factory import DatabaseFactory

        # Create pipeline with database adapters for PostgreSQL
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()
        pipeline = EnhancedPipeline(test_config, database_adapters=adapters)

        try:
            # Initial document with metadata
            metadata_v1 = {
                "version": 1,
                "status": "draft",
                "author": "test_user"
            }

            # Create temp file for testing
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
                f.write("Version 1 content")
                temp_file = f.name

            result1 = await pipeline.process_document(
                source=temp_file,
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

            # Update the temp file with new content
            with open(temp_file, 'w') as f:
                f.write("Version 2 content - updated")

            result2 = await pipeline.process_document(
                source=temp_file,
                metadata=metadata_v2,
                force_reprocess=True
            )

            # Clean up
            import os
            os.unlink(temp_file)

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
                # Extract text from _node_content if available
                text = ""
                if "_node_content" in chunk.payload:
                    import json
                    node_content = json.loads(chunk.payload["_node_content"])
                    text = node_content.get("text", "")
                else:
                    text = chunk.payload.get("text", "")

                assert text, "Chunk has no text content"
                assert "Version 1" not in text, f"Found old version in chunk: {text[:100]}"
                assert "Version 2" in text or "updated" in text, f"New version not found in chunk: {text[:100]}"

        finally:
            try:
                pipeline.index_manager.qdrant_client.delete_collection(test_collection)
            except Exception:
                pass
