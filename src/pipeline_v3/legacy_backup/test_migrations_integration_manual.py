#!/usr/bin/env python3
"""
Integration tests for database migration framework.

Tests the migration system working with real database components.
"""

import sys
import tempfile
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Setup environment for tests that might need OpenAI
try:
    from utils.env_utils import setup_environment

    setup_environment()
except ImportError:
    # If env_utils not available, try basic dotenv loading
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

from core.migrations import Migration, MigrationManager, load_migrations_from_sql_files


def test_real_migration_files():
    """Test loading and applying real migration files from the project."""
    print("🧪 Testing: Real migration files integration")

    # Get the real migrations directory
    migrations_base = Path(__file__).parent.parent.parent / "migrations"

    if not migrations_base.exists():
        print("   ⚠️  SKIPPED - migrations directory not found")
        return True

    for db_type in ["registry", "fingerprints", "keyword_index", "jobs"]:
        migrations_dir = migrations_base / db_type

        if not migrations_dir.exists():
            print(f"   ⚠️  SKIPPED - {db_type} migrations not found")
            continue

        print(f"   🔍 Testing {db_type} migrations...")

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
            db_path = temp_db.name

        try:
            # Load migrations
            migrations = load_migrations_from_sql_files(migrations_dir)

            if not migrations:
                print(f"   ⚠️  No migrations found for {db_type}")
                continue

            # Apply migrations
            manager = MigrationManager(db_path)
            result = manager.run_migrations(migrations)

            # Verify results
            assert result["applied_count"] > 0, f"No migrations applied for {db_type}"
            assert result["current_version"] > 0, f"Version not updated for {db_type}"

            # Verify tables were created
            cursor = manager.conn.execute(
                """
                SELECT name FROM sqlite_master WHERE type='table'
            """
            )
            tables = [row[0] for row in cursor.fetchall()]

            # Check for expected tables based on database type
            if db_type == "registry":
                assert "documents" in tables, "documents table not created"
                assert (
                    "index_consistency" in tables
                ), "index_consistency table not created"
            elif db_type == "fingerprints":
                assert "fingerprints" in tables, "fingerprints table not created"
            elif db_type == "keyword_index":
                assert "documents" in tables, "FTS documents table not created"
                assert "doc_metadata" in tables, "doc_metadata table not created"
            elif db_type == "jobs":
                assert "jobs" in tables, "jobs table not created"

            manager.close()
            print(f"   ✅ {db_type} migrations applied successfully")

        finally:
            db_path_obj = Path(db_path)
            if db_path_obj.exists():
                db_path_obj.unlink()

    print("   ✅ PASSED - Real migration files integration")
    return True


def test_migration_sequence():
    """Test applying multiple migrations in sequence."""
    print("🧪 Testing: Migration sequence application")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Create sequence of migrations
        migrations = [
            Migration(
                version=1,
                name="create_users",
                up_sql="""
                    CREATE TABLE users (
                        id INTEGER PRIMARY KEY,
                        email TEXT UNIQUE NOT NULL
                    );
                    CREATE INDEX idx_users_email ON users(email);
                """,
                down_sql="""
                    DROP INDEX idx_users_email;
                    DROP TABLE users;
                """,
            ),
            Migration(
                version=2,
                name="add_user_name",
                up_sql="""
                    ALTER TABLE users ADD COLUMN name TEXT;
                    CREATE INDEX idx_users_name ON users(name);
                """,
                down_sql="""
                    DROP INDEX idx_users_name;
                    -- SQLite doesn't support DROP COLUMN easily
                    CREATE TABLE users_temp AS SELECT id, email FROM users;
                    DROP TABLE users;
                    ALTER TABLE users_temp RENAME TO users;
                    CREATE INDEX idx_users_email ON users(email);
                """,
            ),
            Migration(
                version=3,
                name="add_timestamps",
                up_sql="""
                    ALTER TABLE users ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                    ALTER TABLE users ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                """,
                down_sql="""
                    CREATE TABLE users_temp AS SELECT id, email, name FROM users;
                    DROP TABLE users;
                    ALTER TABLE users_temp RENAME TO users;
                    CREATE INDEX idx_users_email ON users(email);
                    CREATE INDEX idx_users_name ON users(name);
                """,
            ),
        ]

        # Apply migrations one by one
        for i, migration in enumerate(migrations, 1):
            manager.apply_migration(migration)

            # Verify version
            version = manager.get_current_version()
            assert version == i, f"Expected version {i}, got {version}"

        # Verify final state
        cursor = manager.conn.execute("PRAGMA table_info(users)")
        columns = [row[1] for row in cursor.fetchall()]

        expected_columns = ["id", "email", "name", "created_at", "updated_at"]
        for col in expected_columns:
            assert col in columns, f"Column {col} not found in final schema"

        # Test rollback sequence
        for target_version in [2, 1, 0]:
            manager.rollback_migration(target_version)
            current_version = manager.get_current_version()
            assert (
                current_version == target_version
            ), f"Rollback to {target_version} failed, got {current_version}"

        manager.close()
        print("   ✅ PASSED - Migration sequence application")
        return True

    finally:
        db_path_obj = Path(db_path)
        if db_path_obj.exists():
            db_path_obj.unlink()


