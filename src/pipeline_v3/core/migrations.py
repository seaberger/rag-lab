"""
Database Migration Framework for Pipeline v3

Provides version tracking and migration capabilities for all SQLite databases.
Supports forward migrations and rollback operations.
"""

import hashlib
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Represents a database migration."""

    version: int
    name: str
    up_sql: str
    down_sql: str | None = None
    checksum: str | None = None

    def calculate_checksum(self) -> str:
        """Calculate checksum for migration content."""
        content = f"{self.version}:{self.name}:{self.up_sql}:{self.down_sql or ''}"
        return hashlib.sha256(content.encode()).hexdigest()


class MigrationManager:
    """Manages database migrations with version tracking and rollback support."""

    def __init__(self, db_path: str, migrations_dir: Path | None = None):
        """
        Initialize migration manager.

        Args:
            db_path: Path to the SQLite database
            migrations_dir: Directory containing migration files
        """
        self.db_path = db_path
        self.migrations_dir = migrations_dir
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

        # Create migrations tracking table
        self._create_migration_table()

    def _create_migration_table(self):
        """Create schema_migrations table if it doesn't exist."""
        try:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    applied_at REAL NOT NULL,
                    checksum TEXT NOT NULL,
                    execution_time REAL,
                    rollback_sql TEXT
                )
            """)

            # Create index for faster lookups
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_migrations_applied_at
                ON schema_migrations(applied_at)
            """)

            self.conn.commit()
            logger.info("Migration tracking table ready")

        except Exception as e:
            logger.exception(f"Failed to create migration table: {e}")
            raise

    def get_current_version(self) -> int:
        """Get current schema version."""
        try:
            cursor = self.conn.execute("""
                SELECT MAX(version) as version FROM schema_migrations
            """)
            result = cursor.fetchone()
            return result["version"] if result["version"] is not None else 0

        except sqlite3.OperationalError:
            # Table doesn't exist yet
            return 0

    def get_applied_migrations(self) -> list[dict[str, Any]]:
        """Get list of applied migrations."""
        cursor = self.conn.execute("""
            SELECT version, name, applied_at, checksum, execution_time
            FROM schema_migrations
            ORDER BY version
        """)
        return [dict(row) for row in cursor.fetchall()]

    def get_pending_migrations(self, migrations: list[Migration]) -> list[Migration]:
        """Get migrations that haven't been applied yet."""
        current_version = self.get_current_version()
        return [m for m in migrations if m.version > current_version]

    def apply_migration(self, migration: Migration) -> float:
        """
        Apply a single migration.

        Returns:
            Execution time in seconds
        """
        start_time = time.time()

        # Calculate checksum if not provided
        if not migration.checksum:
            migration.checksum = migration.calculate_checksum()

        try:
            # Begin transaction
            self.conn.execute("BEGIN EXCLUSIVE")

            # Execute migration SQL
            for statement in migration.up_sql.strip().split(";"):
                statement = statement.strip()
                if statement:
                    self.conn.execute(statement)

            # Record migration
            execution_time = time.time() - start_time
            self.conn.execute(
                """
                INSERT INTO schema_migrations
                (version, name, applied_at, checksum, execution_time, rollback_sql)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    migration.version,
                    migration.name,
                    time.time(),
                    migration.checksum,
                    execution_time,
                    migration.down_sql,
                ),
            )

            # Commit transaction
            self.conn.commit()

            logger.info(
                f"Applied migration {migration.version}: {migration.name} in {execution_time:.3f}s"
            )

            return execution_time

        except Exception as e:
            # Rollback on error
            self.conn.rollback()
            logger.exception(f"Failed to apply migration {migration.version}: {e}")
            raise

    def rollback_migration(self, target_version: int) -> list[int]:
        """
        Rollback to a specific version.

        Args:
            target_version: Version to rollback to (exclusive)

        Returns:
            List of rolled back versions
        """
        current_version = self.get_current_version()

        if target_version >= current_version:
            logger.warning(f"Target version {target_version} >= current version {current_version}")
            return []

        rolled_back = []

        try:
            # Get migrations to rollback in reverse order
            cursor = self.conn.execute(
                """
                SELECT version, name, rollback_sql
                FROM schema_migrations
                WHERE version > ?
                ORDER BY version DESC
            """,
                (target_version,),
            )

            migrations_to_rollback = cursor.fetchall()

            for migration in migrations_to_rollback:
                if not migration["rollback_sql"]:
                    raise ValueError(f"Migration {migration['version']} has no rollback SQL")

                # Begin transaction for each rollback
                self.conn.execute("BEGIN EXCLUSIVE")

                try:
                    # Execute rollback SQL
                    for statement in migration["rollback_sql"].strip().split(";"):
                        statement = statement.strip()
                        if statement:
                            self.conn.execute(statement)

                    # Remove migration record
                    self.conn.execute(
                        """
                        DELETE FROM schema_migrations WHERE version = ?
                    """,
                        (migration["version"],),
                    )

                    self.conn.commit()
                    rolled_back.append(migration["version"])

                    logger.info(
                        f"Rolled back migration {migration['version']}: {migration['name']}"
                    )

                except Exception as e:
                    self.conn.rollback()
                    logger.exception(f"Failed to rollback migration {migration['version']}: {e}")
                    raise

            return rolled_back

        except Exception as e:
            logger.exception(f"Rollback failed: {e}")
            raise

    def run_migrations(self, migrations: list[Migration], dry_run: bool = False) -> dict[str, Any]:
        """
        Run all pending migrations.

        Args:
            migrations: List of migrations to apply
            dry_run: If True, only show what would be done

        Returns:
            Summary of migration results
        """
        pending = self.get_pending_migrations(migrations)

        if not pending:
            logger.info("No pending migrations")
            return {
                "current_version": self.get_current_version(),
                "pending_count": 0,
                "applied_count": 0,
                "dry_run": dry_run,
            }

        logger.info(f"Found {len(pending)} pending migrations")

        if dry_run:
            for migration in pending:
                logger.info(f"Would apply: {migration.version} - {migration.name}")
            return {
                "current_version": self.get_current_version(),
                "pending_count": len(pending),
                "applied_count": 0,
                "dry_run": True,
                "pending_migrations": [{"version": m.version, "name": m.name} for m in pending],
            }

        # Apply migrations
        applied = []
        total_time = 0.0

        for migration in pending:
            try:
                execution_time = self.apply_migration(migration)
                applied.append(migration.version)
                total_time += execution_time

            except Exception as e:
                logger.exception(f"Migration failed at version {migration.version}: {e}")
                return {
                    "current_version": self.get_current_version(),
                    "pending_count": len(pending),
                    "applied_count": len(applied),
                    "failed_at": migration.version,
                    "error": str(e),
                    "dry_run": False,
                }

        return {
            "current_version": self.get_current_version(),
            "pending_count": len(pending),
            "applied_count": len(applied),
            "total_time": total_time,
            "dry_run": False,
        }

    def verify_migrations(self, migrations: list[Migration]) -> dict[str, Any]:
        """Verify migration integrity."""
        issues = []
        applied = {m["version"]: m for m in self.get_applied_migrations()}

        for migration in migrations:
            if migration.version in applied:
                # Check checksum
                expected = migration.calculate_checksum()
                actual = applied[migration.version]["checksum"]

                if expected != actual:
                    issues.append(
                        {
                            "version": migration.version,
                            "issue": "checksum_mismatch",
                            "expected": expected,
                            "actual": actual,
                        }
                    )

        return {"valid": len(issues) == 0, "issues": issues}

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def load_migrations_from_sql_files(directory: Path) -> list[Migration]:
    """
    Load migrations from SQL files in a directory.

    Expected file format: XXX_name.sql or XXX_name.up.sql / XXX_name.down.sql
    """
    migrations = []
    migration_files = {}

    # Group files by version
    for file_path in sorted(directory.glob("*.sql")):
        parts = file_path.stem.split("_", 1)
        if len(parts) < 2 or not parts[0].isdigit():
            logger.warning(f"Skipping invalid migration file: {file_path}")
            continue

        version = int(parts[0])
        name = parts[1]

        if file_path.name.endswith(".up.sql"):
            key = (version, name.replace(".up", ""))
            if key not in migration_files:
                migration_files[key] = {}
            migration_files[key]["up"] = file_path

        elif file_path.name.endswith(".down.sql"):
            key = (version, name.replace(".down", ""))
            if key not in migration_files:
                migration_files[key] = {}
            migration_files[key]["down"] = file_path

        else:
            # Single file contains up migration only
            key = (version, name)
            if key not in migration_files:
                migration_files[key] = {}
            migration_files[key]["up"] = file_path

    # Create Migration objects
    for (version, name), files in sorted(migration_files.items()):
        if "up" not in files:
            logger.warning(f"Missing up migration for version {version}")
            continue

        up_sql = files["up"].read_text()
        down_sql = files["down"].read_text() if "down" in files else None

        migration = Migration(version=version, name=name, up_sql=up_sql, down_sql=down_sql)
        migrations.append(migration)

    return migrations
