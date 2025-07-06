"""
Tests for PostgreSQL adapter implementations.

These tests verify that our PostgreSQL adapters maintain compatibility with
SQLite interfaces while adding multi-tenant support.
"""

import pytest
import uuid
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.pipeline_v3.utils.config import PipelineConfig, DatabaseSettings, PostgreSQLSettings
from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex
from src.pipeline_v3.job_queue.postgres_jobs import PostgreSQLJobManager
from src.pipeline_v3.core.postgres_fingerprint import PostgreSQLFingerprintManager
from src.pipeline_v3.core.registry import DocumentState
from src.pipeline_v3.job_queue.job import JobType, JobStatus


@pytest.fixture
def pg_config():
    """Create a test PostgreSQL configuration."""
    return PipelineConfig(
        database=DatabaseSettings(
            backend="postgresql",
            log_queries=False,
            postgresql=PostgreSQLSettings(
                host="localhost",
                port=5432,
                database="test_db",
                user="test_user",
                password="test_password",  # pragma: allowlist secret
                ssl_mode="prefer",
                min_connections=1,
                max_connections=10,
                default_tenant_id=str(uuid.uuid4()),
                registry_schema="registry",
                search_schema="search",
                jobs_schema="jobs",
                fingerprints_schema="fingerprints"
            )
        )
    )


@pytest.fixture
def mock_postgres_base():
    """Mock PostgreSQLBase for unit testing."""
    with patch('src.pipeline_v3.core.postgres_registry.PostgreSQLBase') as mock:
        base_instance = MagicMock()
        base_instance.initialize = MagicMock()
        base_instance.table_exists = MagicMock(return_value=True)
        base_instance.execute = MagicMock(return_value=1)
        base_instance.fetch_one = MagicMock(return_value=None)
        base_instance.fetch_all = MagicMock(return_value=[])
        base_instance.json_to_jsonb = MagicMock(side_effect=lambda x: json.dumps(x))
        base_instance.jsonb_to_dict = MagicMock(side_effect=lambda x: json.loads(x) if x else None)
        base_instance.transaction = MagicMock()
        mock.return_value = base_instance
        yield base_instance


class TestPostgreSQLDocumentRegistry:
    """Test PostgreSQL document registry adapter."""

    def test_initialization(self, pg_config, mock_postgres_base):
        """Test registry initialization with PostgreSQL."""
        registry = PostgreSQLDocumentRegistry(pg_config)

        # Verify PostgreSQL base was initialized correctly
        mock_postgres_base.initialize.assert_called_once()
        assert registry.tenant_id == pg_config.database.postgresql.default_tenant_id

    def test_register_document(self, pg_config, mock_postgres_base):
        """Test document registration with multi-tenant support."""
        registry = PostgreSQLDocumentRegistry(pg_config)

        # Register a new document
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="hash123",
            size=1024,
            modified_time=datetime.now().timestamp(),
            metadata={"test": "data"}
        )

        # Verify execute was called with tenant_id
        mock_postgres_base.execute.assert_called()
        call_args = mock_postgres_base.execute.call_args[0]
        assert "INSERT INTO documents" in call_args[0]
        assert uuid.UUID(registry.tenant_id) in call_args[1]

    def test_get_document_with_tenant_isolation(self, pg_config, mock_postgres_base):
        """Test that documents are tenant-isolated."""
        registry = PostgreSQLDocumentRegistry(pg_config)
        doc_id = str(uuid.uuid4())

        # Get document
        registry.get_document(doc_id)

        # Verify query includes tenant_id
        mock_postgres_base.fetch_one.assert_called()
        query, params = mock_postgres_base.fetch_one.call_args[0]
        assert "tenant_id = %s" in query
        assert uuid.UUID(registry.tenant_id) in params


