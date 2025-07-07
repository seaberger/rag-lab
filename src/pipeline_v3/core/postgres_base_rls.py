"""
PostgreSQL base class with RLS support and tenant context management.

This enhanced version of PostgreSQLBase automatically manages tenant context
for Row-Level Security (RLS) while maintaining backward compatibility.
"""

import json
import logging
from contextlib import asynccontextmanager, contextmanager
from typing import Any, Dict, List, Tuple, TypeVar

import asyncpg
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ..utils.config import PostgreSQLSettings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PostgreSQLError(Exception):
    """Base exception for PostgreSQL operations."""


class PostgreSQLConnectionError(PostgreSQLError):
    """Raised when connection to PostgreSQL fails."""


class PostgreSQLQueryError(PostgreSQLError):
    """Raised when a query execution fails."""


class PostgreSQLBaseRLS:
    """
    Enhanced PostgreSQL base class with automatic RLS tenant context management.

    This class extends the basic PostgreSQL functionality with:
    - Automatic tenant context setting on each connection
    - Connection pool tenant isolation
    - Admin mode support for maintenance operations
    """

    def __init__(
        self,
        settings: PostgreSQLSettings,
        schema: str,
        tenant_id: str | None = None,
        is_admin: bool = False,
        log_queries: bool = False,
    ):
        """
        Initialize PostgreSQL base with RLS support.

        Args:
            settings: PostgreSQL configuration settings
            schema: Database schema name to use
            tenant_id: Tenant ID for RLS context (None for admin operations)
            is_admin: Whether to run in admin mode (bypasses RLS)
            log_queries: Whether to log SQL queries for debugging
        """
        self.settings = settings
        self.schema = schema
        self.tenant_id = tenant_id
        self.is_admin = is_admin
        self.log_queries = log_queries
        self._sync_pool: ConnectionPool | None = None
        self._async_pool: asyncpg.Pool | None = None
        self._is_initialized = False

        # Build connection strings
        self._build_connection_strings()

    def _build_connection_strings(self):
        """Build connection strings for sync and async connections."""
        # Common parameters
        base_params = {
            "host": self.settings.host,
            "port": self.settings.port,
            "dbname": self.settings.database,
            "user": self.settings.user,
            "password": self.settings.password,
        }

        # Sync connection string (psycopg)
        self._sync_dsn = " ".join(f"{k}={v}" for k, v in base_params.items() if v)

        # Add SSL mode if not disabled
        if self.settings.ssl_mode != "disable":
            self._sync_dsn += f" sslmode={self.settings.ssl_mode}"

        # Async connection string (asyncpg)
        self._async_dsn = (
            f"postgresql://{self.settings.user}:{self.settings.password}"
            f"@{self.settings.host}:{self.settings.port}/{self.settings.database}"
        )

    def _set_session_context(self, cur):
        """Set schema and tenant context for a database session."""
        # Set schema
        cur.execute(sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema)))

        # Set timeouts
        cur.execute(f"SET statement_timeout = {self.settings.statement_timeout}")
        cur.execute(f"SET lock_timeout = {self.settings.lock_timeout}")

        # Set admin mode if requested
        if self.is_admin:
            cur.execute("SET app.is_admin = true")
            if self.log_queries:
                logger.debug("Set admin mode for connection")

        # Set tenant context if provided
        if self.tenant_id and not self.is_admin:
            try:
                cur.execute("SELECT tenants.set_current_tenant(%s)", (self.tenant_id,))
                if self.log_queries:
                    logger.debug(f"Set tenant context to: {self.tenant_id}")
            except Exception as e:
                # Log but don't fail if tenant functions don't exist
                logger.warning(f"Could not set tenant context: {e}")

    async def _set_async_session_context(self, conn):
        """Set schema and tenant context for an async database session."""
        # Set schema
        await conn.execute(f"SET search_path TO {self.schema}, public")

        # Set timeouts
        await conn.execute(f"SET statement_timeout = {self.settings.statement_timeout}")
        await conn.execute(f"SET lock_timeout = {self.settings.lock_timeout}")

        # Set admin mode if requested
        if self.is_admin:
            await conn.execute("SET app.is_admin = true")

        # Set tenant context if provided
        if self.tenant_id and not self.is_admin:
            try:
                await conn.execute("SELECT tenants.set_current_tenant($1)", self.tenant_id)
                if self.log_queries:
                    logger.debug(f"Set async tenant context to: {self.tenant_id}")
            except Exception as e:
                logger.warning(f"Could not set async tenant context: {e}")

    # === Synchronous Interface ===

    def initialize(self):
        """Initialize synchronous connection pool."""
        if self._sync_pool is not None:
            return

        try:
            self._sync_pool = ConnectionPool(
                self._sync_dsn,
                min_size=self.settings.min_connections,
                max_size=self.settings.max_connections,
                timeout=30,
                check=ConnectionPool.check_connection,
            )
            self._is_initialized = True
            logger.info(
                f"Initialized PostgreSQL connection pool for schema: {self.schema}"
                f"{f' (tenant: {self.tenant_id})' if self.tenant_id else ' (admin mode)' if self.is_admin else ''}"
            )
        except Exception as e:
            logger.error(f"Failed to initialize connection pool: {e}")
            raise PostgreSQLConnectionError(f"Connection pool initialization failed: {e}")

    @retry(
        retry=retry_if_exception_type(psycopg.OperationalError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def execute(self, query: str, params: Tuple | None = None) -> int:
        """Execute a query with automatic tenant context."""
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor() as cur:
                # Set session context
                self._set_session_context(cur)

                # Execute query
                if self.log_queries:
                    logger.debug(f"Executing query: {query[:100]}... with params: {params}")

                cur.execute(query, params)
                return cur.rowcount

    def fetch_one(self, query: str, params: Tuple | None = None) -> Dict[str, Any] | None:
        """Fetch a single row with automatic tenant context."""
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Set session context
                self._set_session_context(cur)

                # Execute query
                cur.execute(query, params)
                return cur.fetchone()

    def fetch_all(self, query: str, params: Tuple | None = None) -> List[Dict[str, Any]]:
        """Fetch all rows with automatic tenant context."""
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Set session context
                self._set_session_context(cur)

                # Execute query
                cur.execute(query, params)
                return cur.fetchall()

    @contextmanager
    def transaction(self):
        """Context manager for transactions with tenant context."""
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor() as cur:
                # Set session context
                self._set_session_context(cur)

            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    # === Asynchronous Interface ===

    async def initialize_async(self):
        """Initialize asynchronous connection pool."""
        if self._async_pool is not None:
            return

        try:
            self._async_pool = await asyncpg.create_pool(
                self._async_dsn,
                min_size=self.settings.min_connections,
                max_size=self.settings.max_connections,
                timeout=30,
                command_timeout=self.settings.statement_timeout / 1000,  # Convert to seconds
            )
            logger.info(f"Initialized async PostgreSQL pool for schema: {self.schema}")
        except Exception as e:
            logger.error(f"Failed to initialize async pool: {e}")
            raise PostgreSQLConnectionError(f"Async pool initialization failed: {e}")

    @asynccontextmanager
    async def acquire_async(self):
        """Acquire an async connection with tenant context."""
        if self._async_pool is None:
            await self.initialize_async()

        async with self._async_pool.acquire() as conn:
            # Set session context
            await self._set_async_session_context(conn)
            yield conn

    @retry(
        retry=retry_if_exception_type(asyncpg.PostgresConnectionError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    async def execute_async(self, query: str, *args) -> str:
        """Execute an async query with tenant context."""
        async with self.acquire_async() as conn:
            if self.log_queries:
                logger.debug(f"Executing async query: {query[:100]}...")
            return await conn.execute(query, *args)

    async def fetch_one_async(self, query: str, *args) -> Dict[str, Any] | None:
        """Fetch one row asynchronously with tenant context."""
        async with self.acquire_async() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all_async(self, query: str, *args) -> List[Dict[str, Any]]:
        """Fetch all rows asynchronously with tenant context."""
        async with self.acquire_async() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    # === Utility Methods ===

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the current schema."""
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = %s
                AND table_name = %s
            )
        """
        result = self.fetch_one(query, (self.schema, table_name))
        return result["exists"] if result else False

    def json_to_jsonb(self, data: Any) -> Any:
        """Convert Python object to PostgreSQL JSONB type."""
        if data is None:
            return None
        return psycopg.types.json.Json(data)

    def jsonb_to_dict(self, jsonb_data: Any) -> Dict[str, Any] | None:
        """Convert PostgreSQL JSONB to Python dict."""
        if jsonb_data is None:
            return None
        if isinstance(jsonb_data, dict):
            return jsonb_data
        if isinstance(jsonb_data, str):
            return json.loads(jsonb_data)
        return jsonb_data

    def close(self):
        """Close all connection pools."""
        if self._sync_pool:
            self._sync_pool.close()
            self._sync_pool = None

        if self._async_pool:
            # Async pool closing needs to be done in async context
            import asyncio

            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Schedule closing for later
                    asyncio.create_task(self._close_async_pool())
                else:
                    # Run it now
                    loop.run_until_complete(self._close_async_pool())
            except Exception as e:
                logger.warning(f"Error closing async pool: {e}")

        self._is_initialized = False
        logger.info(f"Closed PostgreSQL connections for schema: {self.schema}")

    async def _close_async_pool(self):
        """Close async pool."""
        if self._async_pool:
            await self._async_pool.close()
            self._async_pool = None

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize_async()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._close_async_pool()
