"""
Multi-backend support tests for Pipeline v3.

These tests verify that the database factory and adapters work correctly
with both SQLite and PostgreSQL backends.
"""

import pytest
import uuid
from datetime import datetime
from pathlib import Path

from conftest import (
    create_test_document_info,
    create_test_job_info,
    create_test_search_data,
)


class TestMultiBackendSupport:
    """Test database operations across both SQLite and PostgreSQL backends."""

    def test_database_factory_creation(self, database_factory_multi):
        """Test that database factory can be created for both backends."""
        assert database_factory_multi is not None
        assert database_factory_multi.backend in ["sqlite", "postgresql"]
        assert database_factory_multi.validate_backend_configuration()

    def test_database_adapters_creation(self, database_adapters_multi, database_factory_multi):
        """Test that all database adapters can be created."""
        adapters = database_adapters_multi

        # Check all required adapters exist
        required_adapters = ["registry", "keyword_index", "job_manager", "fingerprint_manager"]
        for adapter_name in required_adapters:
            assert adapter_name in adapters, f"Missing adapter: {adapter_name}"
            assert adapters[adapter_name] is not None

        print(f"✓ All adapters created for {database_factory_multi.backend} backend")

    def test_document_registry_operations(self, database_adapters_multi, database_factory_multi):
        """Test document registry operations."""
        registry = database_adapters_multi["registry"]
        doc_info = create_test_document_info()

        # Register document
        doc_id = registry.register_document(
            source=doc_info["source"],
            content_hash=doc_info["content_hash"],
            size=doc_info["size"],
            modified_time=doc_info["modified_time"],
            metadata=doc_info["metadata"],
        )

        assert doc_id is not None
        assert isinstance(doc_id, str)

        # Retrieve document
        doc = registry.get_document(doc_id)
        assert doc is not None
        assert doc.source == doc_info["source"]
        assert doc.content_hash == doc_info["content_hash"]

        # Retrieve by source
        doc_by_source = registry.get_document_by_source(doc_info["source"])
        assert doc_by_source is not None
        assert doc_by_source.doc_id == doc_id

        print(f"✓ Document registry operations work for {database_factory_multi.backend}")

    def test_keyword_index_operations(self, database_adapters_multi, database_factory_multi):
        """Test keyword index operations."""
        keyword_index = database_adapters_multi["keyword_index"]
        search_data = create_test_search_data()

        # Add document to index
        keyword_index.add_document(
            doc_id=search_data["doc_id"],
            chunk_id=search_data["chunk_id"],
            text=search_data["text"],
            keywords=search_data["keywords"],
            metadata=search_data["metadata"],
        )

        # Search for content
        results = keyword_index.search("laser", limit=5)
        assert len(results) >= 1

        # Check result structure
        result = results[0]
        expected_fields = ["doc_id", "chunk_id", "text"]
        for field in expected_fields:
            assert field in result, f"Missing field: {field}"

        print(f"✓ Keyword index operations work for {database_factory_multi.backend}")

    def test_job_manager_operations(self, database_adapters_multi, database_factory_multi):
        """Test job manager operations."""
        job_manager = database_adapters_multi["job_manager"]
        job_info = create_test_job_info()

        # Add job
        job_id = job_manager.add_job(
            job_type=job_info["job_type"],
            payload=job_info["payload"],
            priority=job_info["priority"],
        )

        assert job_id is not None

        # Get job stats
        stats = job_manager.get_queue_stats()
        assert "total_jobs" in stats
        assert stats["total_jobs"] >= 1

        print(f"✓ Job manager operations work for {database_factory_multi.backend}")

    def test_fingerprint_manager_operations(self, database_adapters_multi, database_factory_multi):
        """Test fingerprint manager operations."""
        fingerprint_manager = database_adapters_multi["fingerprint_manager"]

        # Create a test file
        test_file = Path(__file__).parent / "test_data" / "test_fingerprint.txt"
        test_file.parent.mkdir(exist_ok=True)
        test_file.write_text("Test content for fingerprinting")

        try:
            # Compute fingerprint
            fingerprint = fingerprint_manager.compute_fingerprint(test_file)
            assert fingerprint is not None
            assert fingerprint.source == str(test_file.resolve())
            assert fingerprint.content_hash is not None

            # Update fingerprint
            success = fingerprint_manager.update_fingerprint(fingerprint)
            assert success

            # Check if changed (should be False since we just updated)
            changed = fingerprint_manager.has_changed(test_file)
            assert not changed

            print(f"✓ Fingerprint manager operations work for {database_factory_multi.backend}")

        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()

    def test_backend_specific_features(self, database_factory_multi, test_tenant_id):
        """Test backend-specific features."""
        backend = database_factory_multi.backend

        if backend == "postgresql":
            # Test PostgreSQL-specific features
            assert database_factory_multi.tenant_id is not None

            # Test migration info
            migration_info = database_factory_multi.get_migration_info()
            assert migration_info["current_backend"] == "postgresql"
            assert migration_info["target_backend"] == "sqlite"
            assert migration_info["migration_available"] is False

            print("✓ PostgreSQL-specific features verified")

        elif backend == "sqlite":
            # Test SQLite-specific features
            migration_info = database_factory_multi.get_migration_info()
            assert migration_info["current_backend"] == "sqlite"
            assert migration_info["target_backend"] == "postgresql"
            assert migration_info["migration_available"] is True

            print("✓ SQLite-specific features verified")

    @pytest.mark.slow
    def test_cross_backend_compatibility(self, database_adapters_multi, database_factory_multi):
        """Test that data structures are compatible across backends."""
        # This test verifies that the same data can be handled by both backends
        # (though not necessarily migrated between them without the migration tool)

        registry = database_adapters_multi["registry"]
        doc_info = create_test_document_info()

        # Test complex metadata handling
        complex_metadata = {
            "nested": {"key": "value", "number": 42},
            "array": ["item1", "item2", "item3"],
            "boolean": True,
            "null_value": None,
        }

        doc_id = registry.register_document(
            source=doc_info["source"],
            content_hash=doc_info["content_hash"],
            size=doc_info["size"],
            modified_time=doc_info["modified_time"],
            metadata=complex_metadata,
        )

        # Retrieve and verify metadata
        doc = registry.get_document(doc_id)
        assert doc.metadata == complex_metadata

        print(f"✓ Complex data structures compatible with {database_factory_multi.backend}")


