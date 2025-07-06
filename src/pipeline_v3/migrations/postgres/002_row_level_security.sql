-- PostgreSQL Row Level Security (RLS) Migration
-- This migration adds row-level security policies for proper multi-tenant isolation
-- ensuring that tenants can only access their own data

-- ============================================
-- ENABLE ROW LEVEL SECURITY
-- ============================================

-- Enable RLS on all main tables
ALTER TABLE registry.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE registry.index_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE search.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE search.doc_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs.queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE fingerprints.fingerprints ENABLE ROW LEVEL SECURITY;

-- ============================================
-- TENANT CONTEXT FUNCTIONS
-- ============================================

-- Function to get current tenant ID from session variable or application context
CREATE OR REPLACE FUNCTION tenants.current_tenant_id()
RETURNS UUID AS $$
DECLARE
    tenant_uuid UUID;
BEGIN
    -- Try to get tenant from session variable first
    tenant_uuid := current_setting('app.current_tenant_id', true)::UUID;

    -- If not set, default to the default tenant
    IF tenant_uuid IS NULL THEN
        tenant_uuid := '00000000-0000-0000-0000-000000000000'::UUID;
    END IF;

    RETURN tenant_uuid;
EXCEPTION
    WHEN OTHERS THEN
        -- Fallback to default tenant on any error
        RETURN '00000000-0000-0000-0000-000000000000'::UUID;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to set current tenant context
CREATE OR REPLACE FUNCTION tenants.set_current_tenant(tenant_uuid UUID)
RETURNS VOID AS $$
BEGIN
    -- Validate tenant exists
    IF NOT EXISTS (SELECT 1 FROM tenants.tenants WHERE tenant_id = tenant_uuid) THEN
        RAISE EXCEPTION 'Invalid tenant ID: %', tenant_uuid;
    END IF;

    -- Set session variable
    PERFORM set_config('app.current_tenant_id', tenant_uuid::TEXT, false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to clear tenant context (useful for admin operations)
CREATE OR REPLACE FUNCTION tenants.clear_tenant_context()
RETURNS VOID AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', NULL, false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- ROW LEVEL SECURITY POLICIES
-- ============================================

-- Registry Documents Policies
CREATE POLICY tenant_isolation_registry_documents
    ON registry.documents
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

-- Allow superuser and admin to bypass RLS for maintenance
CREATE POLICY admin_bypass_registry_documents
    ON registry.documents
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- Index Entries Policies (if the table exists)
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables
               WHERE table_schema = 'registry' AND table_name = 'index_entries') THEN
        EXECUTE 'CREATE POLICY tenant_isolation_registry_index_entries
                ON registry.index_entries
                FOR ALL
                TO PUBLIC
                USING (tenant_id = tenants.current_tenant_id())
                WITH CHECK (tenant_id = tenants.current_tenant_id())';

        EXECUTE 'CREATE POLICY admin_bypass_registry_index_entries
                ON registry.index_entries
                FOR ALL
                TO postgres
                USING (true)
                WITH CHECK (true)';
    END IF;
END $$;

-- Search Documents Policies
CREATE POLICY tenant_isolation_search_documents
    ON search.documents
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

CREATE POLICY admin_bypass_search_documents
    ON search.documents
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- Search Metadata Policies
CREATE POLICY tenant_isolation_search_metadata
    ON search.doc_metadata
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

CREATE POLICY admin_bypass_search_metadata
    ON search.doc_metadata
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- Jobs Queue Policies
CREATE POLICY tenant_isolation_jobs_queue
    ON jobs.queue
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

CREATE POLICY admin_bypass_jobs_queue
    ON jobs.queue
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- Fingerprints Policies
CREATE POLICY tenant_isolation_fingerprints
    ON fingerprints.fingerprints
    FOR ALL
    TO PUBLIC
    USING (tenant_id = tenants.current_tenant_id())
    WITH CHECK (tenant_id = tenants.current_tenant_id());

