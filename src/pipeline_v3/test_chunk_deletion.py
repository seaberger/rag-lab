#!/usr/bin/env python3
"""
Test script to verify proper chunk deletion in Qdrant server mode.

This script tests that when a document is updated or removed, all its chunks
are properly deleted from the Qdrant server before new chunks are added.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions

from pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from pipeline_v3.utils.config import PipelineConfig
from pipeline_v3.utils.common_utils import logger


async def test_chunk_deletion():
    """Test that chunk deletion works properly in server mode."""

    # Load configuration
    config = PipelineConfig.from_yaml()

    # Verify we're in server mode
    if config.qdrant.mode != "server":
        logger.error("This test requires Qdrant server mode. Current mode: " + config.qdrant.mode)
        return False

    # Initialize Qdrant client
    try:
        client = QdrantClient(
            host=config.qdrant.server.host,
            port=config.qdrant.server.port,
            timeout=5
        )

        # Check if server is running
        client.get_collections()
        logger.info("✓ Connected to Qdrant server")

    except Exception as e:
        logger.error(f"Failed to connect to Qdrant server: {e}")
        logger.error("Please start the server with: ./scripts/qdrant_server.sh start")
        return False

    # Create test collection name
    test_collection = f"test_chunks_{int(time.time())}"
    config.qdrant.collection_name = test_collection

    try:
        # Initialize pipeline
        pipeline = EnhancedPipeline(config)
        logger.info(f"✓ Created test collection: {test_collection}")

        # Test document content
        test_content_v1 = """# Test Document Version 1

This is the first version of the test document.
It contains some initial content that will be chunked.

## Section 1
This is section 1 with some text.

## Section 2
This is section 2 with more text.
"""

        test_content_v2 = """# Test Document Version 2 - UPDATED

This is the UPDATED version of the test document.
It has completely different content from version 1.

## New Section A
This is a completely new section A.

## New Section B
This is a completely new section B.

## New Section C
This is a completely new section C with even more content.
"""

        # Process document v1
        logger.info("\n--- Processing document version 1 ---")
        result1 = await pipeline.process_document(
            source="test_doc.md",
            content=test_content_v1,
            metadata={"version": 1}
        )

        if result1["status"] != "success":
            logger.error(f"Failed to process v1: {result1}")
            return False

        doc_id = result1["doc_id"]
        logger.info(f"✓ Processed v1 with doc_id: {doc_id}")

        # Check chunks in Qdrant
        chunks_v1 = client.scroll(
            collection_name=test_collection,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100
        )[0]

        logger.info(f"✓ Version 1 has {len(chunks_v1)} chunks in Qdrant")
        for i, chunk in enumerate(chunks_v1):
            logger.debug(f"  Chunk {i}: {chunk.payload.get('text', '')[:50]}...")

        # Process document v2 (update with force)
        logger.info("\n--- Updating to document version 2 ---")
        result2 = await pipeline.process_document(
            source="test_doc.md",
            content=test_content_v2,
            metadata={"version": 2},
            force_reprocess=True
        )

        if result2["status"] != "success":
            logger.error(f"Failed to process v2: {result2}")
            return False

        logger.info(f"✓ Processed v2 update")

        # Check chunks after update
        chunks_v2 = client.scroll(
            collection_name=test_collection,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100
        )[0]

        logger.info(f"✓ Version 2 has {len(chunks_v2)} chunks in Qdrant")

        # Verify no old chunks remain
        old_chunks_found = False
        for chunk in chunks_v2:
            chunk_text = chunk.payload.get("text", "")
            if "Version 1" in chunk_text or "section 1" in chunk_text.lower():
                logger.error(f"❌ Found old chunk that should have been deleted: {chunk_text[:50]}...")
                old_chunks_found = True

        if old_chunks_found:
            logger.error("❌ TEST FAILED: Old chunks were not properly deleted")
            return False

        # Verify new chunks exist
        new_chunks_found = False
        for chunk in chunks_v2:
            chunk_text = chunk.payload.get("text", "")
            if "Version 2" in chunk_text or "UPDATED" in chunk_text:
                new_chunks_found = True
                break

        if not new_chunks_found:
            logger.error("❌ TEST FAILED: New chunks were not found")
            return False

        logger.info("✓ All old chunks were deleted and new chunks were added")

        # Test complete removal
        logger.info("\n--- Testing complete document removal ---")
        success = pipeline.index_manager.remove_document(doc_id)

        if not success:
            logger.error("❌ Failed to remove document")
            return False

        # Verify no chunks remain
        chunks_after_delete = client.scroll(
            collection_name=test_collection,
            scroll_filter={
                "must": [{"key": "doc_id", "match": {"value": doc_id}}]
            },
            limit=100
        )[0]

        if len(chunks_after_delete) > 0:
            logger.error(f"❌ TEST FAILED: {len(chunks_after_delete)} chunks remain after deletion")
            return False

        logger.info("✓ All chunks were successfully deleted")

        return True

    except Exception as e:
        logger.error(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        # Clean up test collection
        try:
            client.delete_collection(test_collection)
            logger.info(f"✓ Cleaned up test collection: {test_collection}")
        except Exception as e:
            logger.warning(f"Failed to clean up test collection: {e}")

        # Clean up pipeline resources
        if 'pipeline' in locals():
            from pipeline_v3.tests.conftest import cleanup_qdrant_resources
            cleanup_qdrant_resources(pipeline, config)


if __name__ == "__main__":
    import time

    logger.info("=== Qdrant Server Mode Chunk Deletion Test ===")
    logger.info("This test verifies that document updates properly delete old chunks\n")

    # Run the async test
    success = asyncio.run(test_chunk_deletion())

    if success:
        logger.info("\n✅ ALL TESTS PASSED - Chunk deletion works correctly in server mode!")
        sys.exit(0)
    else:
        logger.error("\n❌ TESTS FAILED - Chunk deletion has issues in server mode!")
        sys.exit(1)
