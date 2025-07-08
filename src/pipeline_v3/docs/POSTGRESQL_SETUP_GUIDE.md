# PostgreSQL Setup Guide for RAG Lab

This guide provides step-by-step instructions for setting up PostgreSQL from scratch for RAG Lab Pipeline v3.

## Prerequisites

- Docker and Docker Compose installed
- `psql` client (optional but recommended for troubleshooting)
  ```bash
  # Install on macOS
  brew install libpq
  export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
  ```

## Quick Start

### 1. Start PostgreSQL Server

```bash
# From project root
./scripts/postgres_server.sh start
```

This starts PostgreSQL using Docker Compose with:
- **Database**: `rag_lab`
- **User**: `rag_user`
- **Password**: `rag_dev_password` (configurable via POSTGRES_PASSWORD env var)
- **Port**: 5432

### 2. Initialize Database Schema

```bash
# Source environment variables
source .env.postgres

# Run initial schema migrations
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
PGPASSWORD=rag_dev_password psql -U rag_user -h localhost -d rag_lab \
  -f src/pipeline_v3/migrations/postgres/001_initial_schema.sql
```

This creates all necessary schemas and tables:
- `registry.*` - Document registry and state management
- `search.*` - Full-text search indexes
- `jobs.*` - Job queue management
- `fingerprints.*` - Document change detection
- `tenants.*` - Multi-tenant management (basic)

### 3. Setup Row-Level Security (Optional)

For multi-tenant deployments:

```bash
# First, ensure PYTHONPATH is set
export PYTHONPATH=/Users/seanbergman/Repositories/rag_lab

# Run RLS setup
uv run python src/pipeline_v3/scripts/setup_rls.py
```

### 4. Create Demo Tenants (Optional)

```bash
# Create three demo tenants: lmc, cellx, matrix
uv run python src/pipeline_v3/scripts/setup_demo_tenants.py
```

## Configuration

### Pipeline Configuration

The Pipeline v3 configuration automatically uses PostgreSQL when `config.yaml` is symlinked to `config_postgres.yaml`:

```yaml
# config_postgres.yaml
database:
  backend: postgresql
  postgresql:
    host: localhost
    port: 5432
    database: rag_lab
    user: rag_user
    password: ""  # Set via POSTGRES_PASSWORD environment variable
```

### Environment Variables

Create `.env.postgres` file:

```bash
# PostgreSQL credentials
export POSTGRES_PASSWORD=rag_dev_password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DB=rag_lab
export POSTGRES_USER=rag_user
```

## Troubleshooting

### Connection Issues

1. **Check PostgreSQL is running**:
   ```bash
   ./scripts/postgres_server.sh status
   ```

2. **View logs**:
   ```bash
   ./scripts/postgres_server.sh logs
   ```

3. **Test connection**:
   ```bash
   export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
   PGPASSWORD=rag_dev_password psql -U rag_user -h localhost -d rag_lab -c "\l"
   ```

### Common Issues

1. **Password authentication failed**:
   - Ensure environment variables match Docker Compose settings
   - Check that `rag_user` exists with correct password

2. **Database corruption**:
   ```bash
   # Stop server and remove data
   ./scripts/postgres_server.sh stop
   rm -rf postgres_data
   ./scripts/postgres_server.sh start
   # Re-run migrations
   ```

3. **Missing tables**:
   - Re-run the initial schema migration
   - Check migration logs for errors

### Using psql for Debugging

```bash
# Connect to database
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"
PGPASSWORD=rag_dev_password psql -U rag_user -h localhost -d rag_lab

# Useful commands:
\dt *.*              # List all tables
\du                  # List users
\l                   # List databases
\dn                  # List schemas
\d+ registry.documents  # Describe table
```

## Database Schema Overview

### Core Schemas

1. **registry** - Document management
   - `documents` - Main document registry
   - `index_entries` - Index tracking (if created)

2. **search** - Full-text search
   - `documents` - Searchable chunks
   - `doc_metadata` - Document metadata

3. **jobs** - Queue management
   - `queue` - Job processing queue

4. **fingerprints** - Change detection
   - `fingerprints` - Document fingerprints

5. **tenants** - Multi-tenancy
   - `tenants` - Tenant registry
   - `api_keys` - API key management

### Key Features

- **Full-text search**: PostgreSQL tsvector with English stemming
- **Fuzzy search**: pg_trgm extension for trigram matching
- **UUID support**: uuid-ossp extension for primary keys
- **JSONB metadata**: Flexible schema for custom attributes
- **Row-level security**: Prepared but not enabled by default

## Advanced Setup

### Enable All Enterprise Features

```bash
# 1. Run all PostgreSQL migrations
for migration in src/pipeline_v3/migrations/postgres/*.sql; do
    PGPASSWORD=rag_dev_password psql -U rag_user -h localhost -d rag_lab -f "$migration"
done

# 2. Setup RLS
uv run python src/pipeline_v3/scripts/setup_rls.py

# 3. Create demo tenants
uv run python src/pipeline_v3/scripts/setup_demo_tenants.py

# 4. Test isolation
uv run python -m pytest src/pipeline_v3/tests/integration/test_multi_tenant_isolation.py -v
```

## Production Considerations

1. **Credentials**: Change default passwords for production
2. **Backups**: Set up regular PostgreSQL backups
3. **Monitoring**: Enable PostgreSQL logging and metrics
4. **Connection pooling**: Configure appropriate pool sizes
5. **SSL**: Enable SSL for production deployments
6. **Resource limits**: Set appropriate PostgreSQL memory and connection limits

## Next Steps

- Review [POSTGRESQL_MIGRATION_PLAN.md](POSTGRESQL_MIGRATION_PLAN.md) for detailed architecture
- See [RLS_IMPLEMENTATION_SUMMARY.md](RLS_IMPLEMENTATION_SUMMARY.md) for multi-tenant setup
- Check [ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md](ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) for full enterprise features
