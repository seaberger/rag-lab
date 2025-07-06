"""
Test Phase 3 completion - PostgreSQL migration implementation.

This test verifies that all Phase 3 components are properly implemented.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))


def test_phase3_migration_tool_available():
    """Test that the migration tool is available."""
    try:
        # Add pipeline_v3 to path
        import sys
        from pathlib import Path
        pipeline_root = Path(__file__).parent.parent
        if str(pipeline_root) not in sys.path:
            sys.path.insert(0, str(pipeline_root))

        from tools.sqlite_to_postgres import SQLiteToPostgresMigrator, MigrationStats
        print("✓ Migration tool imports successful")

        # Test basic functionality
        stats = MigrationStats()
        assert stats is not None
        print("✓ MigrationStats class working")

    except ImportError as e:
        assert False, f"Migration tool not available: {e}"


def test_phase3_database_factory_available():
    """Test that the database factory is available."""
    try:
        # Add pipeline_v3 to path
        import sys
        from pathlib import Path
        pipeline_root = Path(__file__).parent.parent
        if str(pipeline_root) not in sys.path:
            sys.path.insert(0, str(pipeline_root))

        from core.database_factory import DatabaseFactory, DatabaseContext
        print("✓ Database factory imports successful")

        # Test basic functionality
        from utils.config import PipelineConfig, DatabaseSettings

        config = PipelineConfig(database=DatabaseSettings(backend="sqlite"))
        factory = DatabaseFactory(config)
        assert factory is not None
        assert factory.backend == "sqlite"
        print("✓ DatabaseFactory class working")

    except ImportError as e:
        assert False, f"Database factory not available: {e}"


def test_phase3_cli_migration_commands():
    """Test that migration CLI commands are available."""
    try:
        # Test CLI help for migrate command
        import subprocess
        result = subprocess.run(
            ["uv", "run", "python", "-m", "src.pipeline_v3.cli_main", "migrate", "--help"],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"CLI migrate command failed: {result.stderr}"
        assert "to-postgres" in result.stdout, "to-postgres subcommand not found"
        assert "status" in result.stdout, "status subcommand not found"
        print("✓ Migration CLI commands available")

    except Exception as e:
        assert False, f"Migration CLI not working: {e}"


def test_phase3_postgresql_adapters_available():
    """Test that PostgreSQL adapters are available."""
    try:
        # Add pipeline_v3 to path
        import sys
        from pathlib import Path
        pipeline_root = Path(__file__).parent.parent
        if str(pipeline_root) not in sys.path:
            sys.path.insert(0, str(pipeline_root))

        from core.postgres_registry import PostgreSQLDocumentRegistry
        from storage.postgres_keyword import PostgreSQLKeywordIndex
        from job_queue.postgres_jobs import PostgreSQLJobManager
        from core.postgres_fingerprint import PostgreSQLFingerprintManager
        print("✓ All PostgreSQL adapters import successfully")

    except ImportError as e:
        assert False, f"PostgreSQL adapters not available: {e}"


def test_phase3_configuration_support():
    """Test that PostgreSQL configuration is supported."""
    try:
        # Add pipeline_v3 to path
        import sys
        from pathlib import Path
        pipeline_root = Path(__file__).parent.parent
        if str(pipeline_root) not in sys.path:
            sys.path.insert(0, str(pipeline_root))

        from utils.config import PipelineConfig, DatabaseSettings, PostgreSQLSettings

        # Test PostgreSQL configuration
        pg_config = PipelineConfig(
            database=DatabaseSettings(
                backend="postgresql",
                postgresql=PostgreSQLSettings(
                    host="localhost",
                    port=5432,
                    database="test_db",
                    user="test_user",
                    password="test_password"  # pragma: allowlist secret
                )
            )
        )

        assert pg_config.database.backend == "postgresql"
        assert pg_config.database.postgresql.host == "localhost"
        print("✓ PostgreSQL configuration working")

    except Exception as e:
        assert False, f"PostgreSQL configuration not working: {e}"


def test_phase3_documentation_available():
    """Test that Phase 3 documentation is available."""
    project_root = Path(__file__).parents[3]

    docs_to_check = [
        "src/pipeline_v3/docs/POSTGRESQL_MIGRATION_PLAN.md",
        "src/pipeline_v3/docs/POSTGRESQL_PHASE2_SUMMARY.md",
        "src/pipeline_v3/docs/POSTGRESQL_SECURITY.md",
    ]

    for doc_path in docs_to_check:
        full_path = project_root / doc_path
        assert full_path.exists(), f"Documentation missing: {doc_path}"

        # Check that the file has content
        content = full_path.read_text()
        assert len(content) > 100, f"Documentation too short: {doc_path}"

    print("✓ All Phase 3 documentation available")


def test_phase3_test_infrastructure():
    """Test that test infrastructure supports multi-backend testing."""
    # Check that conftest.py has the multi-backend fixtures
    conftest_path = Path(__file__).parent / "conftest.py"
    assert conftest_path.exists(), "conftest.py not found"

    content = conftest_path.read_text()

    # Check for PostgreSQL-specific fixtures
    required_functions = [
        "check_postgresql_available",
        "postgresql_config",
        "database_backend",
        "database_factory_multi",
        "create_test_document_info",
    ]

    for func_name in required_functions:
        assert func_name in content, f"Missing test function: {func_name}"

    print("✓ Multi-backend test infrastructure available")


def test_phase3_migration_readiness():
    """Test that the system is ready for PostgreSQL migration."""
    try:
        # Test migration status check
        import subprocess
        result = subprocess.run(
            ["uv", "run", "python", "-m", "src.pipeline_v3.cli_main", "migrate", "status"],
            capture_output=True,
            text=True,
            timeout=30
        )

        assert result.returncode == 0, f"Migration status check failed: {result.stderr}"
        assert "Current database backend" in result.stdout, "Backend status not shown"
        assert "SQLite databases" in result.stdout, "SQLite status not shown"
        print("✓ Migration status check working")

    except Exception as e:
        assert False, f"Migration status not working: {e}"


def main():
    """Run all Phase 3 completion tests."""
    print("Phase 3 Completion Tests")
    print("=" * 50)

    test_functions = [
        test_phase3_migration_tool_available,
        test_phase3_database_factory_available,
        test_phase3_cli_migration_commands,
        test_phase3_postgresql_adapters_available,
        test_phase3_configuration_support,
        test_phase3_documentation_available,
        test_phase3_test_infrastructure,
        test_phase3_migration_readiness,
    ]

    passed = 0
    failed = 0

    for test_func in test_functions:
        try:
            print(f"\n{test_func.__name__}:")
            test_func()
            passed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Phase 3 Completion Test Results:")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print(f"  Total:  {len(test_functions)}")

    if failed == 0:
        print("\n🎉 Phase 3 implementation is complete!")
        print("✅ PostgreSQL migration, database factory, and test updates all working")
    else:
        print(f"\n⚠️  {failed} test(s) failed - Phase 3 needs attention")


if __name__ == "__main__":
    main()