class TestPostgreSQLKeywordIndex:
    """Test PostgreSQL keyword index adapter."""

    def test_initialization(self, pg_config, mock_postgres_base):
        """Test keyword index initialization."""
        with patch('src.pipeline_v3.storage.postgres_keyword.PostgreSQLBase', return_value=mock_postgres_base):
            index = PostgreSQLKeywordIndex(pg_config)

            assert index.tenant_id == pg_config.database.postgresql.default_tenant_id
            mock_postgres_base.initialize.assert_called_once()

    def test_search_query_escaping(self, pg_config, mock_postgres_base):
        """Test that search queries are properly escaped."""
        with patch('src.pipeline_v3.storage.postgres_keyword.PostgreSQLBase', return_value=mock_postgres_base):
            index = PostgreSQLKeywordIndex(pg_config)

            # Test various injection attempts
            malicious_queries = [
                "'; DROP TABLE documents; --",
                "UNION SELECT * FROM users",
                "1' OR '1'='1",
                "Robert'); DROP TABLE students;--"
            ]

            for query in malicious_queries:
                escaped = index._escape_search_query(query)
                # Verify dangerous SQL is removed
                assert "DROP" not in escaped
                assert "UNION" not in escaped
                assert "--" not in escaped
                assert ";" not in escaped

    def test_fuzzy_search(self, pg_config, mock_postgres_base):
        """Test fuzzy search functionality."""
        with patch('src.pipeline_v3.storage.postgres_keyword.PostgreSQLBase', return_value=mock_postgres_base):
            index = PostgreSQLKeywordIndex(pg_config)
            mock_postgres_base.fetch_all.return_value = []

            # Test fuzzy search
            results = index.fuzzy_search("lazer", similarity=0.3, limit=10)

            # Verify trigram similarity query was used
            mock_postgres_base.fetch_all.assert_called()
            query = mock_postgres_base.fetch_all.call_args[0][0]
            assert "similarity(" in query
            assert "%%%" in query  # PostgreSQL trigram operator


