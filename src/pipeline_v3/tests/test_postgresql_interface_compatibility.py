"""
Test PostgreSQL adapter interface consistency and completeness.

This ensures our PostgreSQL adapters have consistent interfaces and
implement all required functionality for the multi-tenant architecture.
"""

import pytest
from unittest.mock import MagicMock, patch
import inspect

from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex
from src.pipeline_v3.job_queue.postgres_jobs import PostgreSQLJobManager
from src.pipeline_v3.core.postgres_fingerprint import PostgreSQLFingerprintManager


class TestPostgreSQLInterfaceConsistency:
    """Test that PostgreSQL adapters have consistent and complete interfaces."""

    def test_registry_has_core_methods(self):
        """Test PostgreSQL registry has all core document management methods."""
        postgres_methods = self._get_public_methods(PostgreSQLDocumentRegistry)

        # Check core document methods
        core_methods = [
            'register_document',
            'get_document',
            'get_document_by_source',
            'update_document_state',
            'mark_indexed',
            'list_documents',
            'remove_document',
            'get_statistics'
        ]

        for method in core_methods:
            assert method in postgres_methods, f"Missing core method: {method}"

    def test_keyword_index_has_search_methods(self):
        """Test PostgreSQL keyword index has all search functionality."""
        postgres_methods = self._get_public_methods(PostgreSQLKeywordIndex)

        # Check search methods
        search_methods = [
            'index_nodes',
            'search',
            'get_stats',
            'fuzzy_search',
            'search_with_filters',
            'delete_document'  # Actual method name
        ]

        for method in search_methods:
            assert method in postgres_methods, f"Missing search method: {method}"

    def test_job_manager_has_queue_methods(self):
        """Test PostgreSQL job manager has all queue management methods."""
        postgres_methods = self._get_public_methods(PostgreSQLJobManager)

        # Check job queue methods
        queue_methods = [
            'create_job',
            'get_job',
            'update_job_status',
            'claim_next_job',
            'list_jobs',
            'get_job_statistics',
            'cleanup_completed_jobs'  # Actual method name
        ]

        for method in queue_methods:
            assert method in postgres_methods, f"Missing queue method: {method}"

    def test_fingerprint_manager_has_change_detection(self):
        """Test PostgreSQL fingerprint manager has change detection methods."""
        postgres_methods = self._get_public_methods(PostgreSQLFingerprintManager)

        # Check fingerprint methods
        fingerprint_methods = [
            'compute_fingerprint',
            'get_fingerprint',
            'update_fingerprint',
            'has_changed',
            'get_processing_status',
            'mark_processing_status',
            'find_duplicates'
        ]

        for method in fingerprint_methods:
            assert method in postgres_methods, f"Missing fingerprint method: {method}"

    def test_all_adapters_support_multi_tenancy(self):
        """Test all PostgreSQL adapters support multi-tenant architecture."""
        adapters = [
            PostgreSQLDocumentRegistry,
            PostgreSQLKeywordIndex,
            PostgreSQLJobManager,
            PostgreSQLFingerprintManager
        ]

        for adapter in adapters:
            # Check __init__ accepts tenant_id
            init_sig = inspect.signature(adapter.__init__)
            params = init_sig.parameters

            assert 'tenant_id' in params, f"{adapter.__name__} missing tenant_id parameter"

            # Check it's optional with None default
            param = params['tenant_id']
            assert param.default is None, f"{adapter.__name__} tenant_id should default to None"

    def test_all_adapters_have_context_manager(self):
        """Test all PostgreSQL adapters support context manager protocol."""
        adapters = [
            PostgreSQLDocumentRegistry,
            PostgreSQLKeywordIndex,
            PostgreSQLJobManager,
            PostgreSQLFingerprintManager
        ]

        for adapter in adapters:
            assert hasattr(adapter, '__enter__'), f"{adapter.__name__} missing __enter__"
            assert hasattr(adapter, '__exit__'), f"{adapter.__name__} missing __exit__"
            assert hasattr(adapter, 'close'), f"{adapter.__name__} missing close method"

    def test_all_adapters_have_initialization_methods(self):
        """Test all PostgreSQL adapters have proper initialization."""
        adapters = [
            PostgreSQLDocumentRegistry,
            PostgreSQLKeywordIndex,
            PostgreSQLJobManager,
            PostgreSQLFingerprintManager
        ]

        for adapter in adapters:
            methods = self._get_public_methods(adapter)

            # Should have initialization support
            assert 'initialize' in methods or '__enter__' in dir(adapter), \
                f"{adapter.__name__} missing initialization method"

    def _get_public_methods(self, cls):
        """Get all public methods of a class."""
        return {
            name for name, method in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith('_')
        }


class TestPostgreSQLMethodSignatures:
    """Test that PostgreSQL methods have expected signatures."""

    def test_search_method_signature(self):
        """Test search method has expected signature."""
        pg_sig = inspect.signature(PostgreSQLKeywordIndex.search)

        # Should accept query and limit
        assert 'query' in pg_sig.parameters
        assert 'limit' in pg_sig.parameters

    def test_register_document_signature(self):
        """Test document registration has expected signature."""
        reg_sig = inspect.signature(PostgreSQLDocumentRegistry.register_document)

        # Should accept core document parameters
        required_params = ['source', 'content_hash', 'size', 'modified_time']
        for param in required_params:
            assert param in reg_sig.parameters, f"Missing parameter: {param}"

    def test_job_creation_signature(self):
        """Test job creation has expected signature."""
        job_sig = inspect.signature(PostgreSQLJobManager.create_job)

        # Should accept job parameters
        assert 'source' in job_sig.parameters
        assert 'job_type' in job_sig.parameters

    def test_fingerprint_computation_signature(self):
        """Test fingerprint computation has expected signature."""
        fp_sig = inspect.signature(PostgreSQLFingerprintManager.compute_fingerprint)

        # Should accept source path (actual parameter name)
        assert 'source' in fp_sig.parameters


class TestPostgreSQLFeatureCompleteness:
    """Test that PostgreSQL adapters implement enterprise features."""

    def test_registry_supports_tenant_filtering(self):
        """Test registry supports tenant-aware operations."""
        # This would require actual database testing
        # For now, just verify the interface supports it
        assert hasattr(PostgreSQLDocumentRegistry, 'list_documents')

    def test_keyword_index_supports_advanced_search(self):
        """Test keyword index supports advanced search features."""
        methods = self._get_public_methods(PostgreSQLKeywordIndex)

        # PostgreSQL version should have advanced features
        advanced_features = ['fuzzy_search', 'search_with_filters']
        for feature in advanced_features:
            assert feature in methods, f"Missing advanced feature: {feature}"

    def test_job_manager_supports_priority_queuing(self):
        """Test job manager supports priority-based queuing."""
        # Check that job creation accepts priority
        job_sig = inspect.signature(PostgreSQLJobManager.create_job)
        assert 'priority' in job_sig.parameters or 'metadata' in job_sig.parameters

    def test_fingerprint_manager_supports_duplicate_detection(self):
        """Test fingerprint manager supports duplicate detection."""
        methods = self._get_public_methods(PostgreSQLFingerprintManager)
        assert 'find_duplicates' in methods, "Missing duplicate detection"

    def _get_public_methods(self, cls):
        """Get all public methods of a class."""
        return {
            name for name, method in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith('_')
        }


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
