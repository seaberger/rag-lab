"""
Database credential management for tests.

Handles different authentication methods based on environment:
- Local development: Uses .env file or passwordless auth
- GitHub Actions: Uses secrets passed as environment variables
- Docker: Uses container-specific settings
"""

import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv

from src.pipeline_v3.utils.common_utils import logger


class TestDatabaseCredentials:
    """Manages database credentials for different test environments."""

    @staticmethod
    def get_postgres_credentials() -> Dict[str, str]:
        """
        Get PostgreSQL credentials based on the environment.

        Priority order:
        1. Environment variables (for CI/CD)
        2. .env file (for local development)
        3. Default test values (for local Docker)
        """
        # Check if we're in CI
        is_ci = os.environ.get("CI", "false").lower() == "true"
        is_github_actions = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"

        # Start with defaults
        credentials = {
            "host": os.environ.get("POSTGRES_HOST", "localhost"),
            "port": os.environ.get("POSTGRES_PORT", "5432"),
            "database": os.environ.get("POSTGRES_DATABASE", "rag_lab"),
            "user": os.environ.get("POSTGRES_USER", "postgres"),
            "password": None,
        }

        # Try to get password from environment first (CI/CD)
        if os.environ.get("POSTGRES_PASSWORD"):
            credentials["password"] = os.environ.get("POSTGRES_PASSWORD")
            logger.info("Using PostgreSQL password from environment variable")
            return credentials

        # For local development, try .env files
        if not is_ci:
            project_root = Path(__file__).parent.parent.parent.parent

            # Try .env.postgres first (specific PostgreSQL config)
            postgres_env_file = project_root / ".env.postgres"
            if postgres_env_file.exists():
                # Load with export=True to handle "export VAR=value" format
                load_dotenv(postgres_env_file, override=True)

                # Check for password
                if os.environ.get("POSTGRES_PASSWORD"):
                    credentials["password"] = os.environ.get("POSTGRES_PASSWORD")

                    # Also check for POSTGRES_DB (alternate name)
                    if os.environ.get("POSTGRES_DB"):
                        credentials["database"] = os.environ.get("POSTGRES_DB")

                    logger.info("Using PostgreSQL configuration from .env.postgres file")
                    return credentials

            # Then try main .env file
            env_file = project_root / ".env"
            if env_file.exists():
                load_dotenv(env_file)
                # Check again after loading .env
                if os.environ.get("POSTGRES_PASSWORD"):
                    credentials["password"] = os.environ.get("POSTGRES_PASSWORD")
                    logger.info("Using PostgreSQL password from .env file")
                    return credentials

            # No password found in .env file
            logger.warning("No PostgreSQL password found in .env file")
            return credentials

        # In CI without password - this will fail
        if is_github_actions:
            logger.error("Running in GitHub Actions but POSTGRES_PASSWORD not set!")
            raise ValueError("POSTGRES_PASSWORD must be set in GitHub Actions")

        return credentials

    @staticmethod
    def get_connection_string() -> str:
        """Get PostgreSQL connection string for the current environment."""
        creds = TestDatabaseCredentials.get_postgres_credentials()

        # Build connection string
        conn_parts = [
            f"host={creds['host']}",
            f"port={creds['port']}",
            f"dbname={creds['database']}",
            f"user={creds['user']}",
        ]

        if creds["password"]:
            conn_parts.append(f"password={creds['password']}")

        return " ".join(conn_parts)

    @staticmethod
    def can_connect_without_password() -> bool:
        """
        Check if we can connect to PostgreSQL without a password.
        This is common in development with peer/trust authentication.
        """
        try:
            import psycopg

            creds = TestDatabaseCredentials.get_postgres_credentials()

            # Try connection without password
            conn_str = (
                f"host={creds['host']} "
                f"port={creds['port']} "
                f"dbname={creds['database']} "
                f"user={creds['user']}"
            )

            with psycopg.connect(conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception:
            return False

    @staticmethod
    def configure_test_database(config) -> None:
        """
        Configure a PipelineConfig object with test database credentials.

        Args:
            config: PipelineConfig object to configure
        """
        creds = TestDatabaseCredentials.get_postgres_credentials()

        config.database.postgresql.host = creds["host"]
        config.database.postgresql.port = int(creds["port"])
        config.database.postgresql.database = creds["database"]
        config.database.postgresql.user = creds["user"]

        if creds["password"]:
            config.database.postgresql.password = creds["password"]
