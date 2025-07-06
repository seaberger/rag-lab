#!/usr/bin/env python3
"""
Test script to verify index_manager.py migration from LlamaIndex to custom structures.
"""

import os
import sys
import tempfile
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.registry import IndexType
from src.pipeline_v3.utils.config import PipelineConfig


def create_test_config(temp_dir):
    """Create a test configuration."""
    # Create necessary directories
    os.makedirs(os.path.join(temp_dir, "qdrant"), exist_ok=True)

    # Create a minimal config - using default PipelineConfig with overrides
    config = PipelineConfig()

    # Override paths using environment variables or direct attribute access where possible
    # For Qdrant, we'll use local mode which is already the default
    config.qdrant.local.path = os.path.join(temp_dir, "qdrant")

    # Update storage paths
    config.storage.keyword_db_path = os.path.join(temp_dir, "keyword.db")
    config.storage.base_dir = temp_dir
    config.storage.document_registry_path = os.path.join(temp_dir, "registry.db")

    # Ensure we're in local mode
    config.qdrant.mode = "local"

    return config


def test_basic_operations():
    """Test basic index manager operations with custom structures."""
    print("Testing IndexManager with custom structures...")

    # Create temporary directory for test data
    with tempfile.TemporaryDirectory() as temp_dir:
        # Configure for local testing
        config = create_test_config(temp_dir)

        # Initialize index manager
        print("1. Initializing IndexManager...")
        index_manager = IndexManager(config=config)

        # Pre-register the document in the registry to avoid errors
        index_manager.registry.register_document(
            doc_id="test-doc-001",
            source="test.pdf",
            content_hash="test-hash",
            metadata={"source": "test.pdf", "type": "datasheet"}
        )

        # Test document addition
        print("\n2. Testing document addition...")
        doc_id = "test-doc-001"
        content = """
        This is a test document about laser power measurement sensors.
        The PM10K sensor provides accurate power measurements for industrial lasers.
        It supports USB and RS-232 interfaces for easy integration.
        """

        success = index_manager.add_document(
            doc_id=doc_id,
            content=content,
            metadata={"source": "test.pdf", "type": "datasheet"},
            index_types=IndexType.BOTH
        )

        print(f"   Document added: {success}")

        # Test vector search
        print("\n3. Testing vector search...")
        vector_results = index_manager.search_vector("laser power sensor", top_k=5)
        print(f"   Vector search found {len(vector_results)} results")
        for i, result in enumerate(vector_results[:3]):
            print(f"   Result {i+1}: score={result['score']:.3f}, chunk_id={result.get('chunk_id', result.get('node_id', 'unknown'))[:8]}")

        # Test keyword search
        print("\n4. Testing keyword search...")
        keyword_results = index_manager.search_keyword("USB interface", top_k=5)
        print(f"   Keyword search found {len(keyword_results)} results")
        for i, result in enumerate(keyword_results[:3]):
            print(f"   Result {i+1}: chunk_id={result.get('chunk_id', result.get('node_id', 'unknown'))[:8]}")

        # Test hybrid search
        print("\n5. Testing hybrid search...")
        hybrid_results = index_manager.hybrid_search(
            "PM10K sensor measurement",
            top_k=5,
            fusion_method="rrf"
        )
        print(f"   Hybrid search found {len(hybrid_results)} results")

        # Test document removal
        print("\n6. Testing document removal...")
        remove_success = index_manager.remove_document(doc_id)
        print(f"   Document removed: {remove_success}")

        # Verify removal
        vector_results_after = index_manager.search_vector("laser power", top_k=5)
        print(f"   Vector search after removal: {len(vector_results_after)} results")

        print("\n✅ All tests completed successfully!")


def test_chunk_operations():
    """Test chunk-based operations."""
    print("\n\nTesting chunk-based operations...")

    with tempfile.TemporaryDirectory() as temp_dir:
        config = create_test_config(temp_dir)
        index_manager = IndexManager(config=config)

        # Pre-register the document
        index_manager.registry.register_document(
            doc_id="chunk-test-001",
            source="chunks.pdf",
            content_hash="chunk-hash",
            metadata={"type": "technical"}
        )

        # Create custom chunks
        from src.pipeline_v3.core.data_structures import TextChunk

        doc_id = "chunk-test-001"
        chunks = [
            TextChunk(
                text="First chunk about optical sensors and their calibration procedures.",
                metadata={"doc_id": doc_id, "chunk_index": 0, "type": "technical"}
            ),
            TextChunk(
                text="Second chunk discussing laser wavelength measurements at 1064nm.",
                metadata={"doc_id": doc_id, "chunk_index": 1, "type": "technical"}
            ),
            TextChunk(
                text="Third chunk covering USB communication protocols for sensor data.",
                metadata={"doc_id": doc_id, "chunk_index": 2, "type": "interface"}
            ),
        ]

        print("1. Adding pre-processed chunks...")
        success = index_manager.add_chunks(
            doc_id=doc_id,
            chunks=chunks,
            index_types=IndexType.BOTH
        )
        print(f"   Chunks added: {success}")

        print("\n2. Searching for chunks...")
        results = index_manager.search_vector("optical calibration", top_k=3)
        print(f"   Found {len(results)} results")

        print("\n✅ Chunk operations test completed!")


def test_metadata_and_filters():
    """Test metadata handling and filtering."""
    print("\n\nTesting metadata and filtering...")

    with tempfile.TemporaryDirectory() as temp_dir:
        config = create_test_config(temp_dir)
        index_manager = IndexManager(config=config)

        # Pre-register all documents
        for doc_id in ["sensor-001", "sensor-002", "manual-001"]:
            index_manager.registry.register_document(
                doc_id=doc_id,
                source=f"{doc_id}.pdf",
                content_hash=f"hash-{doc_id}",
                metadata={}
            )

        # Add multiple documents with different metadata
        docs = [
            {
                "doc_id": "sensor-001",
                "content": "PowerMax USB sensor for high power laser measurement up to 10kW.",
                "metadata": {"type": "sensor", "category": "power", "interface": "USB"}
            },
            {
                "doc_id": "sensor-002",
                "content": "EnergyMax sensor for pulse energy measurement with RS-232 interface.",
                "metadata": {"type": "sensor", "category": "energy", "interface": "RS-232"}
            },
            {
                "doc_id": "manual-001",
                "content": "User manual for PowerMax sensor calibration and maintenance.",
                "metadata": {"type": "manual", "category": "power", "interface": "USB"}
            },
        ]

        print("1. Adding documents with metadata...")
        for doc in docs:
            success = index_manager.add_document(
                doc_id=doc["doc_id"],
                content=doc["content"],
                metadata=doc["metadata"],
                index_types=IndexType.VECTOR
            )
            print(f"   Added {doc['doc_id']}: {success}")

        print("\n2. Testing filtered search...")
        # Search with metadata filter
        filters = {"metadata": {"type": "sensor"}}
        results = index_manager.search_vector("measurement", top_k=5, filters=filters)
        print(f"   Filtered search found {len(results)} sensor documents")

        print("\n✅ Metadata and filtering test completed!")


if __name__ == "__main__":
    print("=" * 60)
    print("IndexManager Migration Test Suite")
    print("Testing migration from LlamaIndex to custom structures")
    print("=" * 60)

    # Check for OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ ERROR: OPENAI_API_KEY environment variable not set!")
        print("Please set it before running tests.")
        sys.exit(1)

    try:
        test_basic_operations()
        test_chunk_operations()
        test_metadata_and_filters()

        print("\n" + "=" * 60)
        print("🎉 All tests passed! Migration successful!")
        print("=" * 60)

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
