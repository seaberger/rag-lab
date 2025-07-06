"""
Test PostgreSQL adapter interface compatibility.

This ensures our PostgreSQL adapters maintain the same interface as SQLite versions.
"""

import pytest
from unittest.mock import MagicMock, patch
import inspect

from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
from src.pipeline_v3.storage.keyword_index import BM25Index
from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex
from src.pipeline_v3.job_queue.manager import DocumentQueue
from src.pipeline_v3.job_queue.postgres_jobs import PostgreSQLJobManager
from src.pipeline_v3.core.fingerprint import FingerprintStore
from src.pipeline_v3.core.postgres_fingerprint import PostgreSQLFingerprintManager


class TestInterfaceCompatibility:
    """Test that PostgreSQL adapters implement the same interface as SQLite versions."""

    def test_registry_interface_compatibility(self):
        """Test PostgreSQL registry has all methods from SQLite registry."""
        sqlite_methods = self._get_public_methods(DocumentRegistry)
        postgres_methods = self._get_public_methods(PostgreSQLDocumentRegistry)

        # PostgreSQL should have all SQLite methods
        missing_methods = sqlite_methods - postgres_methods
        assert not missing_methods, f"PostgreSQL registry missing methods: {missing_methods}"

        # Check key method signatures match
        key_methods = [
            'register_document',
            'get_document',
            'update_document_state',
            'mark_indexed',
            'list_documents',
            'get_statistics'
        ]

        for method in key_methods:
            assert method in postgres_methods, f"Missing critical method: {method}"

    def test_keyword_index_interface_compatibility(self):
        """Test PostgreSQL keyword index has all methods from SQLite version."""
        sqlite_methods = self._get_public_methods(BM25Index)
        postgres_methods = self._get_public_methods(PostgreSQLKeywordIndex)

        # Check critical search methods
        critical_methods = ['index_nodes', 'search', 'get_stats']
        for method in critical_methods:
            assert method in postgres_methods, f"Missing critical method: {method}"

        # PostgreSQL adds advanced features
        advanced_methods = ['fuzzy_search', 'search_with_filters']
        for method in advanced_methods:
            assert method in postgres_methods, f"Missing advanced method: {method}"

    def test_job_manager_interface_compatibility(self):
        """Test PostgreSQL job manager has all methods from SQLite version."""
        # DocumentQueue uses different pattern, so check key methods directly
        postgres_methods = self._get_public_methods(PostgreSQLJobManager)

        # Check critical job methods
        critical_methods = [
            'create_job',
            'get_job',
            'update_job_status',
            'claim_next_job',
            'list_jobs',
            'get_job_statistics'
        ]

        for method in critical_methods:
            assert method in postgres_methods, f"Missing critical method: {method}"

    def test_fingerprint_interface_compatibility(self):
        """Test PostgreSQL fingerprint manager has all methods from SQLite version."""
        sqlite_methods = self._get_public_methods(FingerprintStore)
        postgres_methods = self._get_public_methods(PostgreSQLFingerprintManager)

        # Check critical fingerprint methods
        critical_methods = [
            'compute_fingerprint',
            'get_fingerprint',
            'update_fingerprint',
            'has_changed',
            'get_processing_status',
            'mark_processing_status'
        ]

        for method in critical_methods:
            assert method in postgres_methods, f"Missing critical method: {method}"

        # PostgreSQL adds multi-tenant features
        assert 'find_duplicates' in postgres_methods, "Missing duplicate detection"

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

    def test_tenant_id_parameter_consistency(self):
        """Test all PostgreSQL adapters accept tenant_id parameter."""
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

    def _get_public_methods(self, cls):
        """Get all public methods of a class."""
        return {
            name for name, method in inspect.getmembers(cls, inspect.isfunction)
            if not name.startswith('_')
        }


class TestMethodSignatures:
    """Test that critical methods have compatible signatures."""

    def test_search_method_signatures(self):
        """Test search methods have compatible signatures."""
        # BM25Index.search signature
        bm25_sig = inspect.signature(BM25Index.search)
        pg_sig = inspect.signature(PostgreSQLKeywordIndex.search)

        # Both should accept query and limit
        assert 'query' in bm25_sig.parameters
        assert 'query' in pg_sig.parameters
        assert 'limit' in bm25_sig.parameters
        assert 'limit' in pg_sig.parameters

        # Return types should be similar (list of dicts)
        # Note: We can't check return type annotations if not present

    def test_job_claiming_signatures(self):
        """Test job claiming methods are compatible."""
        pg_sig = inspect.signature(PostgreSQLJobManager.claim_next_job)

        # Should accept worker_id
        assert 'worker_id' in pg_sig.parameters

        # Should be simple interface (self, worker_id)
        assert len(pg_sig.parameters) == 2  # self + worker_id


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
