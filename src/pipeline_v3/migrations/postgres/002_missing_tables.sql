-- Create missing tables for RAG Lab Pipeline v3
-- This migration adds tables that were missing from the initial schema

-- ============================================
-- REGISTRY SCHEMA - Index Entries
-- ============================================

-- Create index_entries table for tracking indexed chunks
CREATE TABLE IF NOT EXISTS registry.index_entries (
    -- Primary identifiers
    id SERIAL PRIMARY KEY,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
    doc_id UUID NOT NULL,

    -- Index tracking
    index_type VARCHAR(20) NOT NULL CHECK (index_type IN ('vector', 'keyword')),
    node_id VARCHAR(255) NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- Content tracking
    content_hash VARCHAR(64),

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    indexed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(tenant_id, doc_id, index_type, node_id),
    FOREIGN KEY (doc_id) REFERENCES registry.documents(doc_id) ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_index_entries_tenant ON registry.index_entries(tenant_id);
CREATE INDEX idx_index_entries_doc_id ON registry.index_entries(doc_id);
CREATE INDEX idx_index_entries_type ON registry.index_entries(index_type);
CREATE INDEX idx_index_entries_node_id ON registry.index_entries(node_id);

-- ============================================
-- SEARCH SCHEMA - Keyword Search
-- ============================================

-- Create keyword_search table (alternative to search.documents)
CREATE TABLE IF NOT EXISTS search.keyword_search (
    id SERIAL PRIMARY KEY,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,
    doc_id VARCHAR(255) NOT NULL,
    node_id VARCHAR(255) NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- Content
    content TEXT NOT NULL,
    content_tsvector tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,
    content_hash VARCHAR(64),

    -- Timestamps
    indexed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(tenant_id, node_id)
);

-- Full-text search indexes
CREATE INDEX idx_keyword_search_tsvector ON search.keyword_search USING GIN(content_tsvector);
CREATE INDEX idx_keyword_search_tenant ON search.keyword_search(tenant_id);
CREATE INDEX idx_keyword_search_doc_id ON search.keyword_search(doc_id);

-- ============================================
-- Update existing tables to match expected schema
-- ============================================

-- Add missing columns to registry.documents if they don't exist
DO $$
BEGIN
    -- Add doc_type column if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'registry'
                   AND table_name = 'documents'
                   AND column_name = 'doc_type') THEN
        ALTER TABLE registry.documents ADD COLUMN doc_type VARCHAR(50);
    END IF;

    -- Add file_size as alias for size if needed
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'registry'
                   AND table_name = 'documents'
                   AND column_name = 'file_size') THEN
        ALTER TABLE registry.documents ADD COLUMN file_size BIGINT;
        UPDATE registry.documents SET file_size = size WHERE file_size IS NULL;
    END IF;

    -- Add indexed_at column if missing
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'registry'
                   AND table_name = 'documents'
                   AND column_name = 'indexed_at') THEN
        ALTER TABLE registry.documents ADD COLUMN indexed_at TIMESTAMPTZ;
    END IF;

    -- Add error_message column if it's called last_error
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = 'registry'
                   AND table_name = 'documents'
                   AND column_name = 'error_message') THEN
        ALTER TABLE registry.documents ADD COLUMN error_message TEXT;
        UPDATE registry.documents SET error_message = last_error WHERE error_message IS NULL;
    END IF;
END$$;

-- ============================================
-- Create simplified views for compatibility
-- ============================================

-- Create a view that matches the expected schema without schema prefixes
CREATE OR REPLACE VIEW public.documents AS
SELECT
    doc_id::VARCHAR(255) as doc_id,
    tenant_id::VARCHAR(100) as tenant_id,
    source,
    content_hash,
    COALESCE(file_size, size) as file_size,
    doc_type,
    state,
    created_at::TIMESTAMP as created_at,
    updated_at::TIMESTAMP as updated_at,
    indexed_at::TIMESTAMP as indexed_at,
    vector_indexed,
    keyword_indexed,
    chunk_count,
    COALESCE(error_message, last_error) as error_message,
    metadata
FROM registry.documents;

-- Create similar views for other tables
CREATE OR REPLACE VIEW public.index_entries AS
SELECT * FROM registry.index_entries;

CREATE OR REPLACE VIEW public.keyword_search AS
SELECT * FROM search.keyword_search;

CREATE OR REPLACE VIEW public.doc_metadata AS
SELECT * FROM search.doc_metadata;

CREATE OR REPLACE VIEW public.jobs AS
SELECT * FROM jobs.queue;

CREATE OR REPLACE VIEW public.fingerprints AS
SELECT * FROM fingerprints.fingerprints;

-- ============================================
-- MIGRATION TRACKING
-- ============================================

-- Record this migration
INSERT INTO migrations.schema_versions (version, description, checksum)
VALUES (2, 'Add missing tables and compatibility views', 'missing_tables_v2')
ON CONFLICT (version) DO NOTHING;
