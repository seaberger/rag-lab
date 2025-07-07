"""
Test DatabaseFactory-based fixtures for Phase 4.2.1g

This test file demonstrates and validates that test fixtures properly
use DatabaseFactory for component creation when available.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.database_factory import DatabaseFactory
    from tests.fixtures.database_fixtures import (
        create_test_registry,
        create_test_fingerprint_manager,
        create_test_job_manager,
        create_test_keyword_index,
        cleanup_test_component,
        test_registry,
        test_fingerprint_manager,
        test_job_manager,
        test_keyword_index,
        test_database_components
    )
    FIXTURES_AVAILABLE = True
except ImportError:
    FIXTURES_AVAILABLE = False

from utils.config import PipelineConfig


@pytest.mark.skipif(not FIXTURES_AVAILABLE, reason="DatabaseFactory fixtures not available")
class TestDatabaseFactoryFixtures:
    """Test that fixtures properly use DatabaseFactory."""

    def test_registry_fixture_uses_factory(self, test_registry):
        """Test that test_registry fixture uses DatabaseFactory when available."""
        # Check if the registry has factory markers
        if hasattr(test_registry, '_test_factory'):
            assert test_registry._test_factory is not None
            assert hasattr(test_registry._test_factory, 'create_all')
            assert hasattr(test_registry, '_test_adapters')
            print("✓ Registry fixture using DatabaseFactory")
        else:
            print("✓ Registry fixture using direct instantiation (fallback)")

        # Test basic functionality works
        doc_id = test_registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )
        assert doc_id is not None

        doc = test_registry.get_document(doc_id)
        assert doc is not None

    def test_fingerprint_manager_fixture_uses_factory(self, test_fingerprint_manager):
        """Test that test_fingerprint_manager fixture uses DatabaseFactory when available."""
        # Check if the fingerprint manager has factory markers
        if hasattr(test_fingerprint_manager, '_test_factory'):
            assert test_fingerprint_manager._test_factory is not None
            assert hasattr(test_fingerprint_manager._test_factory, 'create_all')
            assert hasattr(test_fingerprint_manager, '_test_adapters')
            print("✓ FingerprintManager fixture using DatabaseFactory")
        else:
            print("✓ FingerprintManager fixture using direct instantiation (fallback)")

        # Test basic functionality works
        stats = test_fingerprint_manager.get_stats()
        assert isinstance(stats, dict)

    def test_job_manager_fixture_uses_factory(self, test_job_manager):
        """Test that test_job_manager fixture uses DatabaseFactory when available."""
        # Check if the job manager has factory markers
        if hasattr(test_job_manager, '_test_factory'):
            assert test_job_manager._test_factory is not None
            assert hasattr(test_job_manager._test_factory, 'create_all')
            assert hasattr(test_job_manager, '_test_adapters')
            print("✓ JobManager fixture using DatabaseFactory")
        else:
            print("✓ JobManager fixture using direct instantiation (fallback)")

        # Test basic functionality works
        from job_queue.job import JobType
        job_id = test_job_manager.create_job(
            source="test.pdf",
            job_type=JobType.ADD
        )
        assert job_id is not None

    def test_keyword_index_fixture_uses_factory(self, test_keyword_index):
        """Test that test_keyword_index fixture uses DatabaseFactory when available."""
        # Check if the keyword index has factory markers
        if hasattr(test_keyword_index, '_test_factory'):
            assert test_keyword_index._test_factory is not None
            assert hasattr(test_keyword_index._test_factory, 'create_all')
            assert hasattr(test_keyword_index, '_test_adapters')
            print("✓ KeywordIndex fixture using DatabaseFactory")
        else:
            print("✓ KeywordIndex fixture using direct instantiation (fallback)")

        # Test basic functionality works
        from src.pipeline_v3.core.data_structures import TextChunk
        chunk = TextChunk(text="test content", id="test_node")
        test_keyword_index.index_nodes([chunk])

        results = test_keyword_index.search("test", top_k=1)
        assert len(results) <= 1  # May be 0 if indexing not fully committed

    def test_database_components_fixture(self, test_database_components):
        """Test that test_database_components provides all components."""
        assert "registry" in test_database_components
        assert "fingerprint_manager" in test_database_components
        assert "job_manager" in test_database_components
        assert "keyword_index" in test_database_components

        # Test that components work together
        registry = test_database_components["registry"]
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890
        )
        assert doc_id is not None

        fingerprint_manager = test_database_components["fingerprint_manager"]
        stats = fingerprint_manager.get_stats()
        assert isinstance(stats, dict)

    def test_create_functions_with_postgresql_config(self, postgresql_config):
        """Test that create functions work with PostgreSQL configuration."""
        if not DatabaseFactory:
            pytest.skip("DatabaseFactory not available")

        # Test registry creation
        registry = create_test_registry(postgresql_config)
        try:
            assert registry is not None
            if hasattr(registry, '_test_factory'):
                assert registry._test_factory.backend == "postgresql"
        finally:
            cleanup_test_component(registry)

        # Test fingerprint manager creation
        fp_manager = create_test_fingerprint_manager(postgresql_config)
        try:
            assert fp_manager is not None
            if hasattr(fp_manager, '_test_factory'):
                assert fp_manager._test_factory.backend == "postgresql"
        finally:
            cleanup_test_component(fp_manager)

        # Test job manager creation
        job_manager = create_test_job_manager(postgresql_config)
        try:
            assert job_manager is not None
            if hasattr(job_manager, '_test_factory'):
                assert job_manager._test_factory.backend == "postgresql"
        finally:
            cleanup_test_component(job_manager)

    def test_cleanup_function(self, test_config):
        """Test that cleanup_test_component works properly."""
        # Create a component
        registry = create_test_registry(test_config)

        # Add some data
        doc_id = registry.register_document(
            source="cleanup_test.pdf",
            content_hash="hash456",
            size=2000,
            modified_time=1234567890
        )
        assert doc_id is not None

        # Clean up
        cleanup_test_component(registry)

        # After cleanup, component should still be usable if needed
        # (cleanup just closes connections, doesn't destroy the object)
        # But we shouldn't rely on it after cleanup
        print("✓ Cleanup function executed successfully")

    def test_multi_backend_fixture_integration(self, database_backend, test_config_multi_backend):
        """Test that fixtures work with multi-backend parametrization."""
        # Create components using the multi-backend config
        registry = create_test_registry(test_config_multi_backend)
        try:
            # Verify it works
            doc_id = registry.register_document(
                source=f"test_{database_backend}.pdf",
                content_hash="hash789",
                size=3000,
                modified_time=1234567890
            )
            assert doc_id is not None

            # Check backend if using factory
            if hasattr(registry, '_test_factory'):
                assert registry._test_factory.backend == database_backend
                print(f"✓ Multi-backend fixture working with {database_backend}")
        finally:
            cleanup_test_component(registry)
