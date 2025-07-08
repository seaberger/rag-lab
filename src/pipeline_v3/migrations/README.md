# PostgreSQL Migrations for Pipeline v3

This directory contains database migrations for the PostgreSQL backend of Pipeline v3.

## Directory Structure

```
migrations/
├── postgres/           # Raw SQL migration files
│   └── 001_initial_schema.sql
├── alembic/           # Alembic migration framework
│   ├── env.py         # Alembic environment configuration
│   ├── script.py.mako # Template for new migrations
│   └── versions/      # Migration scripts
│       └── 001_initial_schema.py
└── README.md          # This file
```

## Running Migrations

### Initial Setup

1. Ensure PostgreSQL is installed and running
2. Create the database and user:
   ```sql
   CREATE DATABASE rag_lab_db;
   CREATE USER rag_lab_user WITH PASSWORD 'your_password';  -- pragma: allowlist secret
   GRANT ALL PRIVILEGES ON DATABASE rag_lab_db TO rag_lab_user;
   ```

3. Set the PostgreSQL password in environment:
   ```bash
   export POSTGRES_PASSWORD='your_password'  # pragma: allowlist secret
   ```

### Apply Migrations

From the project root:

```bash
# Navigate to pipeline v3 directory
cd src/pipeline_v3

# Run migrations
uv run alembic upgrade head
```

### Create New Migration

```bash
# Auto-generate migration from model changes
uv run alembic revision --autogenerate -m "Description of changes"

# Or create empty migration
uv run alembic revision -m "Description of changes"
```

### Check Migration Status

```bash
# Show current revision
uv run alembic current

# Show migration history
uv run alembic history
```

### Rollback Migrations

```bash
# Rollback one migration
uv run alembic downgrade -1

# Rollback to specific revision
uv run alembic downgrade 001

# Rollback all migrations
uv run alembic downgrade base
```

## Migration Files

### 001_initial_schema.sql

Creates the initial database schema with four main schemas:

1. **registry** - Document state management
2. **search** - Full-text search with PostgreSQL tsvector
3. **jobs** - Asynchronous job queue
4. **fingerprints** - Document fingerprinting

Each schema includes:
- Tables with proper constraints and indexes
- UUID primary keys for multi-tenancy
- JSONB columns for flexible metadata
- Timestamps with automatic updates
- Helper functions and triggers

## Multi-Tenancy Preparation

All tables include a `tenant_id` column (default: `00000000-0000-0000-0000-000000000000`) for future multi-tenant support. Row-level security (RLS) can be enabled per tenant when needed.

## Performance Considerations

The schema includes:
- GIN indexes for JSONB columns
- GIN indexes for full-text search
- Partial indexes for common queries
- Trigram indexes for fuzzy search
- Proper foreign key constraints

## Security

- All sensitive operations should use prepared statements
- Connection strings should never include passwords in code
- Use environment variables for credentials
- Enable SSL for production deployments
