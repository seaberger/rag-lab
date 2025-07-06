# PostgreSQL Migration Plan for Pipeline v3

**Created:** January 6, 2025
**Issue:** [#77](https://github.com/seaberger/rag-lab/issues/77)
**Status:** Planning Complete, Ready for Implementation
**Branch:** `feature/postgresql-migration-77`

## Executive Summary

This document outlines the comprehensive plan for migrating Pipeline v3 from SQLite to PostgreSQL. This migration is critical for enabling multi-tenant support, improving concurrent access, and preparing for enterprise deployment. The migration will be implemented in phases to ensure backward compatibility during the transition.

## Table of Contents

1. [Current Architecture Analysis](#current-architecture-analysis)
2. [PostgreSQL Target Architecture](#postgresql-target-architecture)
3. [Implementation Phases](#implementation-phases)
4. [Technical Details](#technical-details)
5. [Migration Strategy](#migration-strategy)
6. [Testing Plan](#testing-plan)
7. [Rollback Procedures](#rollback-procedures)
8. [Timeline](#timeline)

## Current Architecture Analysis

### SQLite Databases

Pipeline v3 currently uses four separate SQLite databases:

1. **document_registry_v3.db**
   - Central document state tracking
   - Document lifecycle management
   - Consistency verification
   - Location: `./document_registry_v3.db`

2. **keyword_index_v3.db**
   - Full-text search using FTS5
   - BM25 ranking
   - Document metadata storage
   - Location: `./keyword_index_v3.db`

3. **jobs_v3.db**
   - Asynchronous job queue
   - Job state and progress tracking
   - Retry management
   - Location: `./jobs_v3.db`

4. **fingerprints_v3.db**
   - Document fingerprinting
   - Change detection
   - Processing status
   - Location: `./fingerprints_v3.db`

### Current Limitations

- **Concurrency**: SQLite write locks limit concurrent access
- **Performance**: No query parallelization
- **Features**: Limited JSON support, basic full-text search
- **Scalability**: Cannot scale horizontally
- **Multi-tenancy**: No built-in isolation mechanisms

## PostgreSQL Target Architecture

### Database Structure

```
rag_lab_db (PostgreSQL Database)
├── registry schema
│   └── documents table
├── search schema
│   ├── documents table
│   └── doc_metadata table
├── jobs schema
│   └── queue table
└── fingerprints schema
    └── fingerprints table
```

### Key Improvements

1. **Concurrency**: MVCC allows multiple concurrent readers/writers
2. **Performance**: Query parallelization, advanced indexing
3. **Features**: Native JSONB, advanced full-text search, trigrams
4. **Scalability**: Read replicas, partitioning support
5. **Multi-tenancy**: Row-level security, schema isolation

## Implementation Phases

### Phase 1: Foundation Setup (Week 1)

#### 1.1 Dependencies & Configuration

**Add to pyproject.toml:**
```toml
[project]
dependencies = [
    # ... existing dependencies ...
    "asyncpg>=0.29.0",  # Async PostgreSQL driver
    "psycopg[binary,pool]>=3.1.0",  # Sync driver with pooling
    "alembic>=1.13.0",  # Database migrations
]
```

**New Configuration Classes:**
```python
@dataclass
class PostgreSQLSettings:
    host: str = "localhost"
    port: int = 5432
    database: str = "rag_lab_db"
    user: str = "rag_lab_user"
    password: str = ""  # From environment variable
    ssl_mode: str = "prefer"

    # Connection pooling
    min_connections: int = 10
    max_connections: int = 100

    # Performance
    statement_timeout: int = 300000  # 5 minutes
    lock_timeout: int = 10000  # 10 seconds

    # Multi-tenancy prep
    enable_rls: bool = True
    default_schema: str = "public"
```

#### 1.2 Database Adapter Layer

**Base PostgreSQL Adapter (`src/pipeline_v3/core/postgres_base.py`):**
```python
class PostgreSQLBase:
    """Base class for PostgreSQL database operations with connection pooling."""

    def __init__(self, settings: PostgreSQLSettings, schema: str):
        self.settings = settings
        self.schema = schema
        self.pool = None

    async def initialize_pool(self):
        """Initialize connection pool with retry logic."""

    async def execute(self, query: str, *args, timeout: float = None):
        """Execute query with automatic retry and logging."""

    async def fetch_one(self, query: str, *args):
        """Fetch single row with connection management."""

    async def fetch_all(self, query: str, *args):
        """Fetch all rows with pagination support."""
```

#### 1.3 Schema Definitions

**Document Registry Schema:**
```sql
CREATE SCHEMA IF NOT EXISTS registry;

CREATE TABLE registry.documents (
    -- Primary identifiers
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT UNIQUE NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',

    -- Document metadata
    content_hash TEXT NOT NULL,
    size BIGINT NOT NULL,
    modified_time TIMESTAMPTZ NOT NULL,

    -- State tracking
    state TEXT NOT NULL CHECK (state IN ('NEW', 'INDEXED', 'UPDATING', 'STALE', 'CORRUPTED', 'REMOVED')),
    vector_indexed BOOLEAN DEFAULT FALSE,
    keyword_indexed BOOLEAN DEFAULT FALSE,

    -- Statistics
    chunk_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Extended metadata
    metadata JSONB DEFAULT '{}',

    -- Retry tracking
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    retry_strategy TEXT
);

-- Indexes for performance
CREATE INDEX idx_registry_tenant_state ON registry.documents(tenant_id, state);
CREATE INDEX idx_registry_source ON registry.documents(source);
CREATE INDEX idx_registry_metadata ON registry.documents USING GIN(metadata);
```

**Keyword Search Schema:**
```sql
CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE search.documents (
    id SERIAL PRIMARY KEY,
    doc_id UUID NOT NULL,
    chunk_id TEXT NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',

    -- Content
    text TEXT NOT NULL,
    keywords TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Full-text search
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(keywords, '')), 'A') ||
        setweight(to_tsvector('english', text), 'B')
    ) STORED,

    -- Constraints
    UNIQUE(tenant_id, doc_id, chunk_id)
);

-- Full-text search index
CREATE INDEX idx_search_vector ON search.documents USING GIN(search_vector);
CREATE INDEX idx_search_tenant ON search.documents(tenant_id);

-- Document metadata
CREATE TABLE search.doc_metadata (
    doc_id UUID PRIMARY KEY,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',
    source TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, source)
);
```

**Job Queue Schema:**
```sql
CREATE SCHEMA IF NOT EXISTS jobs;

CREATE TABLE jobs.queue (
    -- Identifiers
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',

    -- Job definition
    source TEXT NOT NULL,
    job_type TEXT NOT NULL,
    priority INTEGER DEFAULT 0,

    -- State tracking
    status TEXT NOT NULL CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED')),
    progress DECIMAL(5,2) DEFAULT 0.0,

    -- Worker tracking
    worker_id TEXT,

    -- Error handling
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Job data
    metadata JSONB DEFAULT '{}',
    intermediate_state JSONB DEFAULT '{}'
);

-- Indexes for job processing
CREATE INDEX idx_jobs_pending ON jobs.queue(tenant_id, status, priority DESC, created_at)
    WHERE status = 'PENDING';
CREATE INDEX idx_jobs_worker ON jobs.queue(worker_id)
    WHERE status = 'PROCESSING';
```

**Fingerprint Schema:**
```sql
CREATE SCHEMA IF NOT EXISTS fingerprints;

CREATE TABLE fingerprints.fingerprints (
    -- Primary key
    source TEXT NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000',

    -- Fingerprint data
    content_hash TEXT NOT NULL,
    size BIGINT NOT NULL,
    modified_time TIMESTAMPTZ NOT NULL,
    metadata_hash TEXT,

    -- Tracking
    doc_id UUID,
    processing_status TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_seen TIMESTAMPTZ DEFAULT NOW(),

    -- Primary key
    PRIMARY KEY(tenant_id, source)
);

-- Indexes
CREATE INDEX idx_fingerprints_doc_id ON fingerprints.fingerprints(doc_id);
CREATE INDEX idx_fingerprints_status ON fingerprints.fingerprints(processing_status);
```

### Phase 2: Core Implementation (Week 2)

#### 2.1 PostgreSQL Adapters

**Registry Adapter (`src/pipeline_v3/core/postgres_registry.py`):**
```python
class PostgreSQLDocumentRegistry(PostgreSQLBase):
    """PostgreSQL implementation of document registry."""

    def __init__(self, settings: PostgreSQLSettings):
        super().__init__(settings, "registry")

    async def add_document(self, doc_id: str, source: str, metadata: dict):
        """Add document with UPSERT semantics."""
        query = """
            INSERT INTO registry.documents (
                doc_id, source, content_hash, size,
                modified_time, state, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (source) DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                size = EXCLUDED.size,
                modified_time = EXCLUDED.modified_time,
                state = EXCLUDED.state,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
            RETURNING *
        """

    async def update_state(self, doc_id: str, state: str):
        """Update document state with consistency checks."""

    async def get_stale_documents(self, limit: int = 100):
        """Get documents needing update with tenant isolation."""
```

**Search Adapter (`src/pipeline_v3/storage/postgres_keyword.py`):**
```python
class PostgreSQLKeywordIndex(PostgreSQLBase):
    """PostgreSQL full-text search implementation."""

    async def search(self, query: str, limit: int = 10, tenant_id: str = None):
        """Full-text search with ranking."""
        search_query = """
            SELECT
                doc_id, chunk_id, text, keywords, metadata,
                ts_rank(search_vector, query) AS rank
            FROM
                search.documents,
                plainto_tsquery('english', $1) query
            WHERE
                ($2::uuid IS NULL OR tenant_id = $2) AND
                search_vector @@ query
            ORDER BY rank DESC
            LIMIT $3
        """
```

#### 2.2 Migration Features

**Advanced Search Capabilities:**
```sql
-- Fuzzy search with trigrams
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_search_text_trigram ON search.documents USING GIN(text gin_trgm_ops);

-- Phrase search function
CREATE FUNCTION search.phrase_search(query_text TEXT, tenant_uuid UUID DEFAULT NULL)
RETURNS TABLE(doc_id UUID, chunk_id TEXT, rank REAL) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.doc_id,
        d.chunk_id,
        ts_rank(d.search_vector, phraseto_tsquery('english', query_text)) AS rank
    FROM search.documents d
    WHERE
        (tenant_uuid IS NULL OR d.tenant_id = tenant_uuid) AND
        d.search_vector @@ phraseto_tsquery('english', query_text)
    ORDER BY rank DESC;
END;
$$ LANGUAGE plpgsql;
```

**Job Queue Enhancements:**
```sql
-- Function for atomic job claiming
CREATE FUNCTION jobs.claim_next_job(worker TEXT, tenant_uuid UUID DEFAULT NULL)
RETURNS jobs.queue AS $$
DECLARE
    job jobs.queue;
BEGIN
    SELECT * INTO job
    FROM jobs.queue
    WHERE
        status = 'PENDING' AND
        (tenant_uuid IS NULL OR tenant_id = tenant_uuid)
    ORDER BY priority DESC, created_at
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF FOUND THEN
        UPDATE jobs.queue
        SET
            status = 'PROCESSING',
            worker_id = worker,
            started_at = NOW(),
            updated_at = NOW()
        WHERE job_id = job.job_id;
    END IF;

    RETURN job;
END;
$$ LANGUAGE plpgsql;
```

### Phase 3: Migration Tools (Week 3)

#### 3.1 Data Migration Script

**Migration Tool (`src/pipeline_v3/tools/sqlite_to_postgres.py`):**
```python
class SQLiteToPostgresMigrator:
    """Migrate data from SQLite to PostgreSQL."""

    def __init__(self, sqlite_paths: dict, pg_settings: PostgreSQLSettings):
        self.sqlite_paths = sqlite_paths
        self.pg_settings = pg_settings
        self.stats = MigrationStats()

    async def migrate_all(self, batch_size: int = 1000):
        """Migrate all databases with progress tracking."""
        migrations = [
            self.migrate_registry(),
            self.migrate_keyword_index(),
            self.migrate_jobs(),
            self.migrate_fingerprints()
        ]
        await asyncio.gather(*migrations)

    async def migrate_registry(self):
        """Migrate document registry with validation."""

    async def validate_migration(self):
        """Verify data integrity post-migration."""
```

#### 3.2 Dual-Mode Support

**Database Factory (`src/pipeline_v3/core/db_factory.py`):**
```python
class DatabaseFactory:
    """Factory for creating database instances based on configuration."""

    @staticmethod
    def create_registry(config: PipelineConfig) -> DocumentRegistry:
        if config.database.backend == "postgresql":
            return PostgreSQLDocumentRegistry(config.database.postgresql)
        else:
            return SQLiteDocumentRegistry(config.storage.document_registry_path)

    @staticmethod
    def create_keyword_index(config: PipelineConfig) -> KeywordIndex:
        if config.database.backend == "postgresql":
            return PostgreSQLKeywordIndex(config.database.postgresql)
        else:
            return SQLiteKeywordIndex(config.storage.keyword_db_path)
```

**Configuration Update:**
```python
@dataclass
class DatabaseSettings:
    backend: str = "sqlite"  # "sqlite" or "postgresql"
    postgresql: PostgreSQLSettings = field(default_factory=PostgreSQLSettings)

    # Migration settings
    auto_migrate: bool = True
    migration_batch_size: int = 1000
```

### Phase 4: Multi-Tenant Preparation

#### 4.1 Row-Level Security

```sql
-- Enable RLS on all tables
ALTER TABLE registry.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE search.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs.queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE fingerprints.fingerprints ENABLE ROW LEVEL SECURITY;

-- Create policies
CREATE POLICY tenant_isolation ON registry.documents
    FOR ALL
    USING (tenant_id = current_setting('app.current_tenant')::uuid);

-- Create function to set tenant context
CREATE FUNCTION set_tenant_context(tenant_uuid UUID) RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant', tenant_uuid::text, false);
END;
$$ LANGUAGE plpgsql;
```

#### 4.2 Performance Optimizations

```sql
-- Partial indexes per tenant for large tables
CREATE INDEX idx_registry_tenant_1_active
    ON registry.documents(source, state)
    WHERE tenant_id = '11111111-1111-1111-1111-111111111111'
    AND state != 'REMOVED';

-- Table partitioning for job history
CREATE TABLE jobs.queue_history (LIKE jobs.queue) PARTITION BY RANGE (created_at);

-- Automated partition creation
CREATE TABLE jobs.queue_history_2025_01
    PARTITION OF jobs.queue_history
    FOR VALUES FROM ('2025-01-01') TO ('2025-02-01');
```

## Migration Strategy

### Pre-Migration Checklist

1. **Backup all SQLite databases**
2. **Document current record counts**
3. **Verify PostgreSQL installation and access**
4. **Test migration scripts on sample data**
5. **Plan maintenance window**

### Migration Steps

1. **Deploy dual-mode code** (supports both backends)
2. **Run migration script** with validation
3. **Verify data integrity**
4. **Switch configuration** to PostgreSQL
5. **Monitor performance** and errors
6. **Keep SQLite as backup** for rollback

### Post-Migration Validation

1. **Record count verification**
2. **Search result comparison**
3. **Job processing verification**
4. **Performance benchmarking**
5. **Concurrent access testing**

## Testing Plan

### Unit Tests

- Test all PostgreSQL adapters
- Verify SQL query compatibility
- Test connection pooling and retries
- Validate data type conversions

### Integration Tests

- End-to-end document processing
- Search functionality across backends
- Job queue processing
- Concurrent operation testing

### Performance Tests

- Benchmark search performance
- Test concurrent document processing
- Measure job throughput
- Validate index effectiveness

### Migration Tests

- Test data migration accuracy
- Verify rollback procedures
- Test incremental migration
- Validate dual-mode operation

## Rollback Procedures

### Immediate Rollback

1. **Stop all processing**
2. **Switch configuration** back to SQLite
3. **Restart services**
4. **Verify functionality**

### Data Rollback

1. **Export PostgreSQL data** if changes made
2. **Restore SQLite backups**
3. **Apply incremental changes**
4. **Verify data consistency**

## Timeline

### Week 1: Foundation
- Day 1-2: Dependencies and configuration
- Day 3-4: Base adapter implementation
- Day 5: Schema creation and testing

### Week 2: Core Implementation
- Day 1-2: Registry and search adapters
- Day 3-4: Job queue and fingerprint adapters
- Day 5: Integration testing

### Week 3: Migration Tools
- Day 1-2: Migration script development
- Day 3: Dual-mode implementation
- Day 4-5: Testing and validation

### Week 4: Deployment
- Day 1-2: Production preparation
- Day 3: Migration execution
- Day 4-5: Monitoring and optimization

## Risk Mitigation

### Technical Risks

1. **Data Loss**: Comprehensive backups and validation
2. **Performance Degradation**: Extensive benchmarking
3. **Compatibility Issues**: Dual-mode support period
4. **Connection Failures**: Retry logic and pooling

### Operational Risks

1. **Downtime**: Plan maintenance window
2. **Rollback Complexity**: Tested procedures
3. **Training Needs**: Documentation and guides
4. **Monitoring Gaps**: Enhanced logging

## Success Criteria

1. **All data migrated** with 100% accuracy
2. **No performance degradation** vs SQLite
3. **Concurrent operations** working correctly
4. **Multi-tenant isolation** verified
5. **Zero data loss** during migration

## Next Steps

1. **Review and approve** this plan
2. **Set up PostgreSQL** test environment
3. **Begin Phase 1** implementation
4. **Schedule migration** window

## Related Documents

- [Issue #77](https://github.com/seaberger/rag-lab/issues/77) - PostgreSQL Migration
- [ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md](../docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) - Multi-tenant vision
- [ROADMAP.md](../../../ROADMAP.md) - Project roadmap
- [CLAUDE.md](../CLAUDE.md) - Pipeline v3 context
