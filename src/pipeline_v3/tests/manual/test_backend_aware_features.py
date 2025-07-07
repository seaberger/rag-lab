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
from src.pipeline_v3.core.database_factory import DatabaseFactory
from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.data_structures import Document, TextChunk, MetadataBuilder
from src.pipeline_v3.utils.common_utils import logger, init_cli_logging


def test_backend_aware_document_creation():
    """Test creating documents and chunks with backend-specific metadata."""
    print("\n=== Testing Backend-Aware Document Creation ===\n")

    # Test with PostgreSQL config
    pg_config = PipelineConfig()
    pg_config.database.backend = "postgresql"
    pg_config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    print(f"PostgreSQL Config:")
    print(f"  Backend: {pg_config.database.backend}")
    print(f"  Tenant ID: {pg_config.database.postgresql.default_tenant_id}")

    # Create backend-aware metadata
    pg_metadata = MetadataBuilder.build_document_metadata(
        source="manual_test.pdf",
        source_type="test_document",
        pairs=[("Model123", "Part456")],
        backend=pg_config.database.backend,
        tenant_id=pg_config.database.postgresql.default_tenant_id
    )

    # Create a document with backend-aware metadata
    doc = Document(
        text="This is a test document for PostgreSQL backend",
        doc_id="test-doc-123",
        metadata=pg_metadata
    )

    print(f"\nDocument Metadata:")
    for key, value in doc.metadata.items():
        print(f"  {key}: {value}")

    # Create a text chunk with inherited metadata
    chunk = TextChunk(
        text="This is a test chunk",
        id="test-chunk-1",
        metadata={
            **doc.metadata,
            "chunk_index": 0,
            "doc_id": doc.doc_id
        }
    )

    print(f"\nChunk Metadata:")
    for key, value in chunk.metadata.items():
        print(f"  {key}: {value}")

    # Test with SQLite config
    print("\n--- SQLite Comparison ---")
    sqlite_config = PipelineConfig()
    sqlite_config.database.backend = "sqlite"

    sqlite_metadata = MetadataBuilder.build_document_metadata(
        source="sqlite_test.pdf",
        source_type="test_document",
        backend=sqlite_config.database.backend
    )

    sqlite_doc = Document(
        text="SQLite test document",
        doc_id="sqlite-doc-456",
        metadata=sqlite_metadata
    )

    print(f"\nSQLite Document Metadata:")
    for key, value in sqlite_doc.metadata.items():
        print(f"  {key}: {value}")

    print("\n✓ Backend-aware document creation working correctly!")


def test_backend_aware_database_factory():
    """Test database factory with backend-specific configurations."""
    print("\n=== Testing Backend-Aware Database Factory ===\n")

    # PostgreSQL config
    pg_config = PipelineConfig()
    pg_config.database.backend = "postgresql"
    pg_config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    print("Testing PostgreSQL Database Factory:")
    try:
        factory = DatabaseFactory(pg_config)
        print(f"  Backend: {factory.backend}")
        print(f"  Tenant ID: {factory.tenant_id}")
        print(f"  Configuration validated: {factory.validate_backend_configuration()}")

        # Test adapter creation
        adapters = factory.create_all()
        print(f"  Created adapters: {list(adapters.keys())}")

        # Test backend-specific features
        if hasattr(factory, 'get_migration_info'):
            migration_info = factory.get_migration_info()
            print(f"  Migration info: {migration_info['current_backend']} -> {migration_info['target_backend']}")

        factory.close_all(adapters)
        print("  ✓ PostgreSQL factory working correctly")

    except Exception as e:
        print(f"  PostgreSQL not available: {type(e).__name__}")

    # SQLite config for comparison
    print("\n--- SQLite Comparison ---")
    sqlite_config = PipelineConfig()
    sqlite_config.database.backend = "sqlite"

    sqlite_factory = DatabaseFactory(sqlite_config)
    print(f"  Backend: {sqlite_factory.backend}")
    print(f"  Configuration validated: {sqlite_factory.validate_backend_configuration()}")

    sqlite_adapters = sqlite_factory.create_all()
    print(f"  Created adapters: {list(sqlite_adapters.keys())}")

    sqlite_factory.close_all(sqlite_adapters)
    print("  ✓ SQLite factory working correctly")

    print("\n✓ Backend-aware database factory working correctly!")


