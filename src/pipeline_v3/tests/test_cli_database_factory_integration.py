"""
Test CLI DatabaseFactory Integration - Phase 4.2.1a
Tests that CLI management properly uses DatabaseFactory pattern for both SQLite and PostgreSQL.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with proper module path handling
try:
    from cli.management import PipelineCLI
    from core.database_factory import DatabaseFactory
    from utils.config import PipelineConfig
except ImportError:
    # If direct import fails, try absolute import from project root
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.pipeline_v3.cli.management import PipelineCLI
    from src.pipeline_v3.core.database_factory import DatabaseFactory
    from src.pipeline_v3.utils.config import PipelineConfig


class TestCLIDatabaseFactoryIntegration:
    """Test CLI integration with DatabaseFactory pattern."""

    @pytest.fixture
    def sqlite_config(self):
        """Create test config with SQLite backend."""
        config = PipelineConfig()
        config.database.backend = "sqlite"
        return config

    @pytest.fixture
    def postgresql_config(self):
        """Create test config with PostgreSQL backend."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        config.database.postgresql.host = "localhost"
        config.database.postgresql.port = 5432
        config.database.postgresql.database = "test_db"
        config.database.postgresql.user = "test_user"
        config.database.postgresql.password = "test_pass"  # pragma: allowlist secret
        return config

    @pytest.mark.asyncio
    async def test_cli_uses_database_factory_sqlite(self, sqlite_config):
        """Test CLI uses DatabaseFactory for SQLite backend."""
        with patch('src.pipeline_v3.cli.management.DatabaseFactory') as mock_factory_class:
            # Setup mock factory
            mock_factory = MagicMock()
            mock_factory.backend = "sqlite"
            mock_factory.validate_backend_configuration.return_value = True
            mock_factory.create_all.return_value = {
                "registry": MagicMock(),
                "keyword_index": MagicMock(),
                "job_manager": MagicMock(),
                "fingerprint_manager": MagicMock(),
            }
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = sqlite_config

            with patch('cli.management.IndexManager') as mock_index_manager, \
                 patch('cli.management.DocumentQueue') as mock_doc_queue, \
                 patch('cli.management.EnhancedPipeline') as mock_pipeline:

                await cli.initialize()

                # Verify DatabaseFactory was used
                mock_factory_class.assert_called_once_with(sqlite_config)
                mock_factory.validate_backend_configuration.assert_called_once()
                mock_factory.create_all.assert_called_once()

                # Verify adapters were assigned
                assert cli.database_factory == mock_factory
                assert cli.database_adapters == mock_factory.create_all.return_value
                assert cli.registry == mock_factory.create_all.return_value["registry"]
                assert cli.job_manager == mock_factory.create_all.return_value["job_manager"]
                assert cli.fingerprint_manager == mock_factory.create_all.return_value["fingerprint_manager"]

    @pytest.mark.asyncio
    async def test_cli_uses_database_factory_postgresql(self, postgresql_config):
        """Test CLI uses DatabaseFactory for PostgreSQL backend."""
        with patch('cli.management.DatabaseFactory') as mock_factory_class:
            # Setup mock factory
            mock_factory = MagicMock()
            mock_factory.backend = "postgresql"
            mock_factory.validate_backend_configuration.return_value = True
            mock_factory.create_all.return_value = {
                "registry": MagicMock(),
                "keyword_index": MagicMock(),
                "job_manager": MagicMock(),
                "fingerprint_manager": MagicMock(),
            }
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = postgresql_config

            with patch('cli.management.IndexManager') as mock_index_manager, \
                 patch('cli.management.DocumentQueue') as mock_doc_queue, \
                 patch('cli.management.EnhancedPipeline') as mock_pipeline:

                await cli.initialize()

                # Verify DatabaseFactory was used
                mock_factory_class.assert_called_once_with(postgresql_config)
                mock_factory.validate_backend_configuration.assert_called_once()
                mock_factory.create_all.assert_called_once()

                # Verify backend is PostgreSQL
                assert cli.database_factory.backend == "postgresql"

    @pytest.mark.asyncio
    async def test_cli_handles_invalid_backend_config(self, sqlite_config):
        """Test CLI handles invalid backend configuration."""
        with patch('cli.management.DatabaseFactory') as mock_factory_class:
            # Setup mock factory that fails validation
            mock_factory = MagicMock()
            mock_factory.backend = "invalid"
            mock_factory.validate_backend_configuration.return_value = False
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = sqlite_config

            # Should raise ConfigLoadError for invalid backend
            from utils.common_utils import ConfigLoadError
            with pytest.raises(ConfigLoadError) as exc_info:
                await cli.initialize()

            assert "Invalid database backend configuration" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cli_cleanup_closes_adapters(self, sqlite_config):
        """Test CLI cleanup properly closes database adapters."""
        with patch('cli.management.DatabaseFactory') as mock_factory_class:
            # Setup mock factory
            mock_factory = MagicMock()
            mock_factory.backend = "sqlite"
            mock_factory.validate_backend_configuration.return_value = True
            mock_adapters = {
                "registry": MagicMock(),
                "keyword_index": MagicMock(),
                "job_manager": MagicMock(),
                "fingerprint_manager": MagicMock(),
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = sqlite_config

            with patch('cli.management.IndexManager'), \
                 patch('cli.management.DocumentQueue'), \
                 patch('cli.management.EnhancedPipeline'):

                await cli.initialize()
                await cli.cleanup()

                # Verify cleanup was called
                mock_factory.close_all.assert_called_once_with(mock_adapters)

    def test_cli_database_factory_import_handling(self):
        """Test CLI handles DatabaseFactory import failures gracefully."""
        with patch('cli.management.DatabaseFactory', None):
            # This should be caught in the import block and CORE_AVAILABLE set to False
            # The actual import happens at module level, so we test the fallback behavior
            from cli.management import CORE_AVAILABLE, DatabaseFactory as ImportedFactory

            # If imports failed, these should be None
            if not CORE_AVAILABLE:
                assert ImportedFactory is None

    @pytest.mark.asyncio
    async def test_cli_adapters_compatibility(self, sqlite_config):
        """Test that CLI adapters maintain compatibility with existing interfaces."""
        with patch('cli.management.DatabaseFactory') as mock_factory_class:
            # Setup mock factory with realistic adapters
            mock_factory = MagicMock()
            mock_factory.backend = "sqlite"
            mock_factory.validate_backend_configuration.return_value = True

            # Create mock adapters that implement expected interfaces
            mock_registry = MagicMock()
            mock_registry.register_document = MagicMock(return_value="doc123")
            mock_registry.get_document = MagicMock()

            mock_job_manager = MagicMock()
            mock_job_manager.add_job = MagicMock(return_value="job123")

            mock_fingerprint_manager = MagicMock()
            mock_fingerprint_manager.get_fingerprint = MagicMock()

            mock_adapters = {
                "registry": mock_registry,
                "keyword_index": MagicMock(),
                "job_manager": mock_job_manager,
                "fingerprint_manager": mock_fingerprint_manager,
            }
            mock_factory.create_all.return_value = mock_adapters
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = sqlite_config

            with patch('cli.management.IndexManager'), \
                 patch('cli.management.DocumentQueue'), \
                 patch('cli.management.EnhancedPipeline'):

                await cli.initialize()

                # Test that adapters work as expected
                doc_id = cli.registry.register_document("test.pdf", "hash123", 1000, 1234567890)
                assert doc_id == "doc123"

                job_id = cli.job_manager.add_job("test_job", {"data": "test"})
                assert job_id == "job123"

                # Verify methods exist and are callable
                assert callable(cli.fingerprint_manager.get_fingerprint)

    @pytest.mark.asyncio
    async def test_cli_logs_backend_information(self, sqlite_config):
        """Test that CLI logs which backend is being used."""
        with patch('cli.management.DatabaseFactory') as mock_factory_class, \
             patch('cli.management.logger') as mock_logger:

            # Setup mock factory
            mock_factory = MagicMock()
            mock_factory.backend = "sqlite"
            mock_factory.validate_backend_configuration.return_value = True
            mock_factory.create_all.return_value = {
                "registry": MagicMock(),
                "keyword_index": MagicMock(),
                "job_manager": MagicMock(),
                "fingerprint_manager": MagicMock(),
            }
            mock_factory_class.return_value = mock_factory

            # Initialize CLI
            cli = PipelineCLI()
            cli.config = sqlite_config

            with patch('cli.management.IndexManager'), \
                 patch('cli.management.DocumentQueue'), \
                 patch('cli.management.EnhancedPipeline'):

                await cli.initialize()

                # Verify backend information is logged
                mock_logger.info.assert_called_with("Initialized CLI with sqlite backend")
