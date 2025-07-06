"""
Test EnhancedPipeline DatabaseFactory Integration - Phase 4.2.1b
Tests that EnhancedPipeline properly uses DatabaseFactory adapters.
"""

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with proper module path handling
try:
    from pipeline.enhanced_core import EnhancedPipeline
    from core.database_factory import DatabaseFactory
    from utils.config import PipelineConfig
except ImportError:
    # If direct import fails, try absolute import from project root
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
    from src.pipeline_v3.core.database_factory import DatabaseFactory
    from src.pipeline_v3.utils.config import PipelineConfig


class TestEnhancedPipelineIntegration:
    """Test EnhancedPipeline integration with DatabaseFactory adapters."""

    @pytest.fixture
    def sqlite_config(self):
        """Create test config with SQLite backend."""
        config = PipelineConfig()
        config.database.backend = "sqlite"
        return config

    @pytest.fixture
    def mock_database_adapters(self):
        """Create mock database adapters that match expected interfaces."""
        mock_registry = MagicMock()
        mock_registry.register_document = MagicMock(return_value="doc123")
        mock_registry.get_document = MagicMock()
        mock_registry.update_document_state = MagicMock()
        mock_registry.get_statistics = MagicMock(return_value={})
        mock_registry.cleanup_orphaned_entries = MagicMock(return_value={})
        mock_registry.close = MagicMock()

        mock_job_manager = MagicMock()
        mock_job_manager.create_job = MagicMock(return_value="job123")
        mock_job_manager.get_job = MagicMock()
        mock_job_manager.update_job_status = MagicMock()
        mock_job_manager.get_job_statistics = MagicMock(return_value={})
        mock_job_manager.cleanup_completed_jobs = MagicMock(return_value={})
        mock_job_manager.close = MagicMock()

        mock_fingerprint_manager = MagicMock()
        mock_fingerprint_manager.get_fingerprint = MagicMock()
        mock_fingerprint_manager.update_fingerprint = MagicMock()
        mock_fingerprint_manager.has_changed = MagicMock()
        mock_fingerprint_manager.cleanup_old_fingerprints = MagicMock(return_value={})
        mock_fingerprint_manager.close = MagicMock()

        mock_keyword_index = MagicMock()
        mock_keyword_index.index_nodes = MagicMock()
        mock_keyword_index.search = MagicMock()
        mock_keyword_index.get_stats = MagicMock(return_value={})

        return {
            "registry": mock_registry,
            "keyword_index": mock_keyword_index,
            "job_manager": mock_job_manager,
            "fingerprint_manager": mock_fingerprint_manager,
        }

    def test_enhanced_pipeline_uses_database_adapters(self, sqlite_config, mock_database_adapters):
        """Test EnhancedPipeline uses provided DatabaseFactory adapters."""
        with patch('pipeline.enhanced_core.DocumentQueue') as mock_doc_queue, \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector') as mock_change_detector:

            # Initialize EnhancedPipeline with database adapters
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Verify adapters were used
            assert pipeline.job_manager == mock_database_adapters["job_manager"]
            assert pipeline.fingerprint_manager == mock_database_adapters["fingerprint_manager"]
            assert pipeline.registry == mock_database_adapters["registry"]

            # Verify other components were still created
            mock_doc_queue.assert_called_once_with(sqlite_config)
            mock_index_manager.assert_called_once()
            mock_change_detector.assert_called_once()

    def test_enhanced_pipeline_falls_back_to_direct_instantiation(self, sqlite_config):
        """Test EnhancedPipeline falls back to direct instantiation without adapters."""
        with patch('pipeline.enhanced_core.JobManager') as mock_job_manager, \
             patch('pipeline.enhanced_core.FingerprintManager') as mock_fingerprint_manager, \
             patch('pipeline.enhanced_core.DocumentRegistry') as mock_registry, \
             patch('pipeline.enhanced_core.DocumentQueue') as mock_doc_queue, \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector') as mock_change_detector:

            # Initialize EnhancedPipeline without database adapters
            pipeline = EnhancedPipeline(config=sqlite_config)

            # Verify direct instantiation was used
            mock_job_manager.assert_called_once_with(sqlite_config)
            mock_fingerprint_manager.assert_called_once_with(sqlite_config)
            mock_registry.assert_called_once_with(sqlite_config)

            # Verify components were assigned
            assert pipeline.job_manager == mock_job_manager.return_value
            assert pipeline.fingerprint_manager == mock_fingerprint_manager.return_value
            assert pipeline.registry == mock_registry.return_value

    def test_enhanced_pipeline_logs_adapter_source(self, sqlite_config, mock_database_adapters):
        """Test EnhancedPipeline logs which adapter source was used."""
        with patch('pipeline.enhanced_core.logger') as mock_logger, \
             patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.IndexManager'), \
             patch('pipeline.enhanced_core.ChangeDetector'):

            # Test with database adapters
            EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Verify logging with adapters
            mock_logger.info.assert_called_with(
                "EnhancedPipeline initialized with full lifecycle management using DatabaseFactory adapters"
            )

            # Reset mock
            mock_logger.reset_mock()

            # Test without database adapters
            with patch('pipeline.enhanced_core.JobManager'), \
                 patch('pipeline.enhanced_core.FingerprintManager'), \
                 patch('pipeline.enhanced_core.DocumentRegistry'):

                EnhancedPipeline(config=sqlite_config)

                # Verify logging without adapters
                mock_logger.info.assert_called_with(
                    "EnhancedPipeline initialized with full lifecycle management using direct instantiation"
                )

    def test_enhanced_pipeline_backwards_compatibility(self, sqlite_config):
        """Test EnhancedPipeline maintains backwards compatibility with registry parameter."""
        mock_registry = MagicMock()
        mock_index_manager = MagicMock()

        with patch('pipeline.enhanced_core.JobManager'), \
             patch('pipeline.enhanced_core.FingerprintManager'), \
             patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.ChangeDetector'):

            # Initialize with legacy parameters
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                registry=mock_registry,
                index_manager=mock_index_manager
            )

            # Verify legacy parameters were used
            assert pipeline.registry == mock_registry
            assert pipeline.index_manager == mock_index_manager

    def test_enhanced_pipeline_adapter_override_with_registry(self, sqlite_config, mock_database_adapters):
        """Test that explicit registry parameter overrides adapter registry."""
        mock_registry = MagicMock()

        with patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.IndexManager'), \
             patch('pipeline.enhanced_core.ChangeDetector'):

            # Initialize with both adapters and explicit registry
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                registry=mock_registry,  # This should take precedence
                database_adapters=mock_database_adapters
            )

            # Verify explicit registry was used instead of adapter registry
            assert pipeline.registry == mock_registry
            assert pipeline.registry != mock_database_adapters["registry"]

            # But other adapters should still be used
            assert pipeline.job_manager == mock_database_adapters["job_manager"]
            assert pipeline.fingerprint_manager == mock_database_adapters["fingerprint_manager"]

    @pytest.mark.asyncio
    async def test_enhanced_pipeline_shutdown_with_adapters(self, sqlite_config, mock_database_adapters):
        """Test EnhancedPipeline shutdown works with database adapters."""
        with patch('pipeline.enhanced_core.DocumentQueue') as mock_doc_queue, \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector') as mock_change_detector:

            # Mock shutdown method for DocumentQueue
            mock_doc_queue_instance = MagicMock()
            mock_doc_queue_instance.shutdown = AsyncMock()
            mock_doc_queue.return_value = mock_doc_queue_instance

            # Initialize pipeline
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Test shutdown
            await pipeline.shutdown()

            # Verify shutdown was called on all components
            mock_doc_queue_instance.shutdown.assert_called_once()
            mock_database_adapters["job_manager"].close.assert_called_once()
            mock_database_adapters["fingerprint_manager"].close.assert_called_once()
            mock_database_adapters["registry"].close.assert_called_once()

    def test_enhanced_pipeline_adapter_interface_compatibility(self, sqlite_config, mock_database_adapters):
        """Test that pipeline operations work with database adapters."""
        with patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector'):

            # Initialize pipeline
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Test that components can be used as expected
            # These methods should exist and be callable
            assert hasattr(pipeline.job_manager, 'create_job')
            assert hasattr(pipeline.fingerprint_manager, 'get_fingerprint')
            assert hasattr(pipeline.registry, 'register_document')

            # Test actual method calls work
            job_id = pipeline.job_manager.create_job("test_job", {"data": "test"})
            assert job_id == "job123"

            doc_id = pipeline.registry.register_document("test.pdf", "hash123", 1000, 1234567890)
            assert doc_id == "doc123"

            # Verify method was called
            pipeline.fingerprint_manager.get_fingerprint.return_value = "fp123"
            fingerprint = pipeline.fingerprint_manager.get_fingerprint("test.pdf")
            assert fingerprint == "fp123"

    def test_enhanced_pipeline_status_methods_with_adapters(self, sqlite_config, mock_database_adapters):
        """Test that status methods work with database adapters."""
        with patch('pipeline.enhanced_core.DocumentQueue') as mock_doc_queue, \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector') as mock_change_detector:

            # Setup mock return values
            mock_doc_queue.return_value.get_status.return_value = {"active_jobs": 0}
            mock_index_manager.return_value.get_statistics.return_value = {"vector_count": 100}
            mock_change_detector.return_value = MagicMock()

            # Initialize pipeline
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Test comprehensive status
            status = pipeline.get_comprehensive_status()

            # Verify status includes all components
            assert "pipeline" in status
            assert "queue" in status
            assert "jobs" in status
            assert "registry" in status

            # Verify adapter methods were called
            mock_database_adapters["job_manager"].get_job_statistics.assert_called_once()
            mock_database_adapters["registry"].get_statistics.assert_called_once()

    def test_enhanced_pipeline_maintenance_with_adapters(self, sqlite_config, mock_database_adapters):
        """Test maintenance operations work with database adapters."""
        with patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.IndexManager') as mock_index_manager, \
             patch('pipeline.enhanced_core.ChangeDetector'):

            # Setup mock return values for maintenance
            mock_index_manager.return_value.verify_consistency.return_value = {"overall_health": {"score": 95}}

            # Initialize pipeline
            pipeline = EnhancedPipeline(
                config=sqlite_config,
                database_adapters=mock_database_adapters
            )

            # Test maintenance
            import asyncio
            maintenance_result = asyncio.run(pipeline.perform_maintenance())

            # Verify maintenance operations were called on adapters
            mock_database_adapters["registry"].cleanup_orphaned_entries.assert_called_once()
            mock_database_adapters["fingerprint_manager"].cleanup_old_fingerprints.assert_called_once()
            mock_database_adapters["job_manager"].cleanup_completed_jobs.assert_called_once()

            # Verify maintenance results structure
            assert "consistency_check" in maintenance_result
            assert "registry_cleanup" in maintenance_result
            assert "fingerprint_cleanup" in maintenance_result
            assert "job_cleanup" in maintenance_result
