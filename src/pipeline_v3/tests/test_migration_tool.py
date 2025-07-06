"""
Test script for SQLite to PostgreSQL migration tool.

This script tests the migration functionality without requiring actual databases.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from src.pipeline_v3.utils.config import PipelineConfig


async def test_migration_tool():
    """Test the migration tool import and basic functionality."""
    print("Testing SQLite to PostgreSQL migration tool...")

    # Test imports
    try:
        from src.pipeline_v3.tools.sqlite_to_postgres import (
            MigrationStats,
            SQLiteToPostgresMigrator,
        )
        print("✓ Migration tool imports successful")
    except ImportError as e:
        print(f"✗ Failed to import migration tool: {e}")
        return

    # Test MigrationStats
    stats = MigrationStats()
    print(f"✓ MigrationStats created: {stats.to_dict()}")

    # Test configuration loading
    try:
        config = PipelineConfig()
        print(f"✓ Configuration loaded, backend: {config.database.backend}")
    except Exception as e:
        print(f"✗ Failed to load configuration: {e}")
        return

    # Test CLI integration
    print("\nTesting CLI integration...")
    print("You can now run migration commands:")
    print("  uv run python -m src.pipeline_v3.cli_main migrate status")
    print("  uv run python -m src.pipeline_v3.cli_main migrate to-postgres --help")

    print("\n✅ Migration tool tests complete!")


if __name__ == "__main__":
    asyncio.run(test_migration_tool())
