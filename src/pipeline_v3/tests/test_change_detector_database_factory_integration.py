"""
Test ChangeDetector DatabaseFactory Integration - Phase 4.2.1d
Tests that ChangeDetector properly uses DatabaseFactory adapters.
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with proper module path handling
try:
    from core.change_detector import ChangeDetector, ChangeType, UpdateStrategy
    from core.fingerprint import DocumentFingerprint, FingerprintManager
    from core.registry import DocumentRegistry, DocumentState
    from utils.config import PipelineConfig
except ImportError:
    # If direct import fails, try absolute import from project root
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.pipeline_v3.core.change_detector import ChangeDetector, ChangeType, UpdateStrategy
    from src.pipeline_v3.core.fingerprint import DocumentFingerprint, FingerprintManager
    from src.pipeline_v3.core.registry import DocumentRegistry, DocumentState
    from src.pipeline_v3.utils.config import PipelineConfig


class TestChangeDetectorIntegration:
    """Test ChangeDetector integration with DatabaseFactory adapters."""

    @pytest.fixture
    def config(self):
        """Create test config."""
        return PipelineConfig()

    @pytest.fixture
    def mock_fingerprint_manager(self):
        """Create mock fingerprint manager that matches expected interface."""
        mock_fingerprint_manager = MagicMock(spec=FingerprintManager)

        # Setup mock fingerprint
        mock_fingerprint = MagicMock(spec=DocumentFingerprint)
        mock_fingerprint.content_hash = "hash123"
        mock_fingerprint.metadata_hash = "meta123"
        mock_fingerprint.structure_hash = "struct123"
        mock_fingerprint.timestamp = 1234567890
        mock_fingerprint.size = 1000
        mock_fingerprint.chunk_hashes = ["chunk1", "chunk2"]

        mock_fingerprint_manager.compute_fingerprint.return_value = mock_fingerprint
        mock_fingerprint_manager.get_fingerprint.return_value = mock_fingerprint
        mock_fingerprint_manager.close = MagicMock()

        return mock_fingerprint_manager

    @pytest.fixture
    def mock_registry(self):
        """Create mock registry that matches expected interface."""
        mock_registry = MagicMock(spec=DocumentRegistry)

        # Create mock document
        mock_doc = MagicMock()
        mock_doc.doc_id = "doc123"
        mock_doc.source = "test.pdf"
        mock_doc.state = DocumentState.INDEXED
        mock_doc.content_hash = "hash123"

        mock_registry.get_document_by_source.return_value = mock_doc
        mock_registry.list_documents.return_value = [mock_doc]
        mock_registry.close = MagicMock()

        return mock_registry

    def test_change_detector_uses_database_adapters(self, config, mock_registry, mock_fingerprint_manager):
        """Test ChangeDetector uses provided DatabaseFactory adapters."""
        # Initialize ChangeDetector with adapters
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Verify adapters were used
        assert detector.fingerprint_manager == mock_fingerprint_manager
        assert detector.registry == mock_registry

    def test_change_detector_falls_back_to_direct_instantiation(self, config):
        """Test ChangeDetector falls back to direct instantiation without adapters."""
        with patch('core.change_detector.FingerprintManager') as mock_fingerprint_class, \
             patch('core.change_detector.DocumentRegistry') as mock_registry_class:

            # Initialize ChangeDetector without adapters
            detector = ChangeDetector(config=config)

            # Verify direct instantiation was used
            mock_fingerprint_class.assert_called_once_with(config)
            mock_registry_class.assert_called_once_with(config)

            # Verify instances were assigned
            assert detector.fingerprint_manager == mock_fingerprint_class.return_value
            assert detector.registry == mock_registry_class.return_value

    def test_change_detector_logs_adapter_usage(self, config, mock_registry, mock_fingerprint_manager):
        """Test ChangeDetector logs which components were used."""
        with patch('core.change_detector.logger') as mock_logger:
            # Test with adapters
            ChangeDetector(
                config=config,
                registry=mock_registry,
                fingerprint_manager=mock_fingerprint_manager
            )

            # Verify logging with adapters
            mock_logger.info.assert_called_with(
                "ChangeDetector initialized with DatabaseFactory fingerprint_manager, provided registry"
            )

            # Reset mock
            mock_logger.reset_mock()

            # Test without adapters
            with patch('core.change_detector.FingerprintManager'), \
                 patch('core.change_detector.DocumentRegistry'):

                ChangeDetector(config=config)

                # Verify logging without adapters
                mock_logger.info.assert_called_with(
                    "ChangeDetector initialized with direct FingerprintManager, direct DocumentRegistry"
                )

    def test_change_detector_analyze_changes_with_adapters(self, config, mock_registry, mock_fingerprint_manager):
        """Test analyze_changes works with DatabaseFactory adapters."""
        # Setup mocks
        mock_fingerprint_manager.compute_fingerprint.return_value.content_hash = "newhash"
        mock_fingerprint_manager.get_fingerprint.return_value.content_hash = "oldhash"

        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test analyze_changes
        analysis = detector.analyze_changes("test.pdf", "new content")

        # Verify adapters were called
        mock_fingerprint_manager.compute_fingerprint.assert_called_once()
        mock_fingerprint_manager.get_fingerprint.assert_called_once_with("test.pdf")
        mock_registry.get_document_by_source.assert_called_once_with("test.pdf")

        # Verify analysis result - it detected a significant change
        assert analysis.change_type in [ChangeType.MINOR_UPDATE, ChangeType.MAJOR_UPDATE, ChangeType.COMPLETE_REWRITE]
        assert analysis.update_strategy in [UpdateStrategy.INCREMENTAL, UpdateStrategy.FULL_REINDEX]

    def test_change_detector_batch_analyze_with_adapters(self, config, mock_registry, mock_fingerprint_manager):
        """Test batch_analyze_changes works with adapters."""
        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test batch analysis
        documents = [
            {"source": "doc1.pdf", "content": "content1"},
            {"source": "doc2.pdf", "content": "content2"},
        ]

        analyses = detector.batch_analyze_changes(documents)

        # Verify results
        assert len(analyses) == 2
        assert all(hasattr(a, 'change_type') for a in analyses)
        assert all(hasattr(a, 'update_strategy') for a in analyses)

    def test_change_detector_get_update_recommendations_with_adapters(self, config, mock_registry, mock_fingerprint_manager):
        """Test get_update_recommendations works with adapters."""
        # Setup mock registry to return documents with all required attributes
        mock_doc1 = MagicMock()
        mock_doc1.doc_id = "doc1"
        mock_doc1.source = "stale1.pdf"
        mock_doc1.state = DocumentState.STALE
        mock_doc1.content_hash = "hash1"

        mock_doc2 = MagicMock()
        mock_doc2.doc_id = "doc2"
        mock_doc2.source = "new1.pdf"
        mock_doc2.state = DocumentState.NEW
        mock_doc2.content_hash = "hash2"

        mock_registry.list_documents.side_effect = lambda state: {
            DocumentState.STALE: [mock_doc1],
            DocumentState.NEW: [mock_doc2]
        }.get(state, [])

        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test recommendations
        recommendations = detector.get_update_recommendations(time_budget=300.0)

        # Verify registry was called
        mock_registry.list_documents.assert_any_call(DocumentState.STALE)
        mock_registry.list_documents.assert_any_call(DocumentState.NEW)

        # Verify recommendations structure
        assert "recommendations" in recommendations  # Changed from "recommended_documents"
        assert "estimated_time" in recommendations  # Changed from "total_estimated_time"
        assert "time_budget" in recommendations

    def test_change_detector_close_with_adapters(self, config, mock_registry, mock_fingerprint_manager):
        """Test close method works with adapters."""
        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test close
        detector.close()

        # Verify adapters were closed
        mock_fingerprint_manager.close.assert_called_once()
        mock_registry.close.assert_called_once()

    def test_change_detector_backwards_compatibility(self, config, mock_registry):
        """Test ChangeDetector maintains backwards compatibility with registry parameter only."""
        with patch('core.change_detector.FingerprintManager') as mock_fingerprint_class:
            # Initialize with only registry (legacy pattern)
            detector = ChangeDetector(
                config=config,
                registry=mock_registry
            )

            # Verify registry was used
            assert detector.registry == mock_registry

            # Verify FingerprintManager was created directly
            mock_fingerprint_class.assert_called_once_with(config)
            assert detector.fingerprint_manager == mock_fingerprint_class.return_value

    def test_change_detector_partial_adapters(self, config, mock_fingerprint_manager):
        """Test ChangeDetector works with partial adapters (only fingerprint_manager)."""
        with patch('core.change_detector.DocumentRegistry') as mock_registry_class:
            # Initialize with only fingerprint_manager adapter
            detector = ChangeDetector(
                config=config,
                fingerprint_manager=mock_fingerprint_manager
            )

            # Verify fingerprint_manager adapter was used
            assert detector.fingerprint_manager == mock_fingerprint_manager

            # Verify DocumentRegistry was created directly
            mock_registry_class.assert_called_once_with(config)
            assert detector.registry == mock_registry_class.return_value

    def test_enhanced_pipeline_integration(self, config):
        """Test that EnhancedPipeline properly passes adapters to ChangeDetector."""
        from pipeline.enhanced_core import EnhancedPipeline

        # Create mock adapters
        mock_adapters = {
            "registry": MagicMock(),
            "fingerprint_manager": MagicMock(),
            "job_manager": MagicMock(),
            "keyword_index": MagicMock(),
        }

        with patch('pipeline.enhanced_core.DocumentQueue'), \
             patch('pipeline.enhanced_core.IndexManager'), \
             patch('pipeline.enhanced_core.ChangeDetector') as mock_change_detector_class, \
             patch('pipeline.enhanced_core.CacheManager'), \
             patch('pipeline.enhanced_core.ProgressMonitor'):

            # Initialize EnhancedPipeline with adapters
            pipeline = EnhancedPipeline(
                config=config,
                database_adapters=mock_adapters
            )

            # Verify ChangeDetector was initialized with fingerprint_manager
            mock_change_detector_class.assert_called_once()
            call_args = mock_change_detector_class.call_args
            assert call_args[1]['fingerprint_manager'] == mock_adapters['fingerprint_manager']
            assert call_args[1]['registry'] == mock_adapters['registry']

    def test_error_handling_with_adapters(self, config):
        """Test error handling when adapters fail."""
        # Create faulty adapters
        mock_fingerprint_manager = MagicMock()
        mock_fingerprint_manager.compute_fingerprint.side_effect = Exception("Adapter error")

        mock_registry = MagicMock()
        mock_registry.get_document_by_source.side_effect = Exception("Registry error")

        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test that errors are handled gracefully
        with patch('core.change_detector.logger') as mock_logger:
            analysis = detector.analyze_changes("test.pdf", "content")

            # With errors, it might still analyze as COMPLETE_REWRITE
            assert analysis.change_type in [ChangeType.NEW_DOCUMENT, ChangeType.COMPLETE_REWRITE]

            # Verify error was logged
            assert mock_logger.error.called

    def test_change_detector_with_all_operations(self, config, mock_registry, mock_fingerprint_manager):
        """Test all ChangeDetector operations work with adapters."""
        # Initialize detector
        detector = ChangeDetector(
            config=config,
            registry=mock_registry,
            fingerprint_manager=mock_fingerprint_manager
        )

        # Test various operations
        # 1. Single document analysis
        analysis = detector.analyze_changes("test.pdf", "content")
        assert analysis is not None

        # 2. Batch analysis
        batch_results = detector.batch_analyze_changes([{"source": "test.pdf", "content": "content"}])
        assert len(batch_results) == 1

        # 3. Recommendations
        recommendations = detector.get_update_recommendations()
        assert "recommendations" in recommendations

        # 4. Chunk comparison (internal method)
        chunks1 = ["chunk1", "chunk2"]
        chunks2 = ["chunk1", "chunk3"]
        comparison = detector._compare_chunks(chunks1, chunks2)
        assert len(comparison) > 0

        # 5. Close
        detector.close()
        mock_fingerprint_manager.close.assert_called()
        mock_registry.close.assert_called()
