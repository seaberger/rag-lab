#!/usr/bin/env python3
"""
PostgreSQL connection helper with multiple authentication methods.

This helper tries multiple approaches to connect to PostgreSQL:
1. Environment variables
2. .pgpass file
3. Connection URI with explicit credentials
4. Trust authentication (if configured)
"""

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

import psycopg

# Add pipeline_v3 to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class PostgreSQLConnector:
    """Handles PostgreSQL connections with multiple fallback methods."""

    def __init__(self):
        """Initialize with configuration."""
        self.config = PipelineConfig()
        self.pg_settings = self.config.database.postgresql
        self.connection_methods = []

    def _try_environment_connection(self):
        """Try connection using environment variables."""
        # Check multiple possible environment variable names
        password_vars = ["POSTGRES_PASSWORD", "PGPASSWORD", "POSTGRESQL_PASSWORD"]
        password = None

        for var in password_vars:
            if var in os.environ:
                password = os.environ[var]
                logger.info(f"Found password in {var}")
                break

        if not password:
            logger.warning("No password found in environment variables")
            return None

        # Build connection string with URL-encoded password
        conn_str = (
            f"postgresql://{self.pg_settings.user}:{quote_plus(password)}"
            f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
        )

        try:
            conn = psycopg.connect(conn_str)
            logger.info("Connected using environment variables")
            return conn
        except Exception as e:
            logger.warning(f"Environment connection failed: {e}")
            return None

    def _try_pgpass_connection(self):
        """Try connection using .pgpass file."""
        # .pgpass should handle authentication automatically
        conn_str = (
            f"postgresql://{self.pg_settings.user}"
            f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
        )

        try:
            conn = psycopg.connect(conn_str)
            logger.info("Connected using .pgpass file")
            return conn
        except Exception as e:
            logger.warning(f".pgpass connection failed: {e}")
            return None

    def _try_config_connection(self):
        """Try connection using config file password."""
        if not self.pg_settings.password:
            logger.warning("No password in config")
            return None

        conn_str = (
            f"postgresql://{self.pg_settings.user}:{quote_plus(self.pg_settings.password)}"
            f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
        )

        try:
            conn = psycopg.connect(conn_str)
            logger.info("Connected using config password")
            return conn
        except Exception as e:
            logger.warning(f"Config connection failed: {e}")
            return None

    def _try_trust_connection(self):
        """Try connection without password (trust authentication)."""
        conn_str = (
            f"postgresql://{self.pg_settings.user}"
            f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
        )

        try:
            conn = psycopg.connect(conn_str, password=None)
            logger.info("Connected using trust authentication")
            return conn
        except Exception as e:
            logger.warning(f"Trust connection failed: {e}")
            return None

    def connect(self):
        """Try all connection methods and return the first successful one."""
        methods = [
            ("Environment variables", self._try_environment_connection),
            (".pgpass file", self._try_pgpass_connection),
            ("Config file", self._try_config_connection),
            ("Trust authentication", self._try_trust_connection),
        ]

        for name, method in methods:
            logger.info(f"Trying connection method: {name}")
            conn = method()
            if conn:
                return conn

        # If all methods fail, provide helpful debugging info
        logger.error("All connection methods failed!")
        logger.error("Debug information:")
        logger.error(f"  Host: {self.pg_settings.host}")
        logger.error(f"  Port: {self.pg_settings.port}")
        logger.error(f"  Database: {self.pg_settings.database}")
        logger.error(f"  User: {self.pg_settings.user}")
        logger.error(f"  Password in config: {bool(self.pg_settings.password)}")
        logger.error(f"  POSTGRES_PASSWORD set: {bool(os.environ.get('POSTGRES_PASSWORD'))}")
        logger.error(f"  PGPASSWORD set: {bool(os.environ.get('PGPASSWORD'))}")
        logger.error(
            f"  .pgpass exists: {Path.home().joinpath('.pgpass').exists() or Path('.pgpass').exists()}"
        )

        raise ConnectionError("Could not connect to PostgreSQL with any method")

    def get_connection_string(self):
        """Get a working connection string."""
        # Try to get password from various sources
        password = (
            self.pg_settings.password
            or os.environ.get("POSTGRES_PASSWORD")
            or os.environ.get("PGPASSWORD")
            or ""
        )

        if password:
            return (
                f"postgresql://{self.pg_settings.user}:{quote_plus(password)}"
                f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
            )
        else:
            # Try without password (might work with .pgpass or trust)
            return (
                f"postgresql://{self.pg_settings.user}"
                f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
            )


def test_connection():
    """Test PostgreSQL connection with detailed output."""
    connector = PostgreSQLConnector()

    print("\n" + "=" * 60)
    print("PostgreSQL Connection Test")
    print("=" * 60)

    try:
        with connector.connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT version()")
                version = cur.fetchone()[0]
                print("\n✓ Successfully connected to PostgreSQL!")
                print(f"  Version: {version}")

                # Check if database exists
                cur.execute("SELECT current_database()")
                db_name = cur.fetchone()[0]
                print(f"  Database: {db_name}")

                # Check current user
                cur.execute("SELECT current_user")
                user = cur.fetchone()[0]
                print(f"  User: {user}")

                # Check RLS status
                cur.execute("""
                    SELECT COUNT(*) FROM pg_tables
                    WHERE schemaname = 'tenants' AND tablename = 'tenants'
                """)
                has_tenant_table = cur.fetchone()[0] > 0

                if has_tenant_table:
                    print("  RLS Tables: ✓ Tenant tables exist")
                else:
                    print("  RLS Tables: ✗ Tenant tables not found")

                print("\nConnection successful! You can now run RLS setup.")
                return True

    except Exception as e:
        print(f"\n✗ Connection failed: {e}")
        print("\nTroubleshooting steps:")
        print("1. Ensure PostgreSQL is running:")
        print("   ./scripts/postgres_server.sh status")
        print("2. Source the environment file:")
        print("   source .env.postgres.fixed")
        print("3. Check PostgreSQL logs:")
        print("   ./scripts/postgres_server.sh logs")
        print("4. Verify credentials match your PostgreSQL setup")
        return False


if __name__ == "__main__":
    test_connection()
