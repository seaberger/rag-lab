#!/usr/bin/env python3
"""
Setup Row-Level Security (RLS) for RAG Lab Pipeline v3

This script runs the necessary migrations to enable RLS and creates
the tenant management infrastructure.
"""

import argparse
import sys
from pathlib import Path

import psycopg
from psycopg.errors import DuplicateObject

# Add pipeline_v3 to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class RLSSetup:
    """Manages RLS setup and migration execution."""

    def __init__(self, config: PipelineConfig):
        """Initialize RLS setup with database connection."""
        self.config = config
        self.pg_settings = config.database.postgresql

        # Get password from environment if not in config
        import os

        password = self.pg_settings.password or os.environ.get(
            "POSTGRES_PASSWORD", "rag_dev_password"
        )

        self.connection_string = (
            f"postgresql://{self.pg_settings.user}:{password}"
            f"@{self.pg_settings.host}:{self.pg_settings.port}/{self.pg_settings.database}"
        )
        self.migrations_dir = Path(__file__).parent.parent / "migrations"

    def check_prerequisites(self) -> bool:
        """Check if basic tables exist before applying RLS."""
        required_tables = [
            ("registry", "documents"),
            ("search", "documents"),
            ("search", "doc_metadata"),
            ("jobs", "queue"),
            ("fingerprints", "fingerprints"),
        ]

        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                for schema, table in required_tables:
                    cur.execute(
                        """
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.tables
                            WHERE table_schema = %s AND table_name = %s
                        )
                    """,
                        (schema, table),
                    )

                    exists = cur.fetchone()[0]
                    if not exists:
                        logger.error(f"Required table {schema}.{table} does not exist")
                        return False

        logger.info("All prerequisite tables exist")
        return True

    def run_migration(self, migration_file: Path, skip_if_exists: bool = True) -> bool:
        """Run a single migration file."""
        if not migration_file.exists():
            logger.error(f"Migration file not found: {migration_file}")
            return False

        logger.info(f"Running migration: {migration_file.name}")

        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                try:
                    # Read and execute migration
                    migration_sql = migration_file.read_text()

                    # Set session to admin mode for migrations
                    cur.execute("SET app.is_admin = true")

                    # Execute the migration
                    cur.execute(migration_sql)
                    conn.commit()

                    logger.info(f"Successfully applied migration: {migration_file.name}")
                    return True

                except DuplicateObject as e:
                    if skip_if_exists:
                        logger.warning(f"Object already exists (skipping): {e}")
                        conn.rollback()
                        return True
                    else:
                        raise

                except Exception as e:
                    logger.error(f"Failed to apply migration {migration_file.name}: {e}")
                    conn.rollback()
                    return False

    def setup_rls(self, force: bool = False) -> bool:
        """Set up RLS with all necessary migrations."""
        logger.info("Starting RLS setup...")

        # Check prerequisites
        if not self.check_prerequisites():
            logger.error("Prerequisites not met. Ensure base tables exist first.")
            return False

        # Run migrations in order
        migrations = ["003_tenant_management_fixed.sql", "004_enhanced_rls_policies.sql"]

        success = True
        for migration_name in migrations:
            migration_file = self.migrations_dir / migration_name
            if not self.run_migration(migration_file, skip_if_exists=not force):
                success = False
                if not force:
                    break

        if success:
            logger.info("RLS setup completed successfully")

            # Verify RLS is enabled
            self.verify_rls_enabled()
        else:
            logger.error("RLS setup failed")

        return success

    def verify_rls_enabled(self) -> bool:
        """Verify that RLS is properly enabled on all tables."""
        tables_to_check = [
            ("registry", "documents"),
            ("registry", "index_entries"),
            ("search", "keyword_search"),
            ("search", "doc_metadata"),
            ("jobs", "queue"),
            ("fingerprints", "fingerprints"),
            ("tenants", "tenants"),
            ("tenants", "api_keys"),
        ]

        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                all_enabled = True

                for schema, table in tables_to_check:
                    cur.execute(
                        """
                        SELECT relrowsecurity
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        WHERE n.nspname = %s AND c.relname = %s
                    """,
                        (schema, table),
                    )

                    result = cur.fetchone()
                    if result and result[0]:
                        logger.info(f"✓ RLS enabled on {schema}.{table}")
                    else:
                        logger.warning(f"✗ RLS NOT enabled on {schema}.{table}")
                        all_enabled = False

                return all_enabled

    def create_test_tenant(self) -> dict:
        """Create a test tenant for verification."""
        from src.pipeline_v3.scripts.tenant_management import TenantManager

        manager = TenantManager(self.config)

        try:
            tenant = manager.create_tenant(
                name="rls_test_tenant",
                display_name="RLS Test Tenant",
                admin_email="test@example.com",
                max_documents=10,
                max_storage_gb=1,
            )

            logger.info(f"Created test tenant: {tenant['name']}")
            logger.info(f"Test tenant ID: {tenant['tenant_id']}")
            logger.info(f"Test API key: {tenant['api_key']}")

            return tenant

        except Exception as e:
            logger.error(f"Failed to create test tenant: {e}")
            return None

    def test_rls_isolation(self, tenant_id: str) -> bool:
        """Test that RLS properly isolates tenant data."""
        logger.info("Testing RLS isolation...")

        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                # Test 1: Set tenant context and query
                cur.execute("SELECT tenants.set_current_tenant(%s)", (tenant_id,))

                # Should only see data for this tenant
                cur.execute("SELECT COUNT(*) as cnt FROM registry.documents")
                count = cur.fetchone()[0]
                logger.info(f"Documents visible to tenant: {count}")

                # Test 2: Try to query other tenant's data
                cur.execute(
                    """
                    SELECT COUNT(*) as cnt FROM registry.documents
                    WHERE tenant_id != %s
                """,
                    (tenant_id,),
                )
                other_count = cur.fetchone()[0]

                if other_count == 0:
                    logger.info("✓ RLS properly blocking other tenant data")
                    return True
                else:
                    logger.error(
                        f"✗ RLS FAILURE: Can see {other_count} documents from other tenants!"
                    )
                    return False


