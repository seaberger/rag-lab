#!/usr/bin/env python3
"""
Test script to demonstrate database migration functionality.
"""

import tempfile
import shutil
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.migrations import MigrationManager, Migration
from core.database_base import DatabaseBase
from utils.common_utils import logger


def test_migration_system():
    """Test the migration system with a temporary database."""
    
    print("🧪 Testing Database Migration System\n")
    
    # Create temporary directory for test
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "test_registry.db"
        
        print("1️⃣ Testing basic migration functionality...")
        
        # Create migration manager
        manager = MigrationManager(str(db_path))
        
        # Check initial version
        version = manager.get_current_version()
        print(f"   Initial version: {version}")
        assert version == 0, "Initial version should be 0"
        
        # Create test migrations
        migrations = [
            Migration(
                version=1,
                name="initial_schema",
                up_sql="""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        email TEXT UNIQUE
                    );
                    CREATE INDEX idx_users_email ON users(email);
                """,
                down_sql="""
                    DROP INDEX idx_users_email;
                    DROP TABLE users;
                """
            ),
            Migration(
                version=2,
                name="add_created_at",
                up_sql="""
                    ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                """,
                down_sql="""
                    -- SQLite doesn't support DROP COLUMN, would need table recreation
                    SELECT 1;
                """
            )
        ]
        
        print("\n2️⃣ Running migrations...")
        
        # Run migrations
        result = manager.run_migrations(migrations)
        print(f"   Applied {result['applied_count']} migrations")
        print(f"   Current version: {result['current_version']}")
        assert result['current_version'] == 2, "Should be at version 2"
        
        # Verify migrations were applied
        applied = manager.get_applied_migrations()
        print(f"\n3️⃣ Applied migrations:")
        for m in applied:
            print(f"   v{m['version']}: {m['name']} (took {m['execution_time']:.3f}s)")
        
        # Test dry run
        print("\n4️⃣ Testing dry run (no new migrations)...")
        result = manager.run_migrations(migrations, dry_run=True)
        print(f"   Pending migrations: {result['pending_count']}")
        assert result['pending_count'] == 0, "Should have no pending migrations"
        
        # Test rollback
        print("\n5️⃣ Testing rollback to version 1...")
        rolled_back = manager.rollback_migration(1)
        print(f"   Rolled back versions: {rolled_back}")
        
        current = manager.get_current_version()
        print(f"   Current version after rollback: {current}")
        assert current == 1, "Should be at version 1 after rollback"
        
        # Close manager
        manager.close()
        
        print("\n✅ All migration tests passed!")


def test_real_migrations():
    """Test loading real migration files."""
    
    print("\n\n🔍 Testing real migration files...")
    
    migrations_base = Path(__file__).parent / "migrations"
    
    for db_type in ["registry", "fingerprints", "keyword_index", "jobs"]:
        migrations_dir = migrations_base / db_type
        
        if migrations_dir.exists():
            print(f"\n📁 {db_type} migrations:")
            
            sql_files = list(migrations_dir.glob("*.sql"))
            for sql_file in sorted(sql_files):
                print(f"   - {sql_file.name}")
                
                # Read first few lines
                lines = sql_file.read_text().split('\n')[:3]
                for line in lines:
                    if line.strip() and line.strip().startswith('--'):
                        print(f"     {line.strip()}")
        else:
            print(f"\n⚠️  {db_type} migrations directory not found")
    
    print("\n✅ Migration files review complete!")


if __name__ == "__main__":
    test_migration_system()
    test_real_migrations()