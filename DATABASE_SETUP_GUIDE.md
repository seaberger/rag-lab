# Database Setup Guide - Pipeline v3

This guide provides complete instructions for setting up PostgreSQL and Qdrant databases from scratch for the RAG Lab Pipeline v3 system.

## 🎯 Overview

Pipeline v3 uses a multi-database architecture:
- **PostgreSQL**: Multi-tenant data storage with Row-Level Security (RLS)
- **Qdrant**: Vector database for semantic search

## 📋 Prerequisites

### Required Software
- **PostgreSQL** 13+ with extensions: `uuid-ossp`, `pg_trgm`, `unaccent`
- **Qdrant Server** (Docker or standalone)
- **Python** 3.11+ with `uv` package manager

### Environment Variables
Create `.env` file in project root:
```bash
# OpenAI API
OPENAI_API_KEY=your_openai_api_key_here

# PostgreSQL
POSTGRES_PASSWORD=your_secure_password
POSTGRES_USER=rag_user
POSTGRES_DB=rag_lab
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## 🐘 PostgreSQL Setup

### Step 1: Install PostgreSQL

**macOS (Homebrew):**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql-15 postgresql-contrib-15
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**Docker Alternative:**
```bash
docker run -d \
  --name rag-lab-postgres \
  -e POSTGRES_USER=rag_user \
  -e POSTGRES_PASSWORD=your_secure_password \
  -e POSTGRES_DB=rag_lab \
  -p 5432:5432 \
  postgres:15-alpine
```

### Step 2: Create Database and User

```bash
# Connect as postgres superuser
sudo -u postgres psql

# Create user and database
CREATE USER rag_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE rag_lab OWNER rag_user;
GRANT ALL PRIVILEGES ON DATABASE rag_lab TO rag_user;

# Connect to the new database
\c rag_lab

# Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "unaccent";

# Grant extension usage
GRANT ALL ON SCHEMA public TO rag_user;

\q
```

### Step 3: Run Database Migrations

The system includes multiple migration files that must be run in order:

```bash
# Navigate to project root
cd /Users/seanbergman/Repositories/rag_lab

# Run migrations in order
export POSTGRES_PASSWORD=your_secure_password

# 1. Initial schema with all tables
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/postgres/001_initial_schema.sql

# 2. Row-Level Security and multi-tenancy
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/postgres/002_row_level_security.sql

# 3. Index entries table for chunk tracking
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/postgres/003_add_index_entries.sql

# 4. Enhanced tenant management (optional - for full enterprise features)
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/003_tenant_management.sql

# 5. Fix tenant functions (applies bug fixes)
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/postgres/005_fix_tenant_functions.sql
```

### Step 4: Create Initial Tenants

```bash
# Create test tenants for development
psql -h localhost -U rag_user -d rag_lab << 'EOF'
-- Create LMC tenant
SELECT tenants.create_tenant('lmc-dev', 'LMC Development', 50000, 500);

-- Create Matrix tenant
SELECT tenants.create_tenant('matrix', 'Matrix Technologies', 25000, 250);

-- Create CellX tenant
SELECT tenants.create_tenant('cellx', 'CellX Innovation', 15000, 150);

-- Verify tenants created
SELECT tenant_id, name, display_name, max_documents FROM tenants.tenants;
EOF
```

### Step 5: Verify Database Structure

```bash
# Check schemas and tables
psql -h localhost -U rag_user -d rag_lab << 'EOF'
-- List all schemas
\dn+

-- List tables by schema
\dt registry.*
\dt search.*
\dt jobs.*
\dt fingerprints.*
\dt tenants.*

-- Check RLS policies
SELECT schemaname, tablename, policyname, permissive
FROM pg_policies
ORDER BY schemaname, tablename;

-- Check migration status
SELECT * FROM migrations.schema_versions ORDER BY version;
EOF
```

## 🔍 Qdrant Setup

### Option 1: Docker (Recommended)

```bash
# Start Qdrant server
docker run -d \
  --name rag-lab-qdrant \
  -p 6333:6333 \
  -p 6334:6334 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

### Option 2: Standalone Installation

```bash
# Download and install Qdrant
curl -L https://github.com/qdrant/qdrant/releases/latest/download/qdrant-x86_64-unknown-linux-gnu.tar.gz | tar xz
./qdrant --config-path ./config/production.yaml
```

### Option 3: Local File Mode

Update `config.yaml` to use local file storage:
```yaml
qdrant:
  mode: local  # Instead of 'server'
  path: ./qdrant_data_v3
```

## ⚙️ Configuration

### Update config.yaml

Ensure your `config.yaml` has the correct database settings:

```yaml
database:
  backend: postgresql
  postgresql:
    host: localhost
    port: 5432
    database: rag_lab
    user: rag_user
    password: ""  # Will use POSTGRES_PASSWORD env var
    default_tenant_id: "00000000-0000-0000-0000-000000000000"  # Default tenant
    pool_size: 10
    max_overflow: 20

qdrant:
  mode: server  # or 'local' for file-based storage
  server:
    host: localhost
    port: 6333
    grpc_port: 6334
    api_key: null
    https: false
    timeout: 30
  collection_name: datasheets_v3
```