def main():
    """CLI interface for RLS setup."""
    parser = argparse.ArgumentParser(description="Setup Row-Level Security for RAG Lab")
    parser.add_argument("--force", action="store_true", help="Force re-run migrations")
    parser.add_argument("--verify-only", action="store_true", help="Only verify RLS status")
    parser.add_argument("--create-test-tenant", action="store_true", help="Create a test tenant")
    parser.add_argument("--test-isolation", help="Test RLS isolation with given tenant ID")

    args = parser.parse_args()

    # Load configuration
    config = PipelineConfig()
    setup = RLSSetup(config)

    try:
        if args.verify_only:
            if setup.verify_rls_enabled():
                print("\n✓ RLS is properly enabled on all tables")
                sys.exit(0)
            else:
                print("\n✗ RLS is not fully enabled")
                sys.exit(1)

        elif args.test_isolation:
            if setup.test_rls_isolation(args.test_isolation):
                print("\n✓ RLS isolation test passed")
                sys.exit(0)
            else:
                print("\n✗ RLS isolation test failed")
                sys.exit(1)

        elif args.create_test_tenant:
            tenant = setup.create_test_tenant()
            if tenant:
                print("\n✓ Test tenant created successfully")
                print("\nYou can test isolation with:")
                print(f"  python {__file__} --test-isolation {tenant['tenant_id']}")
                sys.exit(0)
            else:
                print("\n✗ Failed to create test tenant")
                sys.exit(1)

        # Run full RLS setup
        elif setup.setup_rls(force=args.force):
            print("\n✓ RLS setup completed successfully")
            print("\nNext steps:")
            print(
                "1. Create tenants: python tenant_management.py create <name> <display_name> <email>"
            )
            print("2. Test isolation: python setup_rls.py --create-test-tenant")
            print("3. Verify status: python setup_rls.py --verify-only")
            sys.exit(0)
        else:
            print("\n✗ RLS setup failed")
            sys.exit(1)

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