@pytest.mark.sqlite
class TestSQLiteSpecific:
    """SQLite-specific tests."""

    def test_sqlite_file_paths(self, test_config):
        """Test SQLite file path configuration."""
        from core.database_factory import DatabaseFactory

        factory = DatabaseFactory(test_config)
        assert factory.backend == "sqlite"

        # SQLite should use file paths
        adapters = factory.create_all()

        # Registry should have a database file
        registry = adapters["registry"]
        # Check that it's using SQLite (has a connection to a file)
        assert hasattr(registry, 'storage') or hasattr(registry, 'conn')

        factory.close_all(adapters)


@pytest.mark.postgresql
class TestPostgreSQLSpecific:
    """PostgreSQL-specific tests."""

    def test_postgresql_tenant_isolation(self, postgresql_config):
        """Test PostgreSQL tenant isolation."""
        from core.database_factory import DatabaseFactory

        # Create two factories with different tenant IDs
        tenant1 = str(uuid.uuid4())
        tenant2 = str(uuid.uuid4())

        factory1 = DatabaseFactory(postgresql_config, tenant_id=tenant1)
        factory2 = DatabaseFactory(postgresql_config, tenant_id=tenant2)

        try:
            adapters1 = factory1.create_all()
            adapters2 = factory2.create_all()

            # Add document to tenant 1
            doc_info = create_test_document_info()
            doc_id = adapters1["registry"].register_document(
                source=doc_info["source"],
                content_hash=doc_info["content_hash"],
                size=doc_info["size"],
                modified_time=doc_info["modified_time"],
            )

            # Verify tenant 1 can see the document
            doc1 = adapters1["registry"].get_document(doc_id)
            assert doc1 is not None

            # Verify tenant 2 cannot see the document
            doc2 = adapters2["registry"].get_document(doc_id)
            assert doc2 is None

            print("✓ PostgreSQL tenant isolation working")

        finally:
            factory1.close_all(adapters1)
            factory2.close_all(adapters2)

    def test_postgresql_connection_pooling(self, postgresql_config):
        """Test PostgreSQL connection pooling."""
        from core.database_factory import DatabaseFactory

        factory = DatabaseFactory(postgresql_config)
        assert factory.backend == "postgresql"

        adapters = factory.create_all()

        try:
            # Each adapter should have connection pooling
            registry = adapters["registry"]
            assert hasattr(registry, 'db')
            assert hasattr(registry.db, '_sync_pool') or hasattr(registry.db, '_async_pool')

            print("✓ PostgreSQL connection pooling configured")

        finally:
            factory.close_all(adapters)
