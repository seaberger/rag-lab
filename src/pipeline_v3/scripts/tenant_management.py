#!/usr/bin/env python3
"""
Tenant Management Utilities for RAG Lab Pipeline v3

This script provides comprehensive tenant management functionality including:
- Creating new tenants with proper setup
- Managing API keys
- Setting up tenant isolation
- Testing multi-tenant functionality
"""

import argparse
import hashlib
import secrets
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List

import psycopg
from psycopg.rows import dict_row

# Add pipeline_v3 to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class TenantManager:
    """Manages tenant operations for multi-tenant RAG Lab deployment."""

    def __init__(self, config: PipelineConfig):
        """Initialize tenant manager with database connection."""
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

    def create_tenant(
        self,
        name: str,
        display_name: str,
        admin_email: str,
        admin_name: str | None = None,
        settings: Dict[str, Any] | None = None,
        max_documents: int = 10000,
        max_storage_gb: int = 100,
        max_api_calls_per_day: int = 100000,
    ) -> Dict[str, Any]:
        """Create a new tenant with all necessary setup."""

        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Set admin mode for this operation
                cur.execute("SET app.is_admin = true")

                # Create tenant
                cur.execute(
                    """
                    INSERT INTO tenants.tenants (
                        name, display_name, admin_email, admin_name,
                        settings, max_documents, max_storage_gb, max_api_calls_per_day
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                """,
                    (
                        name,
                        display_name,
                        admin_email,
                        admin_name,
                        psycopg.types.json.Json(settings or {}),
                        max_documents,
                        max_storage_gb,
                        max_api_calls_per_day,
                    ),
                )

                tenant = cur.fetchone()
                tenant_id = tenant["tenant_id"]

                # Create default API key
                api_key = self._generate_api_key()
                api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

                cur.execute(
                    """
                    INSERT INTO tenants.api_keys (
                        tenant_id, key_hash, key_prefix, name,
                        expires_at, scopes
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING key_id
                """,
                    (
                        tenant_id,
                        api_key_hash,
                        api_key[:8],
                        "Default API Key",
                        datetime.now() + timedelta(days=365),
                        ["read", "write", "admin"],
                    ),
                )

                key_id = cur.fetchone()["key_id"]

                # Create Qdrant collection for tenant
                self._create_qdrant_collection(str(tenant_id))

                # Create storage directories
                self._create_storage_directories(str(tenant_id))

                # Log creation in audit log
                import json

                cur.execute(
                    """
                    INSERT INTO tenants.audit_log (
                        tenant_id, operation, details, performed_by
                    ) VALUES (%s, %s, %s::jsonb, %s)
                """,
                    (
                        tenant_id,
                        "tenant.create",
                        json.dumps(
                            {
                                "resource_type": "tenant",
                                "resource_id": str(tenant_id),
                                "status": "success",
                            }
                        ),
                        "system",
                    ),
                )

                conn.commit()

        logger.info(f"Created tenant: {name} (ID: {tenant_id})")

        return {
            "tenant_id": str(tenant_id),
            "name": name,
            "display_name": display_name,
            "api_key": api_key,
            "api_key_id": str(key_id),
            "api_key_prefix": api_key[:8],
        }

    def _generate_api_key(self) -> str:
        """Generate a secure API key."""
        return f"rl_{secrets.token_urlsafe(32)}"

    def _create_qdrant_collection(self, tenant_id: str):
        """Create Qdrant collection for tenant."""
        if self.config.qdrant.mode == "server":
            import qdrant_client
            from qdrant_client.models import Distance, VectorParams

            client = qdrant_client.QdrantClient(
                host=self.config.qdrant.server.host, port=self.config.qdrant.server.port
            )

            collection_name = f"tenant_{tenant_id}"

            # Check if collection exists
            collections = client.get_collections().collections
            if not any(c.name == collection_name for c in collections):
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=self.config.openai.dimensions, distance=Distance.COSINE
                    ),
                )
                logger.info(f"Created Qdrant collection: {collection_name}")

    def _create_storage_directories(self, tenant_id: str):
        """Create storage directories for tenant."""
        base_storage = Path(self.config.storage.base_dir)
        tenant_storage = base_storage / f"tenant_{tenant_id}"

        # Create directories
        (tenant_storage / "documents").mkdir(parents=True, exist_ok=True)
        (tenant_storage / "cache").mkdir(parents=True, exist_ok=True)
        (tenant_storage / "temp").mkdir(parents=True, exist_ok=True)

        logger.info(f"Created storage directories at: {tenant_storage}")

    def list_tenants(self) -> List[Dict[str, Any]]:
        """List all tenants with basic info."""
        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Set admin mode
                cur.execute("SET app.is_admin = true")

                cur.execute("""
                    SELECT
                        t.tenant_id, t.name, t.display_name, t.is_active,
                        t.created_at, t.admin_email,
                        COUNT(DISTINCT d.doc_id) as document_count,
                        COUNT(DISTINCT ak.key_id) as api_key_count
                    FROM tenants.tenants t
                    LEFT JOIN registry.documents d ON d.tenant_id = t.tenant_id
                    LEFT JOIN tenants.api_keys ak ON ak.tenant_id = t.tenant_id
                    GROUP BY t.tenant_id
                    ORDER BY t.created_at DESC
                """)

                return cur.fetchall()

    def get_tenant_info(self, tenant_name: str) -> Dict[str, Any]:
        """Get detailed information about a tenant."""
        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Set admin mode
                cur.execute("SET app.is_admin = true")

                # Get tenant info
                cur.execute(
                    """
                    SELECT * FROM tenants.tenants
                    WHERE name = %s
                """,
                    (tenant_name,),
                )

                tenant = cur.fetchone()
                if not tenant:
                    raise ValueError(f"Tenant not found: {tenant_name}")

                tenant_id = tenant["tenant_id"]

                # Get usage stats
                cur.execute(
                    """
                    SELECT
                        COUNT(*) as document_count,
                        COALESCE(SUM(size), 0) as total_size_bytes
                    FROM registry.documents
                    WHERE tenant_id = %s
                """,
                    (tenant_id,),
                )

                stats = cur.fetchone()

                # Get API keys
                cur.execute(
                    """
                    SELECT
                        key_id, name, key_prefix, created_at,
                        last_used_at, expires_at, is_active
                    FROM tenants.api_keys
                    WHERE tenant_id = %s
                    ORDER BY created_at DESC
                """,
                    (tenant_id,),
                )

                api_keys = cur.fetchall()

                # Get recent activity
                cur.execute(
                    """
                    SELECT
                        operation, performed_at, details, performed_by
                    FROM tenants.audit_log
                    WHERE tenant_id = %s
                    ORDER BY performed_at DESC
                    LIMIT 10
                """,
                    (tenant_id,),
                )

                recent_activity = cur.fetchall()

                return {
                    "tenant": tenant,
                    "statistics": {
                        "document_count": stats["document_count"],
                        "storage_used_mb": stats["total_size_bytes"] / (1024 * 1024),
                        "api_key_count": len(api_keys),
                    },
                    "api_keys": api_keys,
                    "recent_activity": recent_activity,
                }

    def create_api_key(
        self, tenant_name: str, key_name: str, expires_days: int = 365, scopes: List[str] = None
    ) -> Dict[str, Any]:
        """Create a new API key for a tenant."""
        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Set admin mode
                cur.execute("SET app.is_admin = true")

                # Get tenant ID
                cur.execute(
                    """
                    SELECT tenant_id FROM tenants.tenants
                    WHERE name = %s AND is_active = true
                """,
                    (tenant_name,),
                )

                result = cur.fetchone()
                if not result:
                    raise ValueError(f"Tenant not found or inactive: {tenant_name}")

                tenant_id = result["tenant_id"]

                # Generate API key
                api_key = self._generate_api_key()
                api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

                # Create key record
                cur.execute(
                    """
                    INSERT INTO tenants.api_keys (
                        tenant_id, key_hash, key_prefix, name,
                        expires_at, scopes
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING key_id
                """,
                    (
                        tenant_id,
                        api_key_hash,
                        api_key[:8],
                        key_name,
                        datetime.now() + timedelta(days=expires_days),
                        scopes or ["read", "write"],
                    ),
                )

                key_id = cur.fetchone()["key_id"]

                # Audit log
                cur.execute(
                    """
                    INSERT INTO tenants.audit_log (
                        tenant_id, action, resource_type, resource_id, status
                    ) VALUES (%s, %s, %s, %s, %s)
                """,
                    (tenant_id, "api_key.create", "api_key", str(key_id), "success"),
                )

                conn.commit()

        return {
            "api_key": api_key,
            "api_key_id": str(key_id),
            "tenant_name": tenant_name,
            "key_name": key_name,
            "expires_days": expires_days,
        }

    def deactivate_tenant(self, tenant_name: str) -> bool:
        """Deactivate a tenant (soft delete)."""
        with psycopg.connect(self.connection_string, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # Set admin mode
                cur.execute("SET app.is_admin = true")

                # Deactivate tenant
                cur.execute(
                    """
                    UPDATE tenants.tenants
                    SET is_active = false, updated_at = NOW()
                    WHERE name = %s
                    RETURNING tenant_id
                """,
                    (tenant_name,),
                )

                result = cur.fetchone()
                if not result:
                    raise ValueError(f"Tenant not found: {tenant_name}")

                tenant_id = result["tenant_id"]

                # Deactivate all API keys
                cur.execute(
                    """
                    UPDATE tenants.api_keys
                    SET is_active = false
                    WHERE tenant_id = %s
                """,
                    (tenant_id,),
                )

                # Audit log
                cur.execute(
                    """
                    INSERT INTO tenants.audit_log (
                        tenant_id, action, resource_type, resource_id, status
                    ) VALUES (%s, %s, %s, %s, %s)
                """,
                    (tenant_id, "tenant.deactivate", "tenant", str(tenant_id), "success"),
                )

                conn.commit()

        logger.info(f"Deactivated tenant: {tenant_name}")
        return True

    def run_migrations(self):
        """Run tenant management migrations."""
        migrations_dir = Path(__file__).parent.parent / "migrations"

        with psycopg.connect(self.connection_string) as conn:
            with conn.cursor() as cur:
                # Set admin mode
                cur.execute("SET app.is_admin = true")

                # Run tenant management migration
                migration_file = migrations_dir / "003_tenant_management.sql"
                if migration_file.exists():
                    logger.info("Running tenant management migration...")
                    cur.execute(migration_file.read_text())
                    conn.commit()

                # Run RLS policies migration
                rls_file = migrations_dir / "004_enhanced_rls_policies.sql"
                if rls_file.exists():
                    logger.info("Running RLS policies migration...")
                    cur.execute(rls_file.read_text())
                    conn.commit()

        logger.info("Migrations completed successfully")


def main():
    """CLI interface for tenant management."""
    parser = argparse.ArgumentParser(description="RAG Lab Tenant Management")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create tenant command
    create_parser = subparsers.add_parser("create", help="Create a new tenant")
    create_parser.add_argument("name", help="Unique tenant name (lowercase, no spaces)")
    create_parser.add_argument("display_name", help="Display name for tenant")
    create_parser.add_argument("admin_email", help="Admin email address")
    create_parser.add_argument("--admin-name", help="Admin name")
    create_parser.add_argument("--max-documents", type=int, default=10000)
    create_parser.add_argument("--max-storage-gb", type=int, default=100)
    create_parser.add_argument("--max-api-calls", type=int, default=100000)

    # List tenants command
    subparsers.add_parser("list", help="List all tenants")

    # Get tenant info command
    info_parser = subparsers.add_parser("info", help="Get tenant information")
    info_parser.add_argument("name", help="Tenant name")

    # Create API key command
    key_parser = subparsers.add_parser("create-key", help="Create API key for tenant")
    key_parser.add_argument("tenant_name", help="Tenant name")
    key_parser.add_argument("key_name", help="Name for the API key")
    key_parser.add_argument("--expires-days", type=int, default=365)
    key_parser.add_argument("--scopes", nargs="+", default=["read", "write"])

    # Deactivate tenant command
    deactivate_parser = subparsers.add_parser("deactivate", help="Deactivate a tenant")
    deactivate_parser.add_argument("name", help="Tenant name")

    # Run migrations command
    subparsers.add_parser("migrate", help="Run tenant migrations")

    args = parser.parse_args()

    # Load configuration
    config = PipelineConfig()
    manager = TenantManager(config)

    try:
        if args.command == "create":
            result = manager.create_tenant(
                name=args.name,
                display_name=args.display_name,
                admin_email=args.admin_email,
                admin_name=args.admin_name,
                max_documents=args.max_documents,
                max_storage_gb=args.max_storage_gb,
                max_api_calls_per_day=args.max_api_calls,
            )
            print("\nTenant created successfully!")
            print(f"Tenant ID: {result['tenant_id']}")
            print(f"API Key: {result['api_key']}")
            print("\nIMPORTANT: Save this API key securely. It cannot be retrieved later.")

        elif args.command == "list":
            tenants = manager.list_tenants()
            print(f"\nFound {len(tenants)} tenants:\n")
            for tenant in tenants:
                status = "Active" if tenant["is_active"] else "Inactive"
                print(f"- {tenant['name']} ({tenant['display_name']})")
                print(f"  Status: {status}")
                print(f"  Documents: {tenant['document_count']}")
                print(f"  API Keys: {tenant['api_key_count']}")
                print(f"  Created: {tenant['created_at']}")
                print()

        elif args.command == "info":
            info = manager.get_tenant_info(args.name)
            tenant = info["tenant"]
            stats = info["statistics"]

            print(f"\nTenant: {tenant['display_name']} ({tenant['name']})")
            print(f"ID: {tenant['tenant_id']}")
            print(f"Status: {'Active' if tenant['is_active'] else 'Inactive'}")
            print(f"Created: {tenant['created_at']}")
            print("\nStatistics:")
            print(f"  Documents: {stats['document_count']}")
            print(f"  Storage: {stats['storage_used_mb']:.2f} MB")
            print(f"  API Keys: {stats['api_key_count']}")

            if info["api_keys"]:
                print("\nAPI Keys:")
                for key in info["api_keys"]:
                    status = "Active" if key["is_active"] else "Inactive"
                    print(f"  - {key['name']} ({key['key_prefix']}...)")
                    print(f"    Status: {status}")
                    print(f"    Expires: {key['expires_at']}")

        elif args.command == "create-key":
            result = manager.create_api_key(
                tenant_name=args.tenant_name,
                key_name=args.key_name,
                expires_days=args.expires_days,
                scopes=args.scopes,
            )
            print("\nAPI Key created successfully!")
            print(f"Key: {result['api_key']}")
            print(f"Key ID: {result['api_key_id']}")
            print("\nIMPORTANT: Save this API key securely. It cannot be retrieved later.")

        elif args.command == "deactivate":
            if (
                input(
                    f"Are you sure you want to deactivate tenant '{args.name}'? (yes/no): "
                ).lower()
                == "yes"
            ):
                manager.deactivate_tenant(args.name)
                print(f"\nTenant '{args.name}' has been deactivated.")
            else:
                print("Deactivation cancelled.")

        elif args.command == "migrate":
            manager.run_migrations()
            print("\nMigrations completed successfully.")

        else:
            parser.print_help()

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
