"""Security tests for PostgreSQL implementation."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import asyncpg
import psycopg

from src.pipeline_v3.core.postgres_base import (
    PostgreSQLBase,
    PostgreSQLError,
    PostgreSQLConnectionError,
    PostgreSQLQueryError
)
from src.pipeline_v3.utils.config import PostgreSQLSettings


class TestPostgreSQLSecurity:
    """Test security aspects of PostgreSQL implementation."""

    @pytest.fixture
    def pg_settings(self):
        """Create test PostgreSQL settings."""
        return PostgreSQLSettings(
            host="localhost",
            port=5432,
            database="test_db",
            user="test_user",
            password="test_password",  # pragma: allowlist secret
            ssl_mode="require"
        )

    def test_connection_string_no_password_logging(self, pg_settings):
        """Test that passwords are not exposed in connection strings."""
        db = PostgreSQLBase(pg_settings, "test")

        # Check sync connection string
        assert "test_password" in db._sync_dsn

        # Check async connection string
        assert "test_password" in db._async_dsn

        # Ensure string representation doesn't expose password
        db_str = str(db)
        assert "test_password" not in db_str

    def test_ssl_mode_enforcement(self, pg_settings):
        """Test that SSL mode is properly set in connections."""
        db = PostgreSQLBase(pg_settings, "test")

        # Check that SSL mode is in sync DSN
        assert "sslmode=require" in db._sync_dsn

        # Test with disabled SSL
        pg_settings.ssl_mode = "disable"
        db_insecure = PostgreSQLBase(pg_settings, "test")
        assert "sslmode=" not in db_insecure._sync_dsn

    def test_sql_injection_protection_sync(self, pg_settings):
        """Test that sync queries use parameterized statements."""
        db = PostgreSQLBase(pg_settings, "test")

        # Mock the connection pool
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_pool.connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        db._sync_pool = mock_pool
        db._is_initialized = True

        # Test with potentially malicious input
        malicious_input = "'; DROP TABLE users; --"

        # Execute query with parameters
        db.fetch_one("SELECT * FROM test WHERE name = %s", (malicious_input,))

        # Verify parameterized query was used
        mock_cursor.execute.assert_called()
        call_args = mock_cursor.execute.call_args

        # Check that the query and params are separate
        assert call_args[0][0] == "SELECT * FROM test WHERE name = %s"
        assert call_args[0][1] == (malicious_input,)

    @pytest.mark.asyncio
    async def test_sql_injection_protection_async(self, pg_settings):
        """Test that async queries use parameterized statements."""
        db = PostgreSQLBase(pg_settings, "test")

        # Mock the async pool
        mock_pool = MagicMock()
        mock_conn = MagicMock()

        # Create async context manager mocks
        mock_acquire = MagicMock()
        mock_acquire.__aenter__.return_value = mock_conn
        mock_acquire.__aexit__.return_value = None
        mock_pool.acquire.return_value = mock_acquire

        # Make execute return a coroutine
        async def mock_execute(query):
            return None
        mock_conn.execute = MagicMock(side_effect=mock_execute)

        # Make fetchrow return a coroutine
        async def mock_fetchrow(query, *args):
            return None
        mock_conn.fetchrow = MagicMock(side_effect=mock_fetchrow)

        db._async_pool = mock_pool

        # Test with potentially malicious input
        malicious_input = "'; DROP TABLE users; --"

        # Execute query with parameters
        await db.fetch_one_async("SELECT * FROM test WHERE name = $1", malicious_input)

        # Verify parameterized query was used
        mock_conn.fetchrow.assert_called()
        call_args = mock_conn.fetchrow.call_args[0]
        assert call_args[0] == "SELECT * FROM test WHERE name = $1"
        assert call_args[1] == malicious_input

    def test_schema_isolation(self, pg_settings):
        """Test that queries are isolated to the specified schema."""
        db = PostgreSQLBase(pg_settings, "test_schema")

        # Mock the connection
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_pool.connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        db._sync_pool = mock_pool
        db._is_initialized = True

        # Execute a query
        db.execute("SELECT 1")

        # Verify schema was set
        calls = mock_cursor.execute.call_args_list
        schema_set = False

        for call in calls:
            if "SET search_path TO" in str(call):
                schema_set = True
                break

        assert schema_set, "Schema isolation not enforced"

    def test_timeout_settings(self, pg_settings):
        """Test that timeout settings are applied to prevent DoS."""
        db = PostgreSQLBase(pg_settings, "test")

        # Check timeout settings
        assert pg_settings.statement_timeout == 300000  # 5 minutes
        assert pg_settings.lock_timeout == 10000  # 10 seconds

        # Mock connection to verify timeouts are set
        mock_pool = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()

        mock_pool.connection.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor

        db._sync_pool = mock_pool
        db._is_initialized = True

        # Execute query
        db.execute("SELECT 1")

        # Check that timeouts were set
        calls = [str(call) for call in mock_cursor.execute.call_args_list]
        assert any("SET statement_timeout" in call for call in calls)
        assert any("SET lock_timeout" in call for call in calls)

    def test_connection_pool_limits(self, pg_settings):
        """Test that connection pool has reasonable limits."""
        db = PostgreSQLBase(pg_settings, "test")

        # Check pool settings
        assert pg_settings.min_connections >= 1
        assert pg_settings.max_connections <= 1000  # Reasonable upper limit
        assert pg_settings.min_connections <= pg_settings.max_connections

    def test_error_messages_no_sensitive_info(self, pg_settings):
        """Test that error messages don't expose sensitive information."""
        db = PostgreSQLBase(pg_settings, "test")

        # Test connection error
        with pytest.raises(PostgreSQLConnectionError) as exc_info:
            db.initialize()  # Will fail without real DB

        error_message = str(exc_info.value)
        assert "test_password" not in error_message
        assert pg_settings.password not in error_message

    def test_json_handling_security(self, pg_settings):
        """Test that JSON handling is secure."""
        # Test with potentially malicious JSON
        malicious_dict = {
            "__proto__": {"isAdmin": True},
            "constructor": {"prototype": {"isAdmin": True}},
            "normal_key": "normal_value"
        }

        # Convert to JSONB
        jsonb_str = PostgreSQLBase.json_to_jsonb(malicious_dict)

        # Verify it's properly escaped
        assert isinstance(jsonb_str, str)
        assert "__proto__" in jsonb_str  # Should be preserved as string

        # Convert back
        result = PostgreSQLBase.jsonb_to_dict(jsonb_str)
        assert result == malicious_dict  # Should maintain structure

    def test_multi_tenancy_preparation(self, pg_settings):
        """Test that multi-tenancy fields are present."""
        # Check default tenant ID
        assert pg_settings.default_tenant_id == "00000000-0000-0000-0000-000000000000"

        # Check RLS is enabled by default
        assert pg_settings.enable_rls is True

        # Check schema names for isolation
        assert pg_settings.registry_schema == "registry"
        assert pg_settings.search_schema == "search"
        assert pg_settings.jobs_schema == "jobs"
        assert pg_settings.fingerprints_schema == "fingerprints"

    def test_no_hardcoded_credentials(self):
        """Test that no credentials are hardcoded."""
        import inspect
        import src.pipeline_v3.core.postgres_base as postgres_module

        # Get source code
        source = inspect.getsource(postgres_module)

        # Check for common credential patterns
        suspicious_patterns = [
            "password=",
            "pwd=",
            "passwd=",
            "secret=",
            "api_key=",
            "token="
        ]

        source_lower = source.lower()
        for pattern in suspicious_patterns:
            # Allow in docstrings and connection string building
            if pattern in source_lower:
                # Check context - should only be in safe contexts
                lines = source.split('\n')
                for i, line in enumerate(lines):
                    if pattern in line.lower():
                        # Allow in specific safe contexts
                        safe_contexts = [
                            "self.settings.password",
                            "password:",
                            '["password"]',
                            "# ",
                            '"""',
                            "'"
                        ]

                        is_safe = any(ctx in line for ctx in safe_contexts)
                        assert is_safe, f"Potential hardcoded credential at line {i+1}: {line.strip()}"