## 🧪 Testing the Setup

### Test PostgreSQL Connection

```bash
# Test connection and tenant setup
uv run python -c "
from src.pipeline_v3.utils.config import PipelineConfig
from src.pipeline_v3.database.database_factory import DatabaseFactory

config = PipelineConfig()
factory = DatabaseFactory(config)

print('✅ PostgreSQL configuration valid:', factory.validate_backend_configuration())

# Test creating adapters
adapters = factory.create_all()
print('✅ Database adapters created successfully')

# Test tenant context
registry = adapters['registry']
print('✅ Registry adapter working')
"
```

### Test Qdrant Connection

```bash
# Test Qdrant connection
uv run python -c "
import qdrant_client
client = qdrant_client.QdrantClient(host='localhost', port=6333)
collections = client.get_collections()
print('✅ Qdrant server accessible, collections:', [c.name for c in collections.collections])
"
```

### Test Document Processing

```bash
# Test end-to-end processing
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf --mode datasheet

# Verify data is properly stored with tenant isolation
uv run python -m src.pipeline_v3.cli_main search "laser power" --type hybrid --top-k 3
```

## 🔧 Database Schema Overview

### Core Schemas Created

1. **`registry`** - Document state management
   - `documents` - Central document registry
   - `index_entries` - Document chunk tracking

2. **`search`** - Full-text search
   - `documents` - Searchable document chunks
   - `doc_metadata` - Document metadata

3. **`jobs`** - Job queue management
   - `queue` - Asynchronous job processing

4. **`fingerprints`** - Change detection
   - `fingerprints` - Document fingerprints

5. **`tenants`** - Multi-tenancy
   - `tenants` - Tenant management
   - `api_keys` - API authentication (enterprise)
   - `usage_metrics` - Usage tracking (enterprise)
   - `audit_log` - Security audit log

6. **`migrations`** - Schema versioning
   - `schema_versions` - Migration tracking

### Row-Level Security (RLS)

All main tables have RLS policies that:
- ✅ **Isolate tenant data** - Each tenant only sees their own data
- ✅ **Allow admin bypass** - `postgres` role can access all data
- ✅ **Use session context** - Tenant ID set via `tenants.set_current_tenant()`

### Tenant Context Functions

- `tenants.current_tenant_id()` - Get current tenant from session
- `tenants.set_current_tenant(uuid)` - Set tenant context
- `tenants.create_tenant(name, display_name)` - Create new tenant

## 🐛 Troubleshooting

### Common Issues

**1. Migration Errors**
```bash
# Check migration status
psql -h localhost -U rag_user -d rag_lab -c "SELECT * FROM migrations.schema_versions;"

# Re-run specific migration
psql -h localhost -U rag_user -d rag_lab -f src/pipeline_v3/migrations/postgres/[migration_file].sql
```

**2. Permission Errors**
```bash
# Grant missing permissions
psql -h localhost -U rag_user -d rag_lab << 'EOF'
GRANT USAGE ON SCHEMA registry, search, jobs, fingerprints, tenants TO rag_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA registry, search, jobs, fingerprints, tenants TO rag_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA registry, search, jobs, fingerprints, tenants TO rag_user;
EOF
```

**3. Qdrant Connection Issues**
```bash
# Check if Qdrant is running
curl http://localhost:6333/collections

# Check Docker logs
docker logs rag-lab-qdrant
```

**4. Tenant Context Issues**
```bash
# Verify tenant exists and is active
psql -h localhost -U rag_user -d rag_lab -c "SELECT * FROM tenants.tenants WHERE is_active = true;"

# Test setting tenant context
psql -h localhost -U rag_user -d rag_lab -c "SELECT tenants.set_current_tenant('00000000-0000-0000-0000-000000000000'::uuid);"
```

### Clean Reset (Nuclear Option)

If you need to completely reset the databases:

```bash
# PostgreSQL - DROP and recreate
sudo -u postgres psql << 'EOF'
DROP DATABASE IF EXISTS rag_lab;
DROP USER IF EXISTS rag_user;
CREATE USER rag_user WITH PASSWORD 'your_secure_password';
CREATE DATABASE rag_lab OWNER rag_user;
EOF

# Qdrant - Remove Docker container and data
docker stop rag-lab-qdrant
docker rm rag-lab-qdrant
rm -rf qdrant_storage

# Then re-run setup from Step 2
```

## 📚 Next Steps

1. **Load test data**: Use CLI to add sample documents
2. **Configure tenants**: Set up tenant-specific collections if needed
3. **Test searches**: Verify tenant isolation in search results
4. **Production setup**: Configure SSL, backups, monitoring

## 🔗 Related Documentation

- [Pipeline v3 CLAUDE.md](src/pipeline_v3/CLAUDE.md) - Development context
- [USER_MANUAL.md](src/pipeline_v3/USER_MANUAL.md) - Complete usage guide
- [Enterprise Implementation](src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) - Advanced features

---

**Database Version**: Schema v5 (with tenant function fixes)
**Last Updated**: 2025-01-07
**Compatible with**: Pipeline v3.2+
