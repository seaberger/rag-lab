#!/usr/bin/env python3
"""
Minimal database setup for CI/CD testing.

This script provides fast, minimal database setup for CI environments.
It focuses on speed and reliability over features.

Key differences from full setup:
- No interactive prompts
- Minimal logging
- Fast failure with clear errors
- Only creates test tenant
- Skips optional features
"""

import sys
from pathlib import Path

import psycopg
from psycopg import sql

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from src.pipeline_v3.tests.fixtures.database_credentials import TestDatabaseCredentials
from src.pipeline_v3.utils.config import PipelineConfig


class CIDatabaseSetup:
    """Fast database setup for CI environments."""

    def __init__(self):
        self.config = None
        self.test_tenant_id = None
        self.errors = []

    def log(self, message: str, level: str = "INFO"):
        """Simple logging for CI."""
        print(f"[{level}] {message}")

    def error(self, message: str):
        """Log error and track it."""
        self.errors.append(message)
        self.log(message, "ERROR")

    def setup_postgresql(self) -> bool:
        """Set up PostgreSQL with migrations."""
        try:
            # Get credentials from CI environment
            creds = TestDatabaseCredentials.get_postgres_credentials()

            self.log(f"Connecting to PostgreSQL at {creds['host']}:{creds['port']}")

            # First ensure database exists
            conn_str = (
                f"host={creds['host']} port={creds['port']} dbname=postgres user={creds['user']}"
            )
            if creds["password"]:
                conn_str += f" password={creds['password']}"

            conn = psycopg.connect(conn_str)
            conn.autocommit = True
            cur = conn.cursor()

            # Check if database exists
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (creds["database"],))
            if not cur.fetchone():
                self.log(f"Creating database {creds['database']}")
                cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(creds["database"])))

            cur.close()
            conn.close()

            # Now connect to our database
            conn_str = (
                f"host={creds['host']} "
                f"port={creds['port']} "
                f"dbname={creds['database']} "
                f"user={creds['user']}"
            )
            if creds["password"]:
                conn_str += f" password={creds['password']}"

            conn = psycopg.connect(conn_str)
            cur = conn.cursor()

            # Run migrations in order
            migrations_dir = Path(__file__).parent.parent / "migrations" / "postgres"
            if not migrations_dir.exists():
                self.error(f"Migrations directory not found: {migrations_dir}")
                return False

            migration_files = sorted(migrations_dir.glob("*.sql"))

            for migration_file in migration_files:
                self.log(f"Running migration: {migration_file.name}")
                sql_content = migration_file.read_text()

                try:
                    cur.execute(sql_content)
                    conn.commit()
                except Exception as e:
                    # Some migrations might fail if already applied
                    if "already exists" in str(e) or "duplicate" in str(e):
                        self.log(f"Migration already applied: {migration_file.name}")
                        conn.rollback()
                    else:
                        raise

            # Verify critical tables exist
            required_tables = ["documents", "index_entries", "keyword_search", "jobs", "tenants"]
            cur.execute("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'registry'
            """)
            existing_tables = {row[0] for row in cur.fetchall()}

            missing_tables = set(required_tables) - existing_tables
            if missing_tables:
                self.error(f"Missing required tables: {missing_tables}")
                return False

            self.log("PostgreSQL setup complete")

            cur.close()
            conn.close()
            return True

        except Exception as e:
            self.error(f"PostgreSQL setup failed: {e}")
            return False

    def create_test_tenant(self) -> bool:
        """Create test tenant for CI."""
        try:
            # Load config
            config_path = (
                Path(__file__).parent.parent.parent / "pipeline_v3" / "config_postgres.yaml"
            )
            if not config_path.exists():
                # Try project root
                config_path = Path(__file__).parent.parent.parent.parent / "config_postgres.yaml"

            if not config_path.exists():
                self.error("Config file not found: config_postgres.yaml")
                return False

            self.config = PipelineConfig.from_yaml(str(config_path))

            # Apply test credentials
            TestDatabaseCredentials.configure_test_database(self.config)

            # Import tenant manager
            from src.pipeline_v3.scripts.tenant_management import TenantManager

            manager = TenantManager(self.config)

            # Check if test tenant exists
            existing_tenants = manager.list_tenants()
            test_tenant = None

            for tenant in existing_tenants:
                if tenant["name"] == "test_tenant":
                    test_tenant = tenant
                    self.log(f"Test tenant already exists: {tenant['tenant_id']}")
                    break

            if not test_tenant:
                # Create test tenant
                self.log("Creating test tenant")
                test_tenant = manager.create_tenant(
                    name="test_tenant",
                    display_name="CI Test Tenant",
                    admin_email="ci@test.com",
                    max_documents=1000,
                    max_storage_gb=10,
                    max_api_calls_per_day=10000,
                )
                self.log(f"Created test tenant: {test_tenant['tenant_id']}")

            self.test_tenant_id = test_tenant["tenant_id"]
            return True

        except Exception as e:
            self.error(f"Failed to create test tenant: {e}")
            return False

    def verify_qdrant(self) -> bool:
        """Verify Qdrant is accessible."""
        try:
            import requests

            # Check Qdrant health
            response = requests.get("http://localhost:6333/health", timeout=5)
            if response.status_code == 200:
                self.log("Qdrant is healthy")
                return True
            else:
                self.error(f"Qdrant health check failed: {response.status_code}")
                return False

        except Exception as e:
            self.error(f"Cannot connect to Qdrant: {e}")
            return False

    def run(self) -> bool:
        """Run complete CI database setup."""
        self.log("Starting CI database setup")

        # Setup PostgreSQL
        if not self.setup_postgresql():
            return False

        # Create test tenant
        if not self.create_test_tenant():
            return False

        # Verify Qdrant
        if not self.verify_qdrant():
            self.log("WARNING: Qdrant not available - vector tests will fail", "WARN")
            # Don't fail completely - some tests might not need Qdrant

        # Success
        self.log("CI database setup complete!")

        # Write test tenant info for tests to use in a secure temp file
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", delete=False, prefix="ci_test_tenant_", suffix=".txt"
        ) as f:
            f.write(self.test_tenant_id)
            self.log(f"Test tenant ID written to: {f.name}")

        return True

    def print_summary(self):
        """Print setup summary."""
        print("\n" + "=" * 50)
        print("CI DATABASE SETUP SUMMARY")
        print("=" * 50)

        if self.errors:
            print(f"\n❌ Setup failed with {len(self.errors)} errors:")
            for error in self.errors:
                print(f"  - {error}")
        else:
            print("\n✅ Setup completed successfully!")
            if self.test_tenant_id:
                print(f"  Test tenant ID: {self.test_tenant_id}")

        print("=" * 50 + "\n")


def main():
    """Main entry point."""
    # For CI, we want fast failure
    setup = CIDatabaseSetup()

    try:
        success = setup.run()
        setup.print_summary()

        if not success:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\nSetup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nFATAL ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
