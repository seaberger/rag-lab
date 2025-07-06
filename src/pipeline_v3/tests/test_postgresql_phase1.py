"""
Test script for PostgreSQL Phase 1 implementation.

This script tests:
1. Configuration loading
2. PostgreSQL connection
3. Base class functionality
4. Schema creation via migrations
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from src.pipeline_v3.utils.config import PipelineConfig, PostgreSQLSettings, DatabaseSettings
from src.pipeline_v3.core.postgres_base import PostgreSQLBase


def test_configuration():
    """Test PostgreSQL configuration loading."""
    print("\n=== Testing Configuration ===")

    # Test default configuration
    config = PipelineConfig()
    print(f"✓ Default database backend: {config.database.backend}")
    print(f"✓ PostgreSQL host: {config.database.postgresql.host}")
    print(f"✓ PostgreSQL port: {config.database.postgresql.port}")
    print(f"✓ PostgreSQL database: {config.database.postgresql.database}")

    # Test environment variable loading
    if os.getenv("POSTGRES_PASSWORD"):
        print(f"✓ PostgreSQL password loaded from environment")
    else:
        print("⚠️  No POSTGRES_PASSWORD environment variable set")

    # Test configuration structure
    assert isinstance(config.database, DatabaseSettings)
    assert isinstance(config.database.postgresql, PostgreSQLSettings)
    print("✓ Configuration structure validated")

    return config


def test_postgres_base_sync(config):
    """Test synchronous PostgreSQL base functionality."""
    print("\n=== Testing Synchronous PostgreSQL Base ===")

    try:
        # Create base instance
        db = PostgreSQLBase(config.database.postgresql, "test")
        print("✓ PostgreSQL base instance created")

        # Initialize connection pool
        db.initialize()
        print("✓ Connection pool initialized")

        # Test basic query
        result = db.fetch_one("SELECT 1 as test")
        assert result['test'] == 1
        print("✓ Basic query executed successfully")

        # Test pool stats
        stats = db.get_pool_stats()
        print(f"✓ Pool stats: {stats}")

        # Test table existence check
        exists = db.table_exists("nonexistent_table")
        assert not exists
        print("✓ Table existence check working")

        # Close pool
        db.close()
        print("✓ Connection pool closed")

        return True

    except Exception as e:
        print(f"✗ Synchronous test failed: {e}")
        return False


async def test_postgres_base_async(config):
    """Test asynchronous PostgreSQL base functionality."""
    print("\n=== Testing Asynchronous PostgreSQL Base ===")

    try:
        # Create base instance
        db = PostgreSQLBase(config.database.postgresql, "test")
        print("✓ PostgreSQL base instance created")

        # Initialize async connection pool
        await db.initialize_async()
        print("✓ Async connection pool initialized")

        # Test basic query
        result = await db.fetch_one_async("SELECT 2 as test")
        assert result['test'] == 2
        print("✓ Async query executed successfully")

        # Test transaction
        async with db.transaction_async() as conn:
            await conn.execute("SELECT 1")
        print("✓ Async transaction executed successfully")

        # Test pool stats
        stats = db.get_pool_stats()
        print(f"✓ Async pool stats: {stats}")

        # Close pool
        await db.close_async()
        print("✓ Async connection pool closed")

        return True

    except Exception as e:
        print(f"✗ Asynchronous test failed: {e}")
        return False


def test_schema_creation(config):
    """Test if we can create schemas (requires database access)."""
    print("\n=== Testing Schema Creation ===")

    try:
        # This will only work if PostgreSQL is running and accessible
        db = PostgreSQLBase(config.database.postgresql, "test_schema")
        db.initialize()

        # Try to create a test schema
        db.create_schema_if_not_exists()
        print("✓ Test schema created successfully")

        # Check if schema exists
        result = db.fetch_one("""
            SELECT EXISTS (
                SELECT 1 FROM information_schema.schemata
                WHERE schema_name = %s
            ) as exists
        """, ("test_schema",))

        assert result['exists']
        print("✓ Schema existence verified")

        # Clean up - drop test schema
        db.execute("DROP SCHEMA IF EXISTS test_schema CASCADE")
        print("✓ Test schema cleaned up")

        db.close()
        return True

    except Exception as e:
        print(f"✗ Schema creation test failed: {e}")
        print("  (This is expected if PostgreSQL is not running)")
        return False


def test_json_helpers():
    """Test JSON/JSONB helper methods."""
    print("\n=== Testing JSON Helpers ===")

    # Test JSON to JSONB conversion
    test_dict = {"key": "value", "number": 42}
    jsonb_str = PostgreSQLBase.json_to_jsonb(test_dict)
    assert jsonb_str == '{"key": "value", "number": 42}'
    print("✓ JSON to JSONB conversion working")

    # Test JSONB to dict conversion
    result = PostgreSQLBase.jsonb_to_dict(jsonb_str)
    assert result == test_dict
    print("✓ JSONB to dict conversion working")

    # Test None handling
    assert PostgreSQLBase.json_to_jsonb(None) is None
    assert PostgreSQLBase.jsonb_to_dict(None) is None
    print("✓ None handling working")

    return True


def check_dependencies():
    """Check if PostgreSQL dependencies are installed."""
    print("\n=== Checking Dependencies ===")

    try:
        import asyncpg
        print(f"✓ asyncpg installed: {asyncpg.__version__}")
    except ImportError:
        print("✗ asyncpg not installed")
        return False

    try:
        import psycopg
        print(f"✓ psycopg installed: {psycopg.__version__}")
    except ImportError:
        print("✗ psycopg not installed")
        return False

    try:
        import alembic
        print(f"✓ alembic installed: {alembic.__version__}")
    except ImportError:
        print("✗ alembic not installed")
        return False

    return True


def check_migration_files():
    """Check if migration files exist."""
    print("\n=== Checking Migration Files ===")

    migrations_dir = Path(__file__).parents[1] / "migrations"

    files_to_check = [
        "postgres/001_initial_schema.sql",
        "alembic/env.py",
        "alembic/script.py.mako",
        "alembic/versions/001_initial_schema.py",
        "README.md"
    ]

    all_exist = True
    for file_path in files_to_check:
        full_path = migrations_dir / file_path
        if full_path.exists():
            print(f"✓ {file_path} exists")
        else:
            print(f"✗ {file_path} missing")
            all_exist = False

    return all_exist


async def main():
    """Run all tests."""
    print("PostgreSQL Phase 1 Implementation Tests")
    print("=" * 50)

    # Check dependencies
    if not check_dependencies():
        print("\n⚠️  Missing dependencies. Run: uv sync")
        return

    # Check migration files
    if not check_migration_files():
        print("\n⚠️  Missing migration files")
        return

    # Test configuration
    config = test_configuration()

    # Test JSON helpers (no database needed)
    test_json_helpers()

    # Check if we should run database tests
    if not config.database.postgresql.password:
        print("\n⚠️  Skipping database tests - no POSTGRES_PASSWORD set")
        print("To run database tests:")
        print("  1. Ensure PostgreSQL is running")
        print("  2. Create database and user:")
        print("     CREATE DATABASE rag_lab_db;")
        print("     CREATE USER rag_lab_user WITH PASSWORD 'your_password';")  # pragma: allowlist secret
        print("     GRANT ALL PRIVILEGES ON DATABASE rag_lab_db TO rag_lab_user;")
        print("  3. Set environment variable:")
        print("     export POSTGRES_PASSWORD='your_password'")  # pragma: allowlist secret
        return

    # Test database connectivity
    print("\n🔌 Testing Database Connectivity...")
    sync_ok = test_postgres_base_sync(config)

    if sync_ok:
        async_ok = await test_postgres_base_async(config)
        schema_ok = test_schema_creation(config)

        print("\n" + "=" * 50)
        print("Test Summary:")
        print(f"  Configuration: ✓")
        print(f"  Dependencies: ✓")
        print(f"  Migration files: ✓")
        print(f"  JSON helpers: ✓")
        print(f"  Sync connection: {'✓' if sync_ok else '✗'}")
        print(f"  Async connection: {'✓' if async_ok else '✗'}")
        print(f"  Schema operations: {'✓' if schema_ok else '✗'}")
    else:
        print("\n⚠️  Database connection failed. Check PostgreSQL setup.")


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
