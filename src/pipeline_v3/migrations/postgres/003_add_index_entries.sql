-- PostgreSQL Index Entries Table Migration
-- This migration adds the index_entries table to track document chunks in indexes

-- ============================================
-- INDEX ENTRIES TABLE
-- ============================================

-- Add index entries table to registry schema (referenced by existing code)
CREATE TABLE IF NOT EXISTS registry.index_entries (
    -- Identifiers
    id SERIAL PRIMARY KEY,
    doc_id UUID NOT NULL,
    tenant_id UUID DEFAULT '00000000-0000-0000-0000-000000000000'::uuid,

    -- Index information
    index_type TEXT NOT NULL CHECK (index_type IN ('vector', 'keyword', 'both')),
    node_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,

    -- Content tracking
    content_hash TEXT NOT NULL,

    -- Metadata
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE(tenant_id, doc_id, index_type, chunk_index),

    -- Foreign key to documents table
    FOREIGN KEY (doc_id, tenant_id) REFERENCES registry.documents(doc_id, tenant_id)
        ON DELETE CASCADE
);

-- Indexes for performance
CREATE INDEX idx_index_entries_doc_id ON registry.index_entries(doc_id);
CREATE INDEX idx_index_entries_tenant ON registry.index_entries(tenant_id);
CREATE INDEX idx_index_entries_type ON registry.index_entries(index_type);
CREATE INDEX idx_index_entries_node_id ON registry.index_entries(node_id);
CREATE INDEX idx_index_entries_metadata ON registry.index_entries USING GIN(metadata);

-- Update trigger for updated_at
CREATE TRIGGER update_index_entries_updated_at
    BEFORE UPDATE ON registry.index_entries
    FOR EACH ROW
    EXECUTE FUNCTION registry.update_updated_at_column();

-- ============================================
-- HELPER FUNCTIONS FOR INDEX MANAGEMENT
-- ============================================

-- Function to get index entry statistics
CREATE OR REPLACE FUNCTION registry.get_index_statistics(tenant_uuid UUID DEFAULT NULL)
RETURNS TABLE(
    tenant_id UUID,
    index_type TEXT,
    total_entries BIGINT,
    unique_documents BIGINT,
    avg_chunks_per_doc NUMERIC
) AS $$
DECLARE
    effective_tenant_id UUID;
BEGIN
    effective_tenant_id := COALESCE(tenant_uuid, tenants.current_tenant_id());

    RETURN QUERY
    SELECT
        ie.tenant_id,
        ie.index_type,
        COUNT(*) as total_entries,
        COUNT(DISTINCT ie.doc_id) as unique_documents,
        ROUND(COUNT(*)::NUMERIC / COUNT(DISTINCT ie.doc_id), 2) as avg_chunks_per_doc
    FROM registry.index_entries ie
    WHERE ie.tenant_id = effective_tenant_id
    GROUP BY ie.tenant_id, ie.index_type
    ORDER BY ie.index_type;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to find orphaned index entries
CREATE OR REPLACE FUNCTION registry.find_orphaned_entries(tenant_uuid UUID DEFAULT NULL)
RETURNS TABLE(
    doc_id UUID,
    index_type TEXT,
    entry_count BIGINT
) AS $$
DECLARE
    effective_tenant_id UUID;
BEGIN
    effective_tenant_id := COALESCE(tenant_uuid, tenants.current_tenant_id());

    RETURN QUERY
    SELECT
        ie.doc_id,
        ie.index_type,
        COUNT(*) as entry_count
    FROM registry.index_entries ie
    LEFT JOIN registry.documents d ON ie.doc_id = d.doc_id AND ie.tenant_id = d.tenant_id
    WHERE ie.tenant_id = effective_tenant_id
      AND d.doc_id IS NULL
    GROUP BY ie.doc_id, ie.index_type
    ORDER BY entry_count DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to cleanup orphaned entries
CREATE OR REPLACE FUNCTION registry.cleanup_orphaned_entries(tenant_uuid UUID DEFAULT NULL)
RETURNS INTEGER AS $$
DECLARE
    effective_tenant_id UUID;
    deleted_count INTEGER;
BEGIN
    effective_tenant_id := COALESCE(tenant_uuid, tenants.current_tenant_id());

    DELETE FROM registry.index_entries ie
    WHERE ie.tenant_id = effective_tenant_id
      AND NOT EXISTS (
          SELECT 1 FROM registry.documents d
          WHERE d.doc_id = ie.doc_id AND d.tenant_id = ie.tenant_id
      );

    GET DIAGNOSTICS deleted_count = ROW_COUNT;

    -- Log the cleanup operation
    PERFORM tenants.log_operation(
        effective_tenant_id,
        'cleanup_orphaned_entries',
        jsonb_build_object('deleted_count', deleted_count)
    );

    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- ROW LEVEL SECURITY FOR INDEX ENTRIES
-- ============================================

-- Enable RLS on the new table
ALTER TABLE registry.index_entries ENABLE ROW LEVEL SECURITY;

-- Tenant isolation policy
CREATE POLICY tenant_isolation_registry_index_entries
    ON registry.index_entries
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

-- Admin bypass policy
CREATE POLICY admin_bypass_registry_index_entries
    ON registry.index_entries
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- ============================================
-- PERMISSIONS
-- ============================================

-- Grant usage on new functions
GRANT EXECUTE ON FUNCTION registry.get_index_statistics(UUID) TO PUBLIC;
GRANT EXECUTE ON FUNCTION registry.find_orphaned_entries(UUID) TO PUBLIC;

-- Admin-only functions
GRANT EXECUTE ON FUNCTION registry.cleanup_orphaned_entries(UUID) TO rag_lab_admin;

-- ============================================
-- MIGRATION TRACKING
-- ============================================

-- Record this migration
INSERT INTO migrations.schema_versions (version, description, checksum)
VALUES (3, 'Add index_entries table for document chunk tracking', 'index_entries_v3')
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- COMMENTS
-- ============================================

COMMENT ON TABLE registry.index_entries IS 'Tracks document chunks in various indexes for consistency management';
COMMENT ON FUNCTION registry.get_index_statistics(UUID) IS 'Returns statistics about index entries per tenant';
COMMENT ON FUNCTION registry.find_orphaned_entries(UUID) IS 'Finds index entries without corresponding documents';
COMMENT ON FUNCTION registry.cleanup_orphaned_entries(UUID) IS 'Removes orphaned index entries and logs the operation';