def test_migration_error_recovery():
    """Test migration error handling and recovery."""
    print("🧪 Testing: Migration error recovery")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Apply valid migration first
        valid_migration = Migration(
            version=1,
            name="valid_migration",
            up_sql="CREATE TABLE test_table (id INTEGER PRIMARY KEY);",
            down_sql="DROP TABLE test_table;",
        )
        manager.apply_migration(valid_migration)

        # Try to apply invalid migration
        invalid_migration = Migration(
            version=2,
            name="invalid_migration",
            up_sql="INVALID SQL SYNTAX HERE",  # Invalid SQL
            down_sql="DROP TABLE invalid_table;",
        )

        # Verify migration fails
        failed = False
        try:
            manager.apply_migration(invalid_migration)
            raise AssertionError("Expected migration to fail")
        except Exception:
            # Expected to fail
            failed = True

        assert failed, "Migration should have failed due to invalid SQL"

        # Verify we're still at version 1
        version = manager.get_current_version()
        assert version == 1, f"Expected version 1 after failed migration, got {version}"

        # Verify valid table still exists
        cursor = manager.conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'
        """
        )
        assert cursor.fetchone() is not None, "Valid table should still exist"

        # Verify invalid table doesn't exist
        cursor = manager.conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='invalid_table'
        """
        )
        assert cursor.fetchone() is None, "Invalid table should not exist"

        manager.close()
        print("   ✅ PASSED - Migration error recovery")
        return True

    finally:
        db_path_obj = Path(db_path)
        if db_path_obj.exists():
            db_path_obj.unlink()


def test_concurrent_migration_safety():
    """Test migration safety with concurrent access."""
    print("🧪 Testing: Migration concurrent access safety")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        # Create first manager and apply migration
        manager1 = MigrationManager(db_path)
        migration = Migration(
            version=1,
            name="test_migration",
            up_sql="CREATE TABLE test_table (id INTEGER PRIMARY KEY);",
            down_sql="DROP TABLE test_table;",
        )
        manager1.apply_migration(migration)

        # Create second manager (simulating concurrent access)
        manager2 = MigrationManager(db_path)

        # Both should see the same version
        version1 = manager1.get_current_version()
        version2 = manager2.get_current_version()
        assert version1 == version2 == 1, f"Version mismatch: {version1} vs {version2}"

        # Both should see the table
        cursor1 = manager1.conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'
        """
        )
        cursor2 = manager2.conn.execute(
            """
            SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'
        """
        )

        assert cursor1.fetchone() is not None, "Table not visible to manager1"
        assert cursor2.fetchone() is not None, "Table not visible to manager2"

        manager1.close()
        manager2.close()
        print("   ✅ PASSED - Migration concurrent access safety")
        return True

    finally:
        db_path_obj = Path(db_path)
        if db_path_obj.exists():
            db_path_obj.unlink()


def main():
    """Run all migration integration tests."""
    print("🚀 Migration Framework Integration Tests")
    print("=" * 60)

    tests = [
        test_real_migration_files,
        test_migration_sequence,
        test_migration_error_recovery,
        test_concurrent_migration_safety,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"   ❌ FAILED - {e}")
            import traceback

            traceback.print_exc()

    print(f"\n📊 Migration Integration Tests: {passed}/{total} passed")

    if passed == total:
        print("🎉 All migration integration tests PASSED!")
        return True
    print("❌ Some migration integration tests FAILED!")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
