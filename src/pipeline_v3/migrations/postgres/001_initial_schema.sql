-- PostgreSQL Initial Schema for RAG Lab Pipeline v3
-- This migration creates all schemas and tables for the document processing system
-- with multi-tenancy support preparation

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- For fuzzy text search
CREATE EXTENSION IF NOT EXISTS "unaccent";   -- For accent-insensitive search

-- ============================================
-- REGISTRY SCHEMA - Document State Management
-- ============================================

CREATE SCHEMA IF NOT EXISTS registry;

-- Main documents table
CREATE TABLE IF NOT EXISTS registry.documents (
    -- Primary identifiers
    doc_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT UNIQUE NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,

    -- Document metadata
    content_hash TEXT NOT NULL,
    size BIGINT NOT NULL,
    modified_time TIMESTAMPTZ NOT NULL,

    -- State tracking
    state TEXT NOT NULL DEFAULT 'NEW' CHECK (state IN ('NEW', 'INDEXED', 'UPDATING', 'STALE', 'CORRUPTED', 'REMOVED')),
    vector_indexed BOOLEAN DEFAULT FALSE,
    keyword_indexed BOOLEAN DEFAULT FALSE,

    -- Statistics
    chunk_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    last_error TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Extended metadata (JSONB for flexible schema)
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Retry tracking
    retry_count INTEGER DEFAULT 0,
    last_retry_at TIMESTAMPTZ,
    retry_strategy TEXT
);

-- Indexes for performance
CREATE INDEX idx_registry_tenant_state ON registry.documents(tenant_id, state);
CREATE INDEX idx_registry_source ON registry.documents(source);
CREATE INDEX idx_registry_metadata ON registry.documents USING GIN(metadata);
CREATE INDEX idx_registry_modified_time ON registry.documents(modified_time);
CREATE INDEX idx_registry_updated_at ON registry.documents(updated_at);

-- Update trigger for updated_at
CREATE OR REPLACE FUNCTION registry.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_registry_documents_updated_at
    BEFORE UPDATE ON registry.documents
    FOR EACH ROW
    EXECUTE FUNCTION registry.update_updated_at_column();

-- ============================================
-- SEARCH SCHEMA - Full-Text Search
-- ============================================

CREATE SCHEMA IF NOT EXISTS search;

-- Main search documents table
CREATE TABLE IF NOT EXISTS search.documents (
    id SERIAL PRIMARY KEY,
    doc_id UUID NOT NULL,
    chunk_id TEXT NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,

    -- Content
    text TEXT NOT NULL,
    keywords TEXT,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Full-text search vector (generated column)
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', COALESCE(keywords, '')), 'A') ||
        setweight(to_tsvector('english', text), 'B')
    ) STORED,

    -- Constraints
    UNIQUE(tenant_id, doc_id, chunk_id)
);

-- Full-text search indexes
CREATE INDEX idx_search_vector ON search.documents USING GIN(search_vector);
CREATE INDEX idx_search_tenant ON search.documents(tenant_id);
CREATE INDEX idx_search_doc_id ON search.documents(doc_id);
CREATE INDEX idx_search_metadata ON search.documents USING GIN(metadata);

-- Trigram index for fuzzy search
CREATE INDEX idx_search_text_trigram ON search.documents USING GIN(text gin_trgm_ops);

-- Document metadata table (similar to SQLite doc_metadata)
CREATE TABLE IF NOT EXISTS search.doc_metadata (
    doc_id UUID PRIMARY KEY,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
    source TEXT NOT NULL,
    metadata JSONB DEFAULT '{}'::jsonb,
    chunk_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(tenant_id, source)
);

CREATE INDEX idx_search_doc_metadata_tenant ON search.doc_metadata(tenant_id);
CREATE INDEX idx_search_doc_metadata_source ON search.doc_metadata(source);

-- Helper function for phrase search
CREATE OR REPLACE FUNCTION search.phrase_search(
    query_text TEXT,
    tenant_uuid UUID DEFAULT NULL,
    limit_count INTEGER DEFAULT 10
)
RETURNS TABLE(
    doc_id UUID,
    chunk_id TEXT,
    text TEXT,
    keywords TEXT,
    metadata JSONB,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.doc_id,
        d.chunk_id,
        d.text,
        d.keywords,
        d.metadata,
        ts_rank(d.search_vector, phraseto_tsquery('english', query_text)) AS rank
    FROM search.documents d
    WHERE
        (tenant_uuid IS NULL OR d.tenant_id = tenant_uuid) AND
        d.search_vector @@ phraseto_tsquery('english', query_text)
    ORDER BY rank DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- JOBS SCHEMA - Job Queue Management
-- ============================================

CREATE SCHEMA IF NOT EXISTS jobs;

CREATE TABLE IF NOT EXISTS jobs.queue (
    -- Identifiers
    job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,

    -- Job definition
    source TEXT NOT NULL,
    job_type TEXT NOT NULL DEFAULT 'DOCUMENT_PROCESSING',
    priority INTEGER DEFAULT 0,

    -- State tracking
    status TEXT NOT NULL DEFAULT 'PENDING' CHECK (
        status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'CANCELLED', 'INTERRUPTED')
    ),
    progress DECIMAL(5,2) DEFAULT 0.0 CHECK (progress >= 0 AND progress <= 100),

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
    metadata JSONB DEFAULT '{}'::jsonb,
    intermediate_state JSONB DEFAULT '{}'::jsonb
);

