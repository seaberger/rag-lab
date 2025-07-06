#!/usr/bin/env python3
"""Quick script to check PostgreSQL configuration."""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from src.pipeline_v3.utils.config import PipelineConfig


def main():
    # Load configuration
    config = PipelineConfig.from_yaml()

    print("PostgreSQL Configuration Check")
    print("=" * 40)
    print(f"Database Backend: {config.database.backend}")
    print("PostgreSQL Settings:")
    print(f"  Host: {config.database.postgresql.host}")
    print(f"  Port: {config.database.postgresql.port}")
    print(f"  Database: {config.database.postgresql.database}")
    print(f"  User: {config.database.postgresql.user}")
    print(
        f"  Password: {'*' * len(config.database.postgresql.password) if config.database.postgresql.password else 'NOT SET'}"
    )
    print(f"  SSL Mode: {config.database.postgresql.ssl_mode}")
    print(f"  Min Connections: {config.database.postgresql.min_connections}")
    print(f"  Max Connections: {config.database.postgresql.max_connections}")
    print(f"  Enable RLS: {config.database.postgresql.enable_rls}")
    print(f"  Default Tenant ID: {config.database.postgresql.default_tenant_id}")
    print()
    print("Migration Settings:")
    print(f"  Auto Migrate: {config.database.auto_migrate}")
    print(f"  Migration Batch Size: {config.database.migration_batch_size}")
    print(f"  Enable Fallback: {config.database.enable_fallback}")

    # Check environment
    if os.getenv("POSTGRES_PASSWORD"):
        print("\n✓ POSTGRES_PASSWORD environment variable is set")
    else:
        print("\n⚠️  POSTGRES_PASSWORD environment variable not set")


if __name__ == "__main__":
    main()
