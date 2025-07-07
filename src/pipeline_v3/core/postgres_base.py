"""
PostgreSQL base class with connection pooling and retry logic.

This module provides the foundation for all PostgreSQL database operations
with built-in connection pooling, automatic retry, and error handling.
"""

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Tuple, TypeVar, Union

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

from src.pipeline_v3.utils.config import PostgreSQLSettings

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PostgreSQLError(Exception):
    """Base exception for PostgreSQL operations."""


class PostgreSQLConnectionError(PostgreSQLError):
    """Raised when connection to PostgreSQL fails."""


class PostgreSQLQueryError(PostgreSQLError):
    """Raised when a query execution fails."""


class PostgreSQLBase:
    """
    Base class for PostgreSQL database operations with connection pooling.

    Provides both sync and async interfaces with automatic retry logic,
    connection pooling, and comprehensive error handling.
    """

    def __init__(self, settings: PostgreSQLSettings, schema: str, log_queries: bool = False):
        """
        Initialize PostgreSQL base with settings and schema.

        Args:
            settings: PostgreSQL configuration settings
            schema: Database schema name to use
            log_queries: Whether to log SQL queries for debugging
        """
        self.settings = settings
        self.schema = schema
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
            "dbname": self.settings.database,  # psycopg uses 'dbname' not 'database'
            "user": self.settings.user,
            "password": self.settings.password,
        }

        # Sync connection string (psycopg)
        self._sync_dsn = " ".join(f"{k}={v}" for k, v in base_params.items() if v)

        # Add SSL mode if not disabled
        if self.settings.ssl_mode != "disable":
            self._sync_dsn += f" sslmode={self.settings.ssl_mode}"

        # Async connection string (asyncpg)
        self._async_dsn = f"postgresql://{self.settings.user}:{self.settings.password}@{self.settings.host}:{self.settings.port}/{self.settings.database}"

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
                timeout=self.settings.connection_timeout,
                max_idle=self.settings.idle_timeout,
                check=ConnectionPool.check_connection,
            )

            # Test connection
            with self._sync_pool.connection() as conn:
                conn.execute("SELECT 1")

            self._is_initialized = True
            logger.info(f"PostgreSQL sync pool initialized for schema: {self.schema}")

        except Exception as e:
            logger.exception(f"Failed to initialize PostgreSQL sync pool: {e}")
            raise PostgreSQLConnectionError(f"Connection pool initialization failed: {e}")

    def close(self):
        """Close synchronous connection pool."""
        if self._sync_pool:
            self._sync_pool.close()
            self._sync_pool = None
            self._is_initialized = False

    @retry(
        retry=retry_if_exception_type(psycopg.OperationalError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    def execute(self, query: str, params: Tuple | None = None) -> int:
        """
        Execute a query that doesn't return results.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Number of affected rows
        """
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor() as cur:
                # Set schema
                cur.execute(
                    sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema))
                )

                # Set timeouts
                cur.execute(f"SET statement_timeout = {self.settings.statement_timeout}")
                cur.execute(f"SET lock_timeout = {self.settings.lock_timeout}")

                # Execute query
                if self.log_queries:
                    logger.debug(f"Executing query: {query[:100]}... with params: {params}")

                cur.execute(query, params)
                return cur.rowcount

    def fetch_one(self, query: str, params: Tuple | None = None) -> Dict[str, Any] | None:
        """
        Fetch a single row.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            Dictionary representing the row or None
        """
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Set schema
                cur.execute(
                    sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema))
                )

                # Execute query
                cur.execute(query, params)
                return cur.fetchone()

    def fetch_all(self, query: str, params: Tuple | None = None) -> List[Dict[str, Any]]:
        """
        Fetch all rows.

        Args:
            query: SQL query to execute
            params: Query parameters

        Returns:
            List of dictionaries representing rows
        """
        if not self._is_initialized:
            self.initialize()

        with self._sync_pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                # Set schema
                cur.execute(
                    sql.SQL("SET search_path TO {}, public").format(sql.Identifier(self.schema))
                )

                # Execute query
                cur.execute(query, params)
                return cur.fetchall()

    def transaction(self):
        """
        Context manager for transactions.

        Usage:
            with db.transaction() as conn:
                conn.execute(query1)
                conn.execute(query2)
        """
        if not self._is_initialized:
            self.initialize()

        return self._sync_pool.connection()

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
                timeout=self.settings.connection_timeout,
                command_timeout=self.settings.statement_timeout / 1000,  # Convert to seconds
            )

            # Test connection
            async with self._async_pool.acquire() as conn:
                await conn.fetchval("SELECT 1")

            logger.info(f"PostgreSQL async pool initialized for schema: {self.schema}")

        except Exception as e:
            logger.exception(f"Failed to initialize PostgreSQL async pool: {e}")
            raise PostgreSQLConnectionError(f"Async pool initialization failed: {e}")

    async def close_async(self):
        """Close asynchronous connection pool."""
        if self._async_pool:
            await self._async_pool.close()
            self._async_pool = None

    @asynccontextmanager
    async def acquire(self):
        """
        Acquire a connection from the async pool.

        Usage:
            async with db.acquire() as conn:
                await conn.fetch(query)
        """
        if self._async_pool is None:
            await self.initialize_async()

        async with self._async_pool.acquire() as conn:
            # Set schema
            await conn.execute(f"SET search_path TO {self.schema}, public")

            # Set timeouts
            await conn.execute(f"SET statement_timeout = {self.settings.statement_timeout}")
            await conn.execute(f"SET lock_timeout = {self.settings.lock_timeout}")

            yield conn

    @retry(
        retry=retry_if_exception_type(asyncpg.PostgresConnectionError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def execute_async(self, query: str, *args) -> str:
        """
        Execute a query asynchronously that doesn't return results.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            Status string from PostgreSQL
        """
        async with self.acquire() as conn:
            if self.log_queries:
                logger.debug(f"Executing async query: {query[:100]}... with params: {args}")

            return await conn.execute(query, *args)

    async def fetch_one_async(self, query: str, *args) -> Dict[str, Any] | None:
        """
        Fetch a single row asynchronously.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            Dictionary representing the row or None
        """
        async with self.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all_async(self, query: str, *args) -> List[Dict[str, Any]]:
        """
        Fetch all rows asynchronously.

        Args:
            query: SQL query to execute
            *args: Query parameters

        Returns:
            List of dictionaries representing rows
        """
        async with self.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    @asynccontextmanager
    async def transaction_async(self):
        """
        Async context manager for transactions.

        Usage:
            async with db.transaction_async() as conn:
                await conn.execute(query1)
                await conn.execute(query2)
        """
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn

    # === Helper Methods ===

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists in the schema."""
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

    async def table_exists_async(self, table_name: str) -> bool:
        """Check if a table exists in the schema (async)."""
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.tables
                WHERE table_schema = $1
                AND table_name = $2
            )
        """
        result = await self.fetch_one_async(query, self.schema, table_name)
        return result["exists"] if result else False

    def create_schema_if_not_exists(self):
        """Create the schema if it doesn't exist."""
        with self.transaction() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(self.schema))
                )

    async def create_schema_if_not_exists_async(self):
        """Create the schema if it doesn't exist (async)."""
        async with self.transaction_async() as conn:
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")

    # === JSON Handling ===

    @staticmethod
    def json_to_jsonb(data: Union[dict, list, None]) -> str | None:
        """Convert Python dict/list to JSONB string."""
        return json.dumps(data) if data is not None else None

    @staticmethod
    def jsonb_to_dict(jsonb_data: Any) -> Union[dict, list] | None:
        """Convert JSONB data to Python dict/list."""
        if jsonb_data is None:
            return None
        if isinstance(jsonb_data, dict | list):
            return jsonb_data
        if isinstance(jsonb_data, str):
            return json.loads(jsonb_data)
        return jsonb_data

    # === Performance Monitoring ===

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get connection pool statistics."""
        stats = {}

        if self._sync_pool:
            pool_info = self._sync_pool.get_stats()
            stats["sync_pool"] = {
                "size": pool_info["pool_size"],
                "available": pool_info["pool_available"],
                "in_use": pool_info["requests_num"],
            }

        if self._async_pool:
            stats["async_pool"] = {
                "size": self._async_pool.get_size(),
                "free_connections": self._async_pool.get_idle_size(),
                "min_size": self._async_pool.get_min_size(),
                "max_size": self._async_pool.get_max_size(),
            }

        return stats
