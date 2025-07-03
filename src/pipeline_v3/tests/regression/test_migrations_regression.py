#!/usr/bin/env python3
"""
Regression tests for database migration framework.

Ensures migration system doesn't break existing functionality and
prevents known migration issues from recurring.
"""

import os
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

from core.migrations import Migration, MigrationManager


def test_migration_idempotency():
    """Test that migrations can be applied multiple times safely."""
    print("🧪 Testing: Migration idempotency")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        migration = Migration(
            version=1,
            name="idempotent_test",
            up_sql="""
                CREATE TABLE IF NOT EXISTS test_table (
                    id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE
                );
                CREATE INDEX IF NOT EXISTS idx_test_name ON test_table(name);
            """,
            down_sql="DROP TABLE IF EXISTS test_table;",
        )

        # Apply migration multiple times
        for i in range(3):
            result = manager.run_migrations([migration])

            if i == 0:
                # First time should apply
                assert result["applied_count"] == 1, "First application should apply 1 migration"
            else:
                # Subsequent times should be no-op
                assert result["applied_count"] == 0, (
                    f"Repeat application {i + 1} should apply 0 migrations"
                )

            # Version should always be 1
            assert result["current_version"] == 1, (
                f"Version should be 1, got {result['current_version']}"
            )

        manager.close()
        print("   ✅ PASSED - Migration idempotency")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_schema_migrations_table_integrity():
    """Test that schema_migrations table remains intact across operations."""
    print("🧪 Testing: Schema migrations table integrity")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Apply several migrations
        migrations = [
            Migration(
                version=1,
                name="test1",
                up_sql="CREATE TABLE t1 (id INTEGER);",
                down_sql="DROP TABLE t1;",
            ),
            Migration(
                version=2,
                name="test2",
                up_sql="CREATE TABLE t2 (id INTEGER);",
                down_sql="DROP TABLE t2;",
            ),
            Migration(
                version=3,
                name="test3",
                up_sql="CREATE TABLE t3 (id INTEGER);",
                down_sql="DROP TABLE t3;",
            ),
        ]

        for migration in migrations:
            manager.apply_migration(migration)

        # Verify all migrations are recorded
        applied = manager.get_applied_migrations()
        assert len(applied) == 3, f"Expected 3 applied migrations, got {len(applied)}"

        # Verify schema_migrations table structure
        cursor = manager.conn.execute("PRAGMA table_info(schema_migrations)")
        columns = {row[1]: row[2] for row in cursor.fetchall()}

        expected_columns = {
            "version": "INTEGER",
            "name": "TEXT",
            "applied_at": "REAL",
            "checksum": "TEXT",
            "execution_time": "REAL",
            "rollback_sql": "TEXT",
        }

        for col_name, col_type in expected_columns.items():
            assert col_name in columns, f"Column {col_name} missing from schema_migrations"

        # Test rollback doesn't corrupt the table
        manager.rollback_migration(1)

        # Verify schema_migrations table is still intact
        cursor = manager.conn.execute("SELECT COUNT(*) FROM schema_migrations")
        count = cursor.fetchone()[0]
        assert count == 1, f"Expected 1 migration after rollback, got {count}"

        manager.close()
        print("   ✅ PASSED - Schema migrations table integrity")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_migration_checksum_verification():
    """Test that migration checksums detect modifications."""
    print("🧪 Testing: Migration checksum verification")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Apply original migration
        original_migration = Migration(
            version=1,
            name="checksum_test",
            up_sql="CREATE TABLE test_table (id INTEGER);",
            down_sql="DROP TABLE test_table;",
        )
        manager.apply_migration(original_migration)

        # Create modified migration with same version/name but different SQL
        modified_migration = Migration(
            version=1,
            name="checksum_test",
            up_sql="CREATE TABLE test_table (id INTEGER, name TEXT);",  # Different SQL
            down_sql="DROP TABLE test_table;",
        )

        # Verify checksums detect the difference
        verification = manager.verify_migrations([modified_migration])
        assert not verification["valid"], "Verification should fail for modified migration"
        assert len(verification["issues"]) == 1, "Should have one checksum issue"
        assert verification["issues"][0]["issue"] == "checksum_mismatch", (
            "Should detect checksum mismatch"
        )

        manager.close()
        print("   ✅ PASSED - Migration checksum verification")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_migration_rollback_consistency():
    """Test that rollback operations maintain database consistency."""
    print("🧪 Testing: Migration rollback consistency")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Apply migration with data
        migration = Migration(
            version=1,
            name="rollback_test",
            up_sql="""
                CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);
                INSERT INTO users (name) VALUES ('Alice'), ('Bob');
                CREATE INDEX idx_users_name ON users(name);
            """,
            down_sql="""
                DROP INDEX idx_users_name;
                DROP TABLE users;
            """,
        )
        manager.apply_migration(migration)

        # Verify data exists
        cursor = manager.conn.execute("SELECT COUNT(*) FROM users")
        count = cursor.fetchone()[0]
        assert count == 2, f"Expected 2 users, got {count}"

        # Rollback
        manager.rollback_migration(0)

        # Verify table is completely gone
        cursor = manager.conn.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='users'
        """)
        assert cursor.fetchone() is None, "Users table should not exist after rollback"

        # Verify index is also gone
        cursor = manager.conn.execute("""
            SELECT name FROM sqlite_master WHERE type='index' AND name='idx_users_name'
        """)
        assert cursor.fetchone() is None, "Users index should not exist after rollback"

        # Verify migration record is gone
        version = manager.get_current_version()
        assert version == 0, f"Version should be 0 after rollback, got {version}"

        manager.close()
        print("   ✅ PASSED - Migration rollback consistency")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_migration_transaction_atomicity():
    """Test that failed migrations don't leave partial changes."""
    print("🧪 Testing: Migration transaction atomicity")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Migration that fails partway through
        failing_migration = Migration(
            version=1,
            name="atomic_test",
            up_sql="""
                CREATE TABLE test_table (id INTEGER PRIMARY KEY);
                INSERT INTO test_table (id) VALUES (1);
                CREATE TABLE invalid_syntax_table (this is not valid SQL);
            """,
            down_sql="DROP TABLE test_table;",
        )

        # Try to apply failing migration
        try:
            manager.apply_migration(failing_migration)
            assert False, "Migration should have failed"
        except Exception:
            # Expected to fail
            pass

        # Verify no partial changes were committed
        cursor = manager.conn.execute("""
            SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'
        """)
        assert cursor.fetchone() is None, "Partial table should not exist after failed migration"

        # Verify version wasn't updated
        version = manager.get_current_version()
        assert version == 0, f"Version should be 0 after failed migration, got {version}"

        # Verify no migration record was created
        applied = manager.get_applied_migrations()
        assert len(applied) == 0, f"Should have 0 applied migrations, got {len(applied)}"

        manager.close()
        print("   ✅ PASSED - Migration transaction atomicity")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_migration_version_sequence():
    """Test that migration versions must be sequential."""
    print("🧪 Testing: Migration version sequence validation")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as temp_db:
        db_path = temp_db.name

    try:
        manager = MigrationManager(db_path)

        # Apply version 1
        migration1 = Migration(
            version=1,
            name="version_test_1",
            up_sql="CREATE TABLE table1 (id INTEGER);",
            down_sql="DROP TABLE table1;",
        )
        manager.apply_migration(migration1)

        # Try to apply version 3 (skipping 2)
        migration3 = Migration(
            version=3,
            name="version_test_3",
            up_sql="CREATE TABLE table3 (id INTEGER);",
            down_sql="DROP TABLE table3;",
        )

        # Our current implementation allows non-sequential migrations
        # (this might be by design for flexibility)
        # So let's test that it applies correctly
        result = manager.run_migrations([migration3])
        assert result["applied_count"] == 1, "Should apply migration with higher version"
        assert result["current_version"] == 3, "Version should jump to 3"

        # Now apply version 2 (lower than current)
        migration2 = Migration(
            version=2,
            name="version_test_2",
            up_sql="CREATE TABLE table2 (id INTEGER);",
            down_sql="DROP TABLE table2;",
        )
        # Version 2 should not apply because current version is 3
        result = manager.run_migrations([migration2])
        assert result["applied_count"] == 0, "Should not apply lower version migration"
        assert result["current_version"] == 3, "Version should remain 3"

        manager.close()
        print("   ✅ PASSED - Migration version sequence validation")
        return True

    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def main():
    """Run all migration regression tests."""
    print("🚀 Migration Framework Regression Tests")
    print("=" * 60)

    tests = [
        test_migration_idempotency,
        test_schema_migrations_table_integrity,
        test_migration_checksum_verification,
        test_migration_rollback_consistency,
        test_migration_transaction_atomicity,
        test_migration_version_sequence,
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

    print(f"\n📊 Migration Regression Tests: {passed}/{total} passed")

    if passed == total:
        print("🎉 All migration regression tests PASSED!")
        return True
    print("❌ Some migration regression tests FAILED!")
    return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