CREATE POLICY admin_bypass_fingerprints
    ON fingerprints.fingerprints
    FOR ALL
    TO postgres
    USING (true)
    WITH CHECK (true);

-- ============================================
-- TENANT MANAGEMENT FUNCTIONS
-- ============================================

-- Function to create a new tenant
CREATE OR REPLACE FUNCTION tenants.create_tenant(
    tenant_name TEXT,
    tenant_display_name TEXT DEFAULT NULL,
    max_docs INTEGER DEFAULT 10000,
    max_storage INTEGER DEFAULT 100
)
RETURNS UUID AS $$
DECLARE
    new_tenant_id UUID;
BEGIN
    -- Generate new tenant ID
    new_tenant_id := gen_random_uuid();

    -- Insert new tenant
    INSERT INTO tenants.tenants (
        tenant_id,
        name,
        display_name,
        max_documents,
        max_storage_gb
    ) VALUES (
        new_tenant_id,
        tenant_name,
        COALESCE(tenant_display_name, tenant_name),
        max_docs,
        max_storage
    );

    RETURN new_tenant_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get tenant information
CREATE OR REPLACE FUNCTION tenants.get_tenant_info(tenant_uuid UUID)
RETURNS TABLE(
    tenant_id UUID,
    name TEXT,
    display_name TEXT,
    status TEXT,
    max_documents INTEGER,
    max_storage_gb INTEGER,
    current_documents BIGINT,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.tenant_id,
        t.name,
        t.display_name,
        t.status,
        t.max_documents,
        t.max_storage_gb,
        COALESCE(doc_count.count, 0) as current_documents,
        t.created_at
    FROM tenants.tenants t
    LEFT JOIN (
        SELECT tenant_id, COUNT(*) as count
        FROM registry.documents
        WHERE tenant_id = tenant_uuid
        GROUP BY tenant_id
    ) doc_count ON t.tenant_id = doc_count.tenant_id
    WHERE t.tenant_id = tenant_uuid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to list all tenants (admin only)
CREATE OR REPLACE FUNCTION tenants.list_tenants()
RETURNS TABLE(
    tenant_id UUID,
    name TEXT,
    display_name TEXT,
    status TEXT,
    document_count BIGINT,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.tenant_id,
        t.name,
        t.display_name,
        t.status,
        COALESCE(doc_count.count, 0) as document_count,
        t.created_at
    FROM tenants.tenants t
    LEFT JOIN (
        SELECT tenant_id, COUNT(*) as count
        FROM registry.documents
        GROUP BY tenant_id
    ) doc_count ON t.tenant_id = doc_count.tenant_id
    ORDER BY t.created_at;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to disable a tenant (soft delete)
CREATE OR REPLACE FUNCTION tenants.disable_tenant(tenant_uuid UUID)
RETURNS BOOLEAN AS $$
BEGIN
    UPDATE tenants.tenants
    SET status = 'suspended',
        updated_at = NOW()
    WHERE tenant_id = tenant_uuid;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- ENHANCED SEARCH FUNCTIONS WITH TENANT ISOLATION
-- ============================================

-- Enhanced phrase search with automatic tenant isolation
CREATE OR REPLACE FUNCTION search.tenant_phrase_search(
    query_text TEXT,
    limit_count INTEGER DEFAULT 10,
    tenant_uuid UUID DEFAULT NULL
)
RETURNS TABLE(
    doc_id UUID,
    chunk_id TEXT,
    text TEXT,
    keywords TEXT,
    metadata JSONB,
    rank REAL
) AS $$
DECLARE
    effective_tenant_id UUID;
BEGIN
    -- Use provided tenant or current tenant context
    effective_tenant_id := COALESCE(tenant_uuid, tenants.current_tenant_id());

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
        d.tenant_id = effective_tenant_id AND
        d.search_vector @@ phraseto_tsquery('english', query_text)
    ORDER BY rank DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Enhanced job claiming with tenant context
CREATE OR REPLACE FUNCTION jobs.tenant_claim_next_job(
    worker TEXT,
    tenant_uuid UUID DEFAULT NULL
)
RETURNS jobs.queue AS $$
DECLARE
    job jobs.queue;
    effective_tenant_id UUID;
BEGIN
    -- Use provided tenant or current tenant context
    effective_tenant_id := COALESCE(tenant_uuid, tenants.current_tenant_id());

    SELECT * INTO job
    FROM jobs.queue
    WHERE
        status = 'PENDING' AND
        tenant_id = effective_tenant_id
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
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- AUDIT AND MONITORING
-- ============================================

-- Create audit log table for tenant operations
CREATE TABLE IF NOT EXISTS tenants.audit_log (
    id SERIAL PRIMARY KEY,
    tenant_id UUID,
    operation TEXT NOT NULL,
    details JSONB DEFAULT '{}'::jsonb,
    performed_by TEXT,
    performed_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_log_tenant ON tenants.audit_log(tenant_id);
CREATE INDEX idx_audit_log_performed_at ON tenants.audit_log(performed_at);

-- Function to log tenant operations
CREATE OR REPLACE FUNCTION tenants.log_operation(
    tenant_uuid UUID,
    operation TEXT,
    details JSONB DEFAULT '{}'::jsonb,
    performer TEXT DEFAULT NULL
)
RETURNS VOID AS $$
BEGIN
    INSERT INTO tenants.audit_log (tenant_id, operation, details, performed_by)
    VALUES (tenant_uuid, operation, details, COALESCE(performer, current_user));
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ============================================
-- PERMISSIONS
-- ============================================

-- Grant usage on tenant functions to application users
GRANT EXECUTE ON FUNCTION tenants.current_tenant_id() TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.set_current_tenant(UUID) TO PUBLIC;
GRANT EXECUTE ON FUNCTION search.tenant_phrase_search(TEXT, INTEGER, UUID) TO PUBLIC;
GRANT EXECUTE ON FUNCTION jobs.tenant_claim_next_job(TEXT, UUID) TO PUBLIC;

-- Grant tenant management functions to admin role (create if needed)
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'rag_lab_admin') THEN
        CREATE ROLE rag_lab_admin;
    END IF;
END $$;

GRANT EXECUTE ON FUNCTION tenants.create_tenant(TEXT, TEXT, INTEGER, INTEGER) TO rag_lab_admin;
GRANT EXECUTE ON FUNCTION tenants.get_tenant_info(UUID) TO rag_lab_admin;
GRANT EXECUTE ON FUNCTION tenants.list_tenants() TO rag_lab_admin;
GRANT EXECUTE ON FUNCTION tenants.disable_tenant(UUID) TO rag_lab_admin;
GRANT EXECUTE ON FUNCTION tenants.log_operation(UUID, TEXT, JSONB, TEXT) TO rag_lab_admin;

-- ============================================
-- MIGRATION TRACKING
-- ============================================

-- Record this migration
INSERT INTO migrations.schema_versions (version, description, checksum)
VALUES (2, 'Row Level Security and Multi-Tenant Isolation', 'rls_multi_tenant_v2')
ON CONFLICT (version) DO NOTHING;

-- ============================================
-- HELPFUL COMMENTS
-- ============================================

COMMENT ON FUNCTION tenants.current_tenant_id() IS 'Returns the current tenant ID from session context';
COMMENT ON FUNCTION tenants.set_current_tenant(UUID) IS 'Sets the current tenant context for the session';
COMMENT ON FUNCTION tenants.create_tenant(TEXT, TEXT, INTEGER, INTEGER) IS 'Creates a new tenant with specified quotas';
COMMENT ON FUNCTION search.tenant_phrase_search(TEXT, INTEGER, UUID) IS 'Performs phrase search with automatic tenant isolation';
COMMENT ON FUNCTION jobs.tenant_claim_next_job(TEXT, UUID) IS 'Claims next job with tenant isolation';

COMMENT ON TABLE tenants.audit_log IS 'Audit log for tenant operations and security monitoring';
