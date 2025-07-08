#!/usr/bin/env python3
"""
Setup CI Test Tenant for RAG Lab Pipeline v3

This script creates a dedicated test tenant for CI/CD testing purposes.
The tenant will have a known UUID that can be used in test configurations.
"""

import os
import sys
from pathlib import Path
from uuid import UUID

import psycopg
from dotenv import load_dotenv

# Add pipeline_v3 to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig

# Fixed tenant ID for CI testing - this should be consistent across all test runs
CI_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
CI_TENANT_NAME = "test_ci"
CI_TENANT_DISPLAY_NAME = "CI Test Tenant"


def setup_ci_tenant():
    """Create or verify the CI test tenant."""

    # Load PostgreSQL credentials
    env_postgres = Path(__file__).parent.parent.parent.parent / ".env.postgres"
    if env_postgres.exists():
        load_dotenv(env_postgres, override=True)

    # Get database connection info
    config = PipelineConfig()
    pg_settings = config.database.postgresql

    password = os.environ.get("POSTGRES_PASSWORD", pg_settings.password)
    if not password:
        raise ValueError("PostgreSQL password not found in environment or config")

    connection_string = (
        f"postgresql://{pg_settings.user}:{password}"
        f"@{pg_settings.host}:{pg_settings.port}/{pg_settings.database}"
    )

    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cur:
            # Set admin mode
            cur.execute("SET app.is_admin = true")

            # Check if tenant already exists
            cur.execute(
                "SELECT tenant_id FROM tenants.tenants WHERE tenant_id = %s", (CI_TENANT_ID,)
            )

            if cur.fetchone():
                logger.info(f"CI test tenant already exists: {CI_TENANT_ID}")
                return CI_TENANT_ID

            # Create the CI test tenant
            cur.execute(
                """
                INSERT INTO tenants.tenants (
                    tenant_id, name, display_name, admin_email, admin_name,
                    settings, max_documents, max_storage_gb, max_api_calls_per_day,
                    is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (tenant_id) DO NOTHING
                """,
                (
                    CI_TENANT_ID,
                    CI_TENANT_NAME,
                    CI_TENANT_DISPLAY_NAME,
                    "ci@test.local",
                    "CI Test Admin",
                    "{}",  # Empty JSON settings
                    1000,  # Lower limits for test tenant
                    10,
                    10000,
                    True,
                ),
            )

            # Create audit log entry
            cur.execute(
                """
                INSERT INTO tenants.audit_log (
                    tenant_id, operation, details, performed_by
                ) VALUES (%s, %s, %s::jsonb, %s)
                """,
                (
                    CI_TENANT_ID,
                    "tenant.create",
                    '{"resource_type": "tenant", "resource_id": "'
                    + str(CI_TENANT_ID)
                    + '", "status": "success", "purpose": "CI testing"}',
                    "ci_setup_script",
                ),
            )

            conn.commit()
            logger.info(f"Created CI test tenant: {CI_TENANT_ID}")

    # Create Qdrant collection for the test tenant if in server mode
    if config.qdrant.mode == "server":
        try:
            import qdrant_client
            from qdrant_client.models import Distance, VectorParams

            client = qdrant_client.QdrantClient(
                host=config.qdrant.server.host, port=config.qdrant.server.port
            )

            # Use a specific collection naming pattern for CI
            collection_name = f"ci_test_{CI_TENANT_ID}".replace("-", "_")

            collections = client.get_collections().collections
            if not any(c.name == collection_name for c in collections):
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=config.openai.dimensions, distance=Distance.COSINE
                    ),
                )
                logger.info(f"Created CI Qdrant collection: {collection_name}")
            else:
                logger.info(f"CI Qdrant collection already exists: {collection_name}")

        except Exception as e:
            logger.warning(f"Could not create Qdrant collection: {e}")
            logger.info("This is okay if Qdrant is not running locally")

    return CI_TENANT_ID


def verify_ci_tenant():
    """Verify the CI test tenant exists and is active."""

    # Load PostgreSQL credentials
    env_postgres = Path(__file__).parent.parent.parent.parent / ".env.postgres"
    if env_postgres.exists():
        load_dotenv(env_postgres, override=True)

    config = PipelineConfig()
    pg_settings = config.database.postgresql

    password = os.environ.get("POSTGRES_PASSWORD", pg_settings.password)
    connection_string = (
        f"postgresql://{pg_settings.user}:{password}"
        f"@{pg_settings.host}:{pg_settings.port}/{pg_settings.database}"
    )

    with psycopg.connect(connection_string) as conn:
        with conn.cursor() as cur:
            # Set admin mode
            cur.execute("SET app.is_admin = true")

            # Check tenant
            cur.execute(
                """
                SELECT tenant_id, name, is_active
                FROM tenants.tenants
                WHERE tenant_id = %s
                """,
                (CI_TENANT_ID,),
            )

            result = cur.fetchone()
            if result:
                tenant_id, name, is_active = result
                print("✓ CI test tenant found:")
                print(f"  ID: {tenant_id}")
                print(f"  Name: {name}")
                print(f"  Active: {is_active}")
                return True
            else:
                print("✗ CI test tenant not found")
                return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Setup CI test tenant")
    parser.add_argument(
        "--verify", action="store_true", help="Verify CI tenant exists instead of creating"
    )

    args = parser.parse_args()

    try:
        if args.verify:
            success = verify_ci_tenant()
            sys.exit(0 if success else 1)
        else:
            tenant_id = setup_ci_tenant()
            print(f"\n✓ CI test tenant ready: {tenant_id}")
            print(f"  Name: {CI_TENANT_NAME}")
            print(f"  Display: {CI_TENANT_DISPLAY_NAME}")
            print("\nUse this tenant ID in your test configurations.")

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