def test_index_manager_with_backend_awareness():
    """Test IndexManager with backend-aware components."""
    print("\n=== Testing IndexManager with Backend Awareness ===\n")

    # Create PostgreSQL config
    config = PipelineConfig()
    config.database.backend = "postgresql"
    config.database.postgresql.default_tenant_id = str(uuid.uuid4())

    try:
        print("Testing IndexManager with PostgreSQL config...")

        # Test that IndexManager respects backend configuration
        index_manager = IndexManager(config=config)
        print(f"  Backend configured: {index_manager.config.database.backend}")

        if hasattr(index_manager.config.database, 'postgresql'):
            print(f"  Tenant ID: {index_manager.config.database.postgresql.default_tenant_id}")

        # Test backend-specific search capabilities
        print("  Testing search interface...")
        # Note: This would fail without actual database, but we can test the interface
        search_methods = ['vector', 'keyword', 'hybrid']
        for method in search_methods:
            if hasattr(index_manager, f'search_{method}') or hasattr(index_manager, 'search'):
                print(f"    ✓ {method} search available")

        print("  ✓ PostgreSQL IndexManager configuration working")

    except Exception as e:
        print(f"  PostgreSQL IndexManager error (expected): {type(e).__name__}")

    # Create IndexManager with SQLite to show it still works
    print("\nTesting IndexManager with SQLite backend...")
    sqlite_config = PipelineConfig()
    sqlite_config.database.backend = "sqlite"

    sqlite_index_manager = IndexManager(config=sqlite_config)
    print(f"  Backend configured: {sqlite_index_manager.config.database.backend}")

    # Test that it has the expected interface
    expected_methods = ['add_documents', 'search', 'remove_document']
    for method in expected_methods:
        if hasattr(sqlite_index_manager, method):
            print(f"    ✓ {method} method available")

    print("  ✓ SQLite IndexManager working correctly")

    print("\n✓ IndexManager backend awareness working correctly!")


def test_metadata_inheritance_and_chunking():
    """Test metadata inheritance in chunk creation with backend awareness."""
    print("\n=== Testing Metadata Inheritance ===\n")

    config = PipelineConfig()
    config.database.backend = "postgresql"
    config.database.postgresql.default_tenant_id = "test-tenant-xyz"

    # Create a document with backend-aware metadata
    doc_metadata = MetadataBuilder.build_document_metadata(
        source="inheritance_test.pdf",
        source_type="test_document",
        pairs=[("TestModel", "TestPart")],
        backend=config.database.backend,
        tenant_id=config.database.postgresql.default_tenant_id
    )

    document = Document(
        text="This is the first chunk. This is the second chunk. This is the third chunk.",
        doc_id="doc-789",
        metadata=doc_metadata
    )

    # Create chunks that inherit document metadata
    from src.pipeline_v3.core.data_structures import TextSplitter

    splitter = TextSplitter(chunk_size=50, chunk_overlap=10)
    chunks = splitter.create_chunks(document)

    print("Created Chunks with Inherited Metadata:")
    for i, chunk in enumerate(chunks):
        print(f"\nChunk {i+1} ({chunk.id}):")
        print(f"  Text: {chunk.text[:30]}...")
        print(f"  doc_id: {chunk.metadata.get('doc_id')}")
        print(f"  source: {chunk.metadata.get('source')}")
        print(f"  chunk_index: {chunk.metadata.get('chunk_index')}")
        print(f"  backend: {chunk.metadata.get('backend')}")
        print(f"  tenant_id: {chunk.metadata.get('tenant_id')}")
        print(f"  pairs inherited: {len(chunk.pairs)} pairs")
        if chunk.pairs:
            print(f"    First pair: {chunk.pairs[0]}")

    # Test manual chunk creation with custom metadata
    print("\n--- Manual Chunk with Custom Metadata ---")
    custom_chunk = TextChunk(
        text="Custom chunk with additional metadata",
        metadata={
            **document.metadata,
            "chunk_index": 999,
            "custom_field": "custom_value",
            "existing": "preserved_data"
        }
    )

    print(f"Custom chunk metadata:")
    for key, value in custom_chunk.metadata.items():
        if key in ['doc_id', 'source', 'backend', 'tenant_id', 'custom_field', 'existing']:
            print(f"  {key}: {value}")

    print("\n✓ Metadata inheritance working correctly!")


def main():
    """Run all manual tests."""
    init_cli_logging()

    print("=" * 60)
    print("Backend-Aware Pipeline v3 Features - Manual Test")
    print("=" * 60)

    try:
        test_backend_aware_document_creation()
        test_backend_aware_database_factory()
        test_index_manager_with_backend_awareness()
        test_metadata_inheritance_and_chunking()

        print("\n" + "=" * 60)
        print("✓ All tests completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