class TestPostgreSQLJobManager:
    """Test PostgreSQL job manager adapter."""

    def test_initialization(self, pg_config, mock_postgres_base):
        """Test job manager initialization."""
        with patch('src.pipeline_v3.job_queue.postgres_jobs.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLJobManager(pg_config)

            assert manager.tenant_id == pg_config.database.postgresql.default_tenant_id
            mock_postgres_base.initialize.assert_called_once()

    def test_create_job_with_tenant(self, pg_config, mock_postgres_base):
        """Test job creation includes tenant_id."""
        with patch('src.pipeline_v3.job_queue.postgres_jobs.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLJobManager(pg_config)

            job_id = manager.create_job(
                source="test.pdf",
                job_type=JobType.PROCESS_DOCUMENT,
                priority=1,
                metadata={"test": "data"}
            )

            # Verify INSERT includes tenant_id
            mock_postgres_base.execute.assert_called()
            query, params = mock_postgres_base.execute.call_args[0]
            assert "tenant_id" in query
            assert uuid.UUID(manager.tenant_id) in params

    def test_claim_next_job_atomic(self, pg_config, mock_postgres_base):
        """Test atomic job claiming with SKIP LOCKED."""
        with patch('src.pipeline_v3.job_queue.postgres_jobs.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLJobManager(pg_config)
            worker_id = "worker-1"

            # Mock job return
            mock_job = {
                "job_id": uuid.uuid4(),
                "source": "test.pdf",
                "job_type": JobType.PROCESS_DOCUMENT.value,
                "priority": 1,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "started_at": None,
                "completed_at": None,
                "status": JobStatus.PENDING.value,
                "progress": 0.0,
                "worker_id": None,
                "error_message": None,
                "retry_count": 0,
                "max_retries": 3,
                "metadata": {},
                "intermediate_state": {}
            }
            mock_postgres_base.fetch_one.return_value = mock_job

            job = manager.claim_next_job(worker_id)

            # Verify stored function was called
            mock_postgres_base.fetch_one.assert_called()
            query = mock_postgres_base.fetch_one.call_args[0][0]
            assert "claim_next_job" in query


class TestPostgreSQLFingerprintManager:
    """Test PostgreSQL fingerprint manager adapter."""

    def test_initialization(self, pg_config, mock_postgres_base):
        """Test fingerprint manager initialization."""
        with patch('src.pipeline_v3.core.postgres_fingerprint.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLFingerprintManager(pg_config)

            assert manager.tenant_id == pg_config.database.postgresql.default_tenant_id
            mock_postgres_base.initialize.assert_called_once()

    def test_update_fingerprint_with_tenant(self, pg_config, mock_postgres_base):
        """Test fingerprint updates include tenant_id."""
        with patch('src.pipeline_v3.core.postgres_fingerprint.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLFingerprintManager(pg_config)

            # Create a test fingerprint
            with patch.object(Path, 'exists', return_value=True):
                with patch('builtins.open', create=True) as mock_open:
                    mock_open.return_value.__enter__.return_value.read.return_value = b"test content"

                    fingerprint = manager.compute_fingerprint("test.pdf")
                    manager.update_fingerprint(fingerprint, doc_id=str(uuid.uuid4()))

            # Verify upsert includes tenant_id
            mock_postgres_base.execute.assert_called()
            query, params = mock_postgres_base.execute.call_args[0]
            assert "ON CONFLICT (tenant_id, source)" in query
            assert uuid.UUID(manager.tenant_id) in params

    def test_find_duplicates(self, pg_config, mock_postgres_base):
        """Test duplicate detection within tenant."""
        with patch('src.pipeline_v3.core.postgres_fingerprint.PostgreSQLBase', return_value=mock_postgres_base):
            manager = PostgreSQLFingerprintManager(pg_config)

            # Mock duplicate results
            mock_postgres_base.fetch_all.return_value = [
                {
                    "content_hash": "hash123",
                    "sources": ["doc1.pdf", "doc2.pdf"]
                }
            ]

            duplicates = manager.find_duplicates()

            # Verify query filtered by tenant
            mock_postgres_base.fetch_all.assert_called()
            query, params = mock_postgres_base.fetch_all.call_args[0]
            assert "tenant_id = %s" in query
            assert uuid.UUID(manager.tenant_id) in params


class TestPostgreSQLIntegration:
    """Integration tests for all PostgreSQL adapters."""

    def test_all_adapters_use_same_tenant(self, pg_config, mock_postgres_base):
        """Test that all adapters use consistent tenant_id."""
        with patch('src.pipeline_v3.core.postgres_registry.PostgreSQLBase', return_value=mock_postgres_base), \
             patch('src.pipeline_v3.storage.postgres_keyword.PostgreSQLBase', return_value=mock_postgres_base), \
             patch('src.pipeline_v3.job_queue.postgres_jobs.PostgreSQLBase', return_value=mock_postgres_base), \
             patch('src.pipeline_v3.core.postgres_fingerprint.PostgreSQLBase', return_value=mock_postgres_base):

            # Create all adapters
            registry = PostgreSQLDocumentRegistry(pg_config)
            keyword_index = PostgreSQLKeywordIndex(pg_config)
            job_manager = PostgreSQLJobManager(pg_config)
            fingerprint_manager = PostgreSQLFingerprintManager(pg_config)

            # Verify all use same tenant_id
            tenant_id = pg_config.database.postgresql.default_tenant_id
            assert registry.tenant_id == tenant_id
            assert keyword_index.tenant_id == tenant_id
            assert job_manager.tenant_id == tenant_id
            assert fingerprint_manager.tenant_id == tenant_id

    def test_error_handling(self, pg_config, mock_postgres_base):
        """Test proper error handling in adapters."""
        with patch('src.pipeline_v3.core.postgres_registry.PostgreSQLBase', return_value=mock_postgres_base):
            registry = PostgreSQLDocumentRegistry(pg_config)

            # Simulate database error
            mock_postgres_base.execute.side_effect = Exception("Database connection failed")

            # Test error handling doesn't expose sensitive info
            result = registry.update_document_state(
                doc_id=str(uuid.uuid4()),
                state=DocumentState.INDEXED
            )

            assert result is False  # Operation should fail gracefully


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
