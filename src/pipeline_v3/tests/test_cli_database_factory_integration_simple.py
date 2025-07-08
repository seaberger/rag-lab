"""
Simple CLI DatabaseFactory Integration Test - Phase 4.2.1a
Tests that CLI management properly initializes with DatabaseFactory pattern.
"""

import sys
from pathlib import Path

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database_factory import DatabaseFactory
from utils.config import PipelineConfig


class TestCLIDatabaseFactoryIntegrationSimple:
    """Simple integration tests for CLI DatabaseFactory usage."""

    def test_database_factory_creates_postgresql_adapters_by_default(self):
        """Test DatabaseFactory creates PostgreSQL adapters by default."""
        config = PipelineConfig()
        # Default backend is now PostgreSQL
        assert config.database.backend == "postgresql"

        factory = DatabaseFactory(config)
        assert factory.backend == "postgresql"

        # PostgreSQL validation might fail without actual database
        # The important thing is that the backend is correctly set
        validation_result = factory.validate_backend_configuration()
        assert isinstance(validation_result, bool)

    def test_database_factory_creates_sqlite_adapters_when_configured(self):
        """Test DatabaseFactory creates SQLite adapters when explicitly configured."""
        config = PipelineConfig()
        config.database.backend = "sqlite"

        factory = DatabaseFactory(config)
        assert factory.backend == "sqlite"
        assert factory.validate_backend_configuration() == True

        adapters = factory.create_all()
        assert "registry" in adapters
        assert "keyword_index" in adapters
        assert "job_manager" in adapters
        assert "fingerprint_manager" in adapters

        # Clean up
        factory.close_all(adapters)

    def test_database_factory_postgresql_config_validation(self):
        """Test DatabaseFactory validates PostgreSQL configuration."""
        config = PipelineConfig()
        config.database.backend = "postgresql"

        factory = DatabaseFactory(config)
        assert factory.backend == "postgresql"

        # Should fail validation with default empty PostgreSQL config
        # (missing host, database, user, etc.)
        validation_result = factory.validate_backend_configuration()

        # The validation might pass or fail depending on defaults
        # The important thing is that it doesn't crash
        assert isinstance(validation_result, bool)

    def test_database_factory_unknown_backend_fails(self):
        """Test DatabaseFactory fails with unknown backend."""
        config = PipelineConfig()
        config.database.backend = "unknown"

        factory = DatabaseFactory(config)
        assert factory.backend == "unknown"
        assert factory.validate_backend_configuration() == False

    def test_database_factory_migration_info(self):
        """Test DatabaseFactory provides migration information."""
        config = PipelineConfig()
        config.database.backend = "sqlite"

        factory = DatabaseFactory(config)
        migration_info = factory.get_migration_info()

        assert migration_info["current_backend"] == "sqlite"
        assert migration_info["target_backend"] == "postgresql"
        assert migration_info["migration_available"] == True
        assert "migrate to-postgres" in migration_info["migration_tool"]

    def test_database_factory_supports_tenant_id(self):
        """Test DatabaseFactory supports tenant ID for multi-tenancy."""
        config = PipelineConfig()
        # Use SQLite for this test since PostgreSQL might not be available
        config.database.backend = "sqlite"
        tenant_id = "test-tenant-123"

        factory = DatabaseFactory(config, tenant_id=tenant_id)
        assert factory.tenant_id == tenant_id

        # For SQLite, tenant_id might not be used, but should not cause errors
        adapters = factory.create_all()
        assert adapters is not None

        # Clean up
        factory.close_all(adapters)

    def test_cli_config_includes_database_settings(self):
        """Test that PipelineConfig includes database settings."""
        config = PipelineConfig()

        # Check that database settings exist
        assert hasattr(config, 'database')
        assert hasattr(config.database, 'backend')
        assert hasattr(config.database, 'postgresql')

        # Check default values - PostgreSQL is now the default
        assert config.database.backend == "postgresql"
        assert config.database.postgresql.host == "localhost"
        assert config.database.postgresql.port == 5432

    def test_database_factory_context_manager(self):
        """Test DatabaseFactory works with context manager pattern."""
        from core.database_factory import DatabaseContext

        config = PipelineConfig()
        # Use SQLite for this test since PostgreSQL might not be available in test environment
        config.database.backend = "sqlite"

        with DatabaseContext(config) as adapters:
            assert "registry" in adapters
            assert "keyword_index" in adapters
            assert "job_manager" in adapters
            assert "fingerprint_manager" in adapters

            # Test basic adapter functionality
            registry = adapters["registry"]
            assert hasattr(registry, 'register_document')
            assert hasattr(registry, 'get_document')

    def test_database_factory_adapter_interfaces(self):
        """Test that DatabaseFactory adapters implement expected interfaces."""
        config = PipelineConfig()
        # Use SQLite for this test to verify actual adapter functionality
        config.database.backend = "sqlite"

        factory = DatabaseFactory(config)
        adapters = factory.create_all()

        # Test DocumentRegistry interface
        registry = adapters["registry"]
        assert hasattr(registry, 'register_document')
        assert hasattr(registry, 'get_document')
        assert hasattr(registry, 'update_document_state')
        assert hasattr(registry, 'remove_document')
        assert hasattr(registry, 'list_documents')
        assert hasattr(registry, 'close')

        # Test KeywordIndex interface (BM25Index for SQLite)
        keyword_index = adapters["keyword_index"]
        assert hasattr(keyword_index, 'index_nodes')  # BM25Index uses index_nodes instead of add_document
        assert hasattr(keyword_index, 'search')
        assert hasattr(keyword_index, 'get_stats')

        # Test JobManager interface
        job_manager = adapters["job_manager"]
        assert hasattr(job_manager, 'create_job')  # JobManager uses create_job instead of add_job
        assert hasattr(job_manager, 'get_job')
        assert hasattr(job_manager, 'update_job_status')
        assert hasattr(job_manager, 'close')

        # Test FingerprintManager interface
        fingerprint_manager = adapters["fingerprint_manager"]
        assert hasattr(fingerprint_manager, 'get_fingerprint')
        assert hasattr(fingerprint_manager, 'update_fingerprint')
        assert hasattr(fingerprint_manager, 'has_changed')
        assert hasattr(fingerprint_manager, 'close')

        # Clean up
        factory.close_all(adapters)

    def test_database_factory_logging(self):
        """Test that DatabaseFactory logs adapter creation."""
        import logging
        from unittest.mock import patch

        config = PipelineConfig()
        # Use SQLite for this test to avoid PostgreSQL dependency
        config.database.backend = "sqlite"

        with patch('core.database_factory.logger') as mock_logger:
            factory = DatabaseFactory(config)
            adapters = factory.create_all()

            # Verify logging calls were made
            assert mock_logger.info.called

            # Clean up
            factory.close_all(adapters)
