#!/usr/bin/env python3
"""
Test search functionality with Qdrant server mode.

This test verifies that search operations work correctly when
Qdrant serializes node data in _node_content field.
"""

import asyncio
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.enhanced_core import EnhancedPipeline
from utils.config import PipelineConfig
from utils.common_utils import logger


async def test_search_with_server_mode():
    """Test search functionality in server mode."""

    # Force server mode
    config = PipelineConfig()
    config.qdrant.mode = "server"

    # Use a test collection
    config.qdrant.collection_name = "test_search_server_mode"

    pipeline = EnhancedPipeline(config)

    try:
        # Add a test document
        test_content = """
        # Laser Power Measurement Device

        This is a test document for the PM10K laser power meter.

        ## Specifications
        - Model: PM10K
        - Power Range: 0.1mW to 10W
        - Wavelength: 400-1100nm
        - Accuracy: ±2%

        ## Features
        - USB connectivity
        - Real-time measurement
        - Data logging capability
        """

        # Create a temporary test file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write(test_content)
            test_file = f.name

        logger.info("Adding test document...")
        result = await pipeline.process_document(
            source=test_file,
            metadata={
                "doc_type": "datasheet",
                "product": "PM10K",
                "category": "power_meter"
            }
        )

        # Clean up temp file
        import os
        os.unlink(test_file)

        assert result["status"] == "success"
        doc_id = result["doc_id"]
        logger.info(f"Document added: {doc_id}")

        # Wait a moment for indexing
        await asyncio.sleep(1)

        # Test vector search
        logger.info("\nTesting vector search...")
        vector_results = pipeline.search("laser power measurement", search_type="vector", top_k=3)

        assert len(vector_results) > 0, "Vector search returned no results"
        logger.info(f"Vector search found {len(vector_results)} results")

        # Check result structure
        first_result = vector_results[0]
        assert "content" in first_result, "Result missing content field"
        assert "doc_id" in first_result, "Result missing doc_id field"
        assert "source" in first_result, "Result missing source field"
        assert "metadata" in first_result, "Result missing metadata field"
        assert first_result["content"], "Result has empty content"

        logger.info(f"First result content preview: {first_result['content'][:100]}...")
        logger.info(f"Doc ID: {first_result['doc_id']}")

        # Test keyword search
        logger.info("\nTesting keyword search...")
        keyword_results = pipeline.search("PM10K", search_type="keyword", top_k=3)

        assert len(keyword_results) > 0, "Keyword search returned no results"
        logger.info(f"Keyword search found {len(keyword_results)} results")

        # Test hybrid search
        logger.info("\nTesting hybrid search...")
        hybrid_results = pipeline.search("PM10K laser power", search_type="hybrid", top_k=3)

        assert len(hybrid_results) > 0, "Hybrid search returned no results"
        logger.info(f"Hybrid search found {len(hybrid_results)} results")

        # Check hybrid result structure
        for i, result in enumerate(hybrid_results):
            assert "content" in result or "text" in result, f"Result {i} missing content/text"
            content = result.get("content") or result.get("text", "")
            assert content, f"Result {i} has empty content"
            logger.info(f"Result {i}: {content[:80]}...")

        # Test with keywords enhancement
        logger.info("\nTesting with keyword enhancement...")
        with tempfile.NamedTemporaryFile(mode='w', suffix='.md', delete=False) as f:
            f.write("Advanced laser sensor for precision measurements")
            test_file2 = f.name

        result2 = await pipeline.process_document(
            source=test_file2,
            metadata={"doc_type": "datasheet"},
            with_keywords=True
        )

        os.unlink(test_file2)

        assert result2["status"] == "success"

        # Search for the keyword-enhanced document
        await asyncio.sleep(1)
        enhanced_results = pipeline.search("precision sensor", search_type="hybrid", top_k=5)
        logger.info(f"Found {len(enhanced_results)} results with keyword search")

        logger.info("\n✅ All search tests passed!")

        # Clean up
        logger.info("\nCleaning up test documents...")
        from core.index_manager import IndexType
        pipeline.index_manager.remove_document(doc_id, IndexType.BOTH)
        pipeline.index_manager.remove_document(result2["doc_id"], IndexType.BOTH)

    except Exception as e:
        logger.error(f"Test failed: {e}")
        raise
    finally:
        # Clean up collection
        try:
            if hasattr(pipeline.index_manager, 'qdrant_client') and pipeline.index_manager.qdrant_client:
                pipeline.index_manager.qdrant_client.delete_collection(config.qdrant.collection_name)
        except:
            pass


if __name__ == "__main__":
    asyncio.run(test_search_with_server_mode())
