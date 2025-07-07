"""
Test database setup utilities for Pipeline v3.

Handles PostgreSQL and Qdrant server startup, test tenant creation,
and proper cleanup for both local and CI environments.
"""

import os
import subprocess
import time
import socket
from pathlib import Path
from typing import Dict, Optional, Tuple
import psycopg
import requests
import pytest

from src.pipeline_v3.scripts.tenant_management import TenantManager
from src.pipeline_v3.utils.config import PipelineConfig
from src.pipeline_v3.utils.common_utils import logger
from .database_credentials import TestDatabaseCredentials


class TestDatabaseManager:
    """Manages test database lifecycle for e2e testing."""

    def __init__(self):
        self.config = PipelineConfig()
        self.test_tenant_name = "test_tenant"
        self.test_tenant_id: Optional[str] = None
        self.test_tenant_api_key: Optional[str] = None

        # Check if running in CI
        self.is_ci = os.environ.get("CI", "false").lower() == "true"
        self.is_github_actions = os.environ.get("GITHUB_ACTIONS", "false").lower() == "true"

        # Configure database credentials based on environment
        TestDatabaseCredentials.configure_test_database(self.config)

    def check_port_open(self, host: str, port: int, timeout: float = 5.0) -> bool:
        """Check if a port is open and accepting connections."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    def start_postgresql(self) -> bool:
        """Start PostgreSQL if not running."""
        if self.check_port_open("localhost", 5432):
            logger.info("PostgreSQL is already running on port 5432")
            return True

        if self.is_github_actions:
            # In GitHub Actions, PostgreSQL should be pre-configured
            logger.info("Running in GitHub Actions - PostgreSQL should be pre-configured")
            return True

        logger.info("Starting PostgreSQL...")

        if self.is_ci:
            # Generic CI environment - try docker
            try:
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", "postgres-test",
                    "-e", "POSTGRES_PASSWORD=postgres",
                    "-e", "POSTGRES_DB=rag_lab",
                    "-p", "5432:5432",
                    "postgres:15"
                ], check=True)
                time.sleep(10)  # Wait for PostgreSQL to start
                return True
            except subprocess.CalledProcessError:
                logger.error("Failed to start PostgreSQL in CI")
                return False
        else:
            # Local development - try various methods
            # Try Docker first
            try:
                subprocess.run(["docker", "ps"], check=True, capture_output=True)
                # Docker is available
                return self._start_postgresql_docker()
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Try native PostgreSQL
                return self._start_postgresql_native()

    def _start_postgresql_docker(self) -> bool:
        """Start PostgreSQL using Docker."""
        try:
            # Check if container exists
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", "name=rag-lab-postgres"],
                capture_output=True, text=True
            )

            if "rag-lab-postgres" in result.stdout:
                # Container exists, start it
                subprocess.run(["docker", "start", "rag-lab-postgres"], check=True)
            else:
                # Create new container
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", "rag-lab-postgres",
                    "-e", "POSTGRES_PASSWORD=postgres",
                    "-e", "POSTGRES_DB=rag_lab",
                    "-p", "5432:5432",
                    "postgres:15"
                ], check=True)

            # Wait for PostgreSQL to be ready
            for _ in range(30):
                if self.check_port_open("localhost", 5432):
                    time.sleep(2)  # Extra wait for full initialization
                    return True
                time.sleep(1)

            return False
        except subprocess.CalledProcessError:
            logger.error("Failed to start PostgreSQL with Docker")
            return False

    def _start_postgresql_native(self) -> bool:
        """Start PostgreSQL using native installation."""
        try:
            # Try pg_ctl
            subprocess.run(["pg_ctl", "start"], check=True)
            time.sleep(5)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            try:
                # Try brew services (macOS)
                subprocess.run(["brew", "services", "start", "postgresql"], check=True)
                time.sleep(5)
                return True
            except (subprocess.CalledProcessError, FileNotFoundError):
                logger.error("Could not start PostgreSQL - please start it manually")
                return False

    def start_qdrant(self) -> bool:
        """Start Qdrant if not running."""
        if self.check_port_open("localhost", 6333):
            logger.info("Qdrant is already running on port 6333")
            return True

        if self.is_github_actions:
            # In GitHub Actions, use Docker service
            logger.info("Running in GitHub Actions - starting Qdrant via Docker")
            try:
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", "qdrant-test",
                    "-p", "6333:6333",
                    "qdrant/qdrant"
                ], check=True)
                time.sleep(10)
                return True
            except subprocess.CalledProcessError:
                logger.error("Failed to start Qdrant in GitHub Actions")
                return False

        logger.info("Starting Qdrant...")

        # Try Docker first
        try:
            subprocess.run(["docker", "ps"], check=True, capture_output=True)
            return self._start_qdrant_docker()
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Try script
            return self._start_qdrant_script()

    def _start_qdrant_docker(self) -> bool:
        """Start Qdrant using Docker."""
        try:
            # Check if container exists
            result = subprocess.run(
                ["docker", "ps", "-a", "--filter", "name=rag-lab-qdrant"],
                capture_output=True, text=True
            )

            if "rag-lab-qdrant" in result.stdout:
                # Container exists, start it
                subprocess.run(["docker", "start", "rag-lab-qdrant"], check=True)
            else:
                # Create new container
                subprocess.run([
                    "docker", "run", "-d",
                    "--name", "rag-lab-qdrant",
                    "-p", "6333:6333",
                    "-v", "qdrant_storage:/qdrant/storage",
                    "qdrant/qdrant"
                ], check=True)

            # Wait for Qdrant to be ready
            for _ in range(30):
                if self.check_port_open("localhost", 6333):
                    time.sleep(2)  # Extra wait for full initialization
                    return True
                time.sleep(1)

            return False
        except subprocess.CalledProcessError:
            logger.error("Failed to start Qdrant with Docker")
            return False

    def _start_qdrant_script(self) -> bool:
        """Start Qdrant using the shell script."""
        script_path = Path(__file__).parent.parent.parent.parent / "scripts" / "qdrant_server.sh"
        if script_path.exists():
            try:
                subprocess.run([str(script_path), "start"], check=True)
                time.sleep(5)
                return True
            except subprocess.CalledProcessError:
                logger.error("Failed to start Qdrant with script")
                return False
        return False

    def setup_test_database(self) -> bool:
        """Set up PostgreSQL database and schema."""
        try:
            # Get connection string from credential manager
            conn_str = TestDatabaseCredentials.get_connection_string()

            with psycopg.connect(conn_str) as conn:
                with conn.cursor() as cur:
                    # Check if schemas exist
                    cur.execute("""
                        SELECT schema_name
                        FROM information_schema.schemata
                        WHERE schema_name IN ('registry', 'search', 'jobs', 'fingerprints', 'tenants')
                    """)
                    existing_schemas = {row[0] for row in cur.fetchall()}

                    if len(existing_schemas) < 5:
                        logger.info("Database schemas missing - running migrations...")
                        # Run migrations
                        from src.pipeline_v3.scripts.setup_postgresql import setup_postgresql
                        if not setup_postgresql():
                            logger.error("Failed to set up PostgreSQL schemas")
                            return False

            return True
        except Exception as e:
            logger.error(f"Failed to set up database: {e}")
            return False

    def create_test_tenant(self) -> Dict[str, str]:
        """Create or get test tenant for testing."""
        try:
            manager = TenantManager(self.config)

            # Check if test tenant already exists
            existing_tenants = manager.list_tenants()
            for tenant in existing_tenants:
                if tenant['name'] == self.test_tenant_name:
                    logger.info(f"Test tenant already exists: {tenant['tenant_id']}")
                    self.test_tenant_id = tenant['tenant_id']
                    # Note: We can't retrieve the API key, so tests need to handle this
                    return tenant

            # Create new test tenant
            logger.info("Creating new test tenant...")
            test_tenant = manager.create_tenant(
                name=self.test_tenant_name,
                display_name="Test Tenant for E2E Testing",
                admin_email="test@example.com",
                admin_name="Test Admin",
                max_documents=1000,
                max_storage_gb=10,
                max_api_calls_per_day=10000,
                settings={
                    "purpose": "automated_testing",
                    "cleanup_on_teardown": True
                }
            )

            self.test_tenant_id = test_tenant['tenant_id']
            self.test_tenant_api_key = test_tenant['api_key']

            logger.info(f"Created test tenant: {self.test_tenant_id}")
            return test_tenant

        except Exception as e:
            logger.error(f"Failed to create test tenant: {e}")
            raise

    def cleanup_test_tenant(self):
        """Clean up test tenant data."""
        if not self.test_tenant_id:
            return

        try:
            # Get connection string from credential manager
            conn_str = TestDatabaseCredentials.get_connection_string()

            with psycopg.connect(conn_str) as conn:
                with conn.cursor() as cur:
                    # Clean up test data from all schemas
                    schemas = ['registry', 'search', 'jobs', 'fingerprints']
                    tables = {
                        'registry': ['documents'],
                        'search': ['chunks'],
                        'jobs': ['jobs'],
                        'fingerprints': ['fingerprints']
                    }

                    for schema in schemas:
                        for table in tables.get(schema, []):
                            cur.execute(f"""
                                DELETE FROM {schema}.{table}
                                WHERE tenant_id = %s
                            """, (self.test_tenant_id,))

                    conn.commit()
                    logger.info("Cleaned up test tenant data")

        except Exception as e:
            logger.error(f"Failed to cleanup test tenant: {e}")

    def ensure_databases_ready(self) -> Tuple[bool, Optional[Dict[str, str]]]:
        """Ensure all databases are running and configured."""
        # Start PostgreSQL
        if not self.start_postgresql():
            return False, None

        # Start Qdrant
        if not self.start_qdrant():
            return False, None

        # Set up database schema
        if not self.setup_test_database():
            return False, None

        # Create test tenant
        try:
            tenant_info = self.create_test_tenant()
            return True, tenant_info
        except Exception:
            return False, None


# Global instance for test session
_test_db_manager: Optional[TestDatabaseManager] = None


def get_test_database_manager() -> TestDatabaseManager:
    """Get or create the test database manager."""
    global _test_db_manager
    if _test_db_manager is None:
        _test_db_manager = TestDatabaseManager()
    return _test_db_manager


# Pytest fixtures
@pytest.fixture(scope="session")
def test_databases():
    """Ensure test databases are running for the entire test session."""
    manager = get_test_database_manager()

    # Ensure databases are ready
    success, tenant_info = manager.ensure_databases_ready()
    if not success:
        pytest.fail("Failed to set up test databases")

    yield tenant_info

    # Cleanup at end of session
    manager.cleanup_test_tenant()


@pytest.fixture(scope="function")
def test_tenant_id(test_databases):
    """Provide test tenant ID for individual tests."""
    return test_databases['tenant_id']


@pytest.fixture(scope="function")
def test_tenant_config(test_config, test_tenant_id):
    """Provide test config with test tenant ID set."""
    test_config.database.postgresql.default_tenant_id = test_tenant_id
    return test_config