-- Indexes for job processing
CREATE INDEX idx_jobs_pending ON jobs.queue(tenant_id, status, priority DESC, created_at)
    WHERE status = 'PENDING';
CREATE INDEX idx_jobs_processing ON jobs.queue(worker_id, status)
    WHERE status = 'PROCESSING';
CREATE INDEX idx_jobs_tenant_status ON jobs.queue(tenant_id, status);
CREATE INDEX idx_jobs_created_at ON jobs.queue(created_at);

-- Update trigger for updated_at
CREATE TRIGGER update_jobs_queue_updated_at
    BEFORE UPDATE ON jobs.queue
    FOR EACH ROW
    EXECUTE FUNCTION registry.update_updated_at_column();

-- Function for atomic job claiming (using FOR UPDATE SKIP LOCKED)
CREATE OR REPLACE FUNCTION jobs.claim_next_job(
    worker TEXT,
    tenant_uuid UUID DEFAULT NULL
)
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

-- ============================================
-- FINGERPRINTS SCHEMA - Document Fingerprinting
-- ============================================

CREATE SCHEMA IF NOT EXISTS fingerprints;

CREATE TABLE IF NOT EXISTS fingerprints.fingerprints (
    -- Primary key
    source TEXT NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,

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
CREATE INDEX idx_fingerprints_content_hash ON fingerprints.fingerprints(content_hash);
CREATE INDEX idx_fingerprints_last_seen ON fingerprints.fingerprints(last_seen);

-- ============================================
-- MIGRATION TRACKING
-- ============================================

CREATE SCHEMA IF NOT EXISTS migrations;

CREATE TABLE IF NOT EXISTS migrations.schema_versions (
    version INTEGER PRIMARY KEY,
    description TEXT NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW(),
    checksum TEXT
);

-- Record this migration
INSERT INTO migrations.schema_versions (version, description, checksum)
VALUES (1, 'Initial schema with all tables', 'initial_schema_v1')
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- FUTURE MULTI-TENANCY PREPARATION
-- ============================================

-- Create tenant management table (for future use)
CREATE SCHEMA IF NOT EXISTS tenants;

CREATE TABLE IF NOT EXISTS tenants.tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,

    -- Settings
    settings JSONB DEFAULT '{}'::jsonb,

    -- Quotas
    max_documents INTEGER DEFAULT 10000,
    max_storage_gb INTEGER DEFAULT 100,

    -- Status
    status TEXT DEFAULT 'active' CHECK (status IN ('active', 'suspended', 'deleted')),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Default tenant for single-tenant mode
INSERT INTO tenants.tenants (tenant_id, name, display_name)
VALUES ('00000000-0000-0000-0000-000000000000'::uuid, 'default', 'Default Tenant')
ON CONFLICT (tenant_id) DO NOTHING;

-- ============================================
-- PERMISSIONS AND COMMENTS
-- ============================================

-- Add helpful comments
COMMENT ON SCHEMA registry IS 'Document registry for tracking document states and metadata';
COMMENT ON SCHEMA search IS 'Full-text search indexes and document content';
COMMENT ON SCHEMA jobs IS 'Asynchronous job queue for document processing';
COMMENT ON SCHEMA fingerprints IS 'Document fingerprinting for change detection';
COMMENT ON SCHEMA tenants IS 'Multi-tenant management (future use)';

COMMENT ON TABLE registry.documents IS 'Central document registry tracking all documents in the system';
COMMENT ON TABLE search.documents IS 'Searchable document chunks with full-text indexes';
COMMENT ON TABLE jobs.queue IS 'Job queue for asynchronous document processing';
COMMENT ON TABLE fingerprints.fingerprints IS 'Document fingerprints for detecting changes';

-- Grant permissions (adjust based on your PostgreSQL user setup)
-- GRANT USAGE ON SCHEMA registry, search, jobs, fingerprints TO rag_lab_user;
-- GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA registry, search, jobs, fingerprints TO rag_lab_user;
-- GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA registry, search, jobs, fingerprints TO rag_lab_user;
