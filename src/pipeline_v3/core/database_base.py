"""
Base class for database managers with migration support.

Provides common functionality for SQLite-based storage components
with automatic schema migration capabilities.
"""

import logging
import sqlite3
from pathlib import Path

from .migrations import MigrationManager, load_migrations_from_sql_files

logger = logging.getLogger(__name__)


class DatabaseBase:
    """Base class for database managers with migration support."""

    def __init__(self, db_path: str, migrations_subdir: str, db_name: str = "Database"):
        """
        Initialize database with migration support.

        Args:
            db_path: Path to the SQLite database file
            migrations_subdir: Subdirectory name under migrations/ for this database
            db_name: Human-readable name for logging
        """
        self.db_path = Path(db_path)
        self.db_name = db_name
        self.migrations_subdir = migrations_subdir

        # Ensure directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Run migrations before initializing connection
        self._run_migrations()

        # Initialize connection with row factory
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

        logger.info(f"{self.db_name} initialized at: {self.db_path}")

    def _run_migrations(self):
        """Run database migrations."""
        # Determine migrations directory
        migrations_base = Path(__file__).parent.parent / "migrations"
        migrations_dir = migrations_base / self.migrations_subdir

        if not migrations_dir.exists():
            logger.warning(
                f"No migrations directory found for {self.db_name} at {migrations_dir}. "
                "Creating tables directly (legacy mode)."
            )
            return

        # Initialize migration manager
        migration_manager = MigrationManager(str(self.db_path))

        try:
            # Load migrations from directory
            migrations = load_migrations_from_sql_files(migrations_dir)

            if not migrations:
                logger.info(f"No migrations found for {self.db_name}")
                return

            # Check current version
            current_version = migration_manager.get_current_version()
            logger.info(f"{self.db_name} current schema version: {current_version}")

            # Run pending migrations
            result = migration_manager.run_migrations(migrations)

            if result["applied_count"] > 0:
                logger.info(
                    f"Applied {result['applied_count']} migrations to {self.db_name}. "
                    f"New version: {result['current_version']}"
                )
            else:
                logger.info(f"{self.db_name} schema is up to date")

        except Exception as e:
            logger.exception(f"Migration failed for {self.db_name}: {e}")
            raise

        finally:
            migration_manager.close()

    def get_schema_version(self) -> int:
        """Get current schema version."""
        migration_manager = MigrationManager(str(self.db_path))
        try:
            return migration_manager.get_current_version()
        finally:
            migration_manager.close()

    def verify_schema(self) -> bool:
        """Verify schema integrity."""
        migrations_dir = Path(__file__).parent.parent / "migrations" / self.migrations_subdir

        if not migrations_dir.exists():
            return True  # No migrations to verify

        migration_manager = MigrationManager(str(self.db_path))
        try:
            migrations = load_migrations_from_sql_files(migrations_dir)
            result = migration_manager.verify_migrations(migrations)

            if not result["valid"]:
                logger.error(f"Schema verification failed for {self.db_name}: {result['issues']}")

            return result["valid"]

        finally:
            migration_manager.close()

    def close(self):
        """Close database connection."""
        if hasattr(self, "conn") and self.conn:
            self.conn.close()
            logger.info(f"{self.db_name} connection closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
