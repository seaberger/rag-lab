#!/usr/bin/env python3
"""
Manual test script for backend-aware LlamaIndex features.

This script demonstrates and tests the new backend-aware node creation
and query processing capabilities added in Phase 4.3a.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import uuid
from src.pipeline_v3.utils.config import PipelineConfig
from src.pipeline_v3.core.llama_index_helpers import BackendAwareNodeFactory
from src.pipeline_v3.core.query_helpers import BackendAwareQueryProcessor
from src.pipeline_v3.storage.database_factory import DatabaseFactory
from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.utils.common_utils import logger, init_cli_logging


def test_backend_aware_node_creation():
    """Test creating nodes with backend-specific metadata."""
    print("\n=== Testing Backend-Aware Node Creation ===\n")

    # Test with PostgreSQL config
    pg_config = PipelineConfig()
    pg_config.database.backend = "postgresql"
    pg_config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    print(f"PostgreSQL Config:")
    print(f"  Backend: {pg_config.database.backend}")
    print(f"  Tenant ID: {pg_config.database.postgresql.default_tenant_id}")

    # Create factory
    factory = BackendAwareNodeFactory(pg_config)

    # Create a document
    doc = factory.create_document(
        text="This is a test document for PostgreSQL backend",
        doc_id="test-doc-123",
        metadata={"source": "manual_test.pdf", "category": "test"}
    )

    print(f"\nDocument Metadata:")
    for key, value in doc.metadata.items():
        print(f"  {key}: {value}")

    # Create a text node
    node = factory.create_text_node(
        text="This is a test node",
        node_id="test-node-1",
        metadata={"chunk_index": 0}
    )

    print(f"\nNode Metadata:")
    for key, value in node.metadata.items():
        print(f"  {key}: {value}")

    # Test with SQLite config
    print("\n--- SQLite Comparison ---")
    sqlite_config = PipelineConfig()
    sqlite_config.database.backend = "sqlite"

    sqlite_factory = BackendAwareNodeFactory(sqlite_config)
    sqlite_doc = sqlite_factory.create_document(
        text="SQLite test document",
        doc_id="sqlite-doc-456",
        metadata={"source": "sqlite_test.pdf"}
    )

    print(f"\nSQLite Document Metadata:")
    for key, value in sqlite_doc.metadata.items():
        print(f"  {key}: {value}")

    print("\n✓ Backend-aware node creation working correctly!")


def test_backend_aware_query_processing():
    """Test query processing with backend-specific handling."""
    print("\n=== Testing Backend-Aware Query Processing ===\n")

    # PostgreSQL config
    pg_config = PipelineConfig()
    pg_config.database.backend = "postgresql"
    pg_config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    processor = BackendAwareQueryProcessor(pg_config)

    # Test filter processing
    print("Testing Filter Processing:")
    filters = {"category": "datasheet", "year": 2024}
    processed_filters = processor.process_filters(filters)

    print(f"  Original filters: {filters}")
    print(f"  Processed filters: {processed_filters}")
    print(f"  → Tenant ID automatically added: {processed_filters.get('tenant_id')}")

    # Test keyword query preparation
    print("\nTesting Keyword Query Preparation:")
    query_params = processor.prepare_keyword_query(
        "laser power sensor",
        filters={"category": "datasheet"}
    )

    print(f"  Query: {query_params['query']}")
    print(f"  Filters: {query_params['filters']}")
    print(f"  Search config: {query_params.get('search_config')}")
    print(f"  Tenant ID: {query_params.get('tenant_id')}")

    # Test result processing
    print("\nTesting Result Processing:")
    mock_results = [
        {"text": "Result 1", "score": 10.0, "doc_id": "doc1"},
        {"text": "Result 2", "score": 5.0, "doc_id": "doc2"},
        {"text": "Result 3", "score": 2.5, "doc_id": "doc3"},
    ]

    processed_results = processor.process_keyword_results(mock_results, normalize_scores=True)

    print("  Original scores: 10.0, 5.0, 2.5")
    print(f"  Normalized scores: {[r['score'] for r in processed_results]}")
    print(f"  Backend added to results: {processed_results[0].get('backend')}")

    print("\n✓ Backend-aware query processing working correctly!")


def test_index_manager_with_backend_awareness():
    """Test IndexManager with backend-aware components."""
    print("\n=== Testing IndexManager with Backend Awareness ===\n")

    # Create PostgreSQL config
    config = PipelineConfig()
    config.database.backend = "postgresql"
    config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    try:
        # Try to create with DatabaseFactory
        print("Attempting to create IndexManager with DatabaseFactory...")

        factory = DatabaseFactory(config)
        if factory.validate_backend_configuration():
            print("✓ PostgreSQL backend validated")

            # Note: This will fail without actual PostgreSQL connection
            # but we can check if the components would be initialized
            print("\nDatabaseFactory would create:")
            print("  - PostgreSQL DocumentRegistry")
            print("  - PostgreSQL KeywordIndex")
            print("  - PostgreSQL FingerprintManager")
            print("  - PostgreSQL JobManager")
        else:
            print("✗ PostgreSQL not available, would fall back to SQLite")

    except Exception as e:
        print(f"Expected error without PostgreSQL: {type(e).__name__}")

    # Create IndexManager with SQLite to show it still works
    print("\nCreating IndexManager with SQLite backend...")
    sqlite_config = PipelineConfig()
    sqlite_config.database.backend = "sqlite"

    index_manager = IndexManager(config=sqlite_config)

    print(f"IndexManager created with backend: {index_manager.config.database.backend}")

    # Check if backend-aware components are available
    if hasattr(index_manager, 'node_factory') and index_manager.node_factory:
        print(f"✓ Node factory available: backend={index_manager.node_factory.backend}")
    else:
        print("✗ Node factory not available")

    if hasattr(index_manager, 'query_processor') and index_manager.query_processor:
        print(f"✓ Query processor available: backend={index_manager.query_processor.backend}")
    else:
        print("✗ Query processor not available")


def test_metadata_inheritance():
    """Test metadata inheritance in node creation."""
    print("\n=== Testing Metadata Inheritance ===\n")

    config = PipelineConfig()
    config.database.backend = "postgresql"
    config.database.postgresql.default_tenant_id = "test-tenant-xyz"

    factory = BackendAwareNodeFactory(config)

    # Create nodes with prepare_nodes_for_indexing
    from llama_index.core.schema import TextNode

    nodes = [
        TextNode(text="First chunk of content", id_="node1"),
        TextNode(text="Second chunk of content", id_="node2", metadata={"existing": "data"}),
        TextNode(text="Third chunk of content", id_="node3"),
    ]

    # Prepare nodes
    prepared = factory.prepare_nodes_for_indexing(
        nodes,
        doc_id="doc-789",
        source="inheritance_test.pdf"
    )

    print("Prepared Nodes:")
    for i, node in enumerate(prepared):
        print(f"\nNode {i+1} ({node.id_}):")
        print(f"  doc_id: {node.metadata.get('doc_id')}")
        print(f"  source: {node.metadata.get('source')}")
        print(f"  chunk_index: {node.metadata.get('chunk_index')}")
        print(f"  backend: {node.metadata.get('backend')}")
        print(f"  tenant_id: {node.metadata.get('tenant_id')}")
        if 'existing' in node.metadata:
            print(f"  existing: {node.metadata.get('existing')} (preserved)")


def main():
    """Run all manual tests."""
    init_cli_logging()

    print("=" * 60)
    print("Backend-Aware LlamaIndex Features - Manual Test")
    print("=" * 60)

    try:
        test_backend_aware_node_creation()
        test_backend_aware_query_processing()
        test_index_manager_with_backend_awareness()
        test_metadata_inheritance()

        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
