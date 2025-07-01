# Database Migration System

This directory contains database migrations for all SQLite databases in Pipeline v3.

## Overview

The migration system provides:
- **Version tracking** - Know exactly what schema version each database is at
- **Safe upgrades** - Apply schema changes without data loss
- **Rollback capability** - Undo migrations if issues arise
- **Consistency** - Ensure all deployments have the same schema

## Directory Structure

```
migrations/
├── registry/          # Document registry migrations
├── fingerprints/      # Fingerprint tracking migrations
├── keyword_index/     # Keyword search index migrations
└── jobs/             # Job queue migrations
```

## Migration File Naming

Migrations follow this naming convention:
- Single file: `XXX_migration_name.sql` (contains only UP migration)
- Split files: `XXX_migration_name.up.sql` and `XXX_migration_name.down.sql`

Where `XXX` is a 3-digit version number (e.g., `001`, `002`, etc.)

## Creating New Migrations

### 1. Determine the next version number
Look at existing migrations in the target directory and increment.

### 2. Create migration file(s)

**For simple additions (no rollback needed):**
```sql
-- migrations/registry/003_add_processing_stats.sql
-- Migration: 003_add_processing_stats
-- Description: Add columns for processing statistics

ALTER TABLE documents ADD COLUMN processing_time REAL;
ALTER TABLE documents ADD COLUMN processing_attempts INTEGER DEFAULT 0;
```

**For complex changes (with rollback):**
```sql
-- migrations/registry/004_add_indexes.up.sql
CREATE INDEX idx_documents_processing_time ON documents(processing_time);
CREATE INDEX idx_documents_attempts ON documents(processing_attempts);

-- migrations/registry/004_add_indexes.down.sql
DROP INDEX idx_documents_processing_time;
DROP INDEX idx_documents_attempts;
```

### 3. Test the migration
```python
from core.migrations import MigrationManager

manager = MigrationManager("test.db")
# ... load and apply migrations
```

## Migration Guidelines

### DO:
- Keep migrations small and focused
- Always test migrations on a copy of production data
- Include descriptive comments
- Consider rollback scenarios
- Use transactions (automatic in our system)

### DON'T:
- Modify existing migration files after deployment
- Skip version numbers
- Include data modifications in schema migrations
- Use database-specific features not supported by SQLite

## SQLite Limitations

Be aware of SQLite limitations:
- No `DROP COLUMN` support (requires table recreation)
- Limited `ALTER TABLE` capabilities
- No stored procedures or complex constraints

For complex schema changes, use the table recreation pattern:
```sql
-- Create new table with desired schema
CREATE TABLE documents_new AS SELECT ... FROM documents;
-- Drop old table
DROP TABLE documents;
-- Rename new table
ALTER TABLE documents_new RENAME TO documents;
-- Recreate indexes
```

## Running Migrations

Migrations are automatically applied when databases are initialized:

```python
from core.registry_migrated import DocumentRegistry

# Migrations run automatically on init
registry = DocumentRegistry()

# Check current version
version = registry.get_schema_version()
```

## Manual Migration Management

For manual control:

```python
from core.migrations import MigrationManager, load_migrations_from_sql_files

# Initialize manager
manager = MigrationManager("path/to/database.db")

# Load migrations from directory
migrations = load_migrations_from_sql_files(Path("migrations/registry"))

# Check pending
pending = manager.get_pending_migrations(migrations)

# Run migrations
result = manager.run_migrations(migrations, dry_run=True)  # Test first
result = manager.run_migrations(migrations)  # Actually apply

# Rollback if needed
manager.rollback_migration(target_version=2)
```

## Troubleshooting

### Migration Failed
1. Check the error message in logs
2. Verify SQL syntax is valid for SQLite
3. Ensure no conflicting schema exists
4. Test on a copy of the database first

### Inconsistent State
1. Check current version: `SELECT MAX(version) FROM schema_migrations`
2. Review applied migrations: `SELECT * FROM schema_migrations`
3. Manually fix if needed, then update version tracking

### Performance Issues
1. Migrations run in transactions - large operations may lock database
2. Consider running during maintenance windows
3. Add indexes in separate migrations for better control

## Best Practices

1. **Always backup** before running migrations in production
2. **Test thoroughly** on development data first
3. **Document changes** in migration comments
4. **Keep migrations idempotent** where possible
5. **Version control** all migration files
6. **Monitor execution time** for large migrations
7. **Plan rollback strategy** before applying