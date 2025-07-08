-- Migration: 004_enhanced_rls_policies.sql
-- Purpose: Implement comprehensive RLS policies with tenant management
-- Created: 2025-01-07

-- Enable RLS on all tables
ALTER TABLE registry.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE registry.index_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE search.keyword_search ENABLE ROW LEVEL SECURITY;
ALTER TABLE search.doc_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs.queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE fingerprints.fingerprints ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants.usage_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants.audit_log ENABLE ROW LEVEL SECURITY;

-- Drop existing policies if they exist (safe to run multiple times)
DROP POLICY IF EXISTS tenant_isolation ON registry.documents;
DROP POLICY IF EXISTS tenant_isolation ON registry.index_entries;
DROP POLICY IF EXISTS tenant_isolation ON search.keyword_search;
DROP POLICY IF EXISTS tenant_isolation ON search.doc_metadata;
DROP POLICY IF EXISTS tenant_isolation ON jobs.queue;
DROP POLICY IF EXISTS tenant_isolation ON fingerprints.fingerprints;

-- Registry policies
CREATE POLICY tenant_isolation_documents ON registry.documents
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY tenant_isolation_index_entries ON registry.index_entries
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Search policies
CREATE POLICY tenant_isolation_keyword_search ON search.keyword_search
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY tenant_isolation_doc_metadata ON search.doc_metadata
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Jobs policies
CREATE POLICY tenant_isolation_jobs ON jobs.queue
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Fingerprints policies
CREATE POLICY tenant_isolation_fingerprints ON fingerprints.fingerprints
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Tenant management policies
CREATE POLICY tenant_self_read ON tenants.tenants
    FOR SELECT
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY tenant_admin_write ON tenants.tenants
    FOR ALL
    USING (tenants.is_admin());

-- API keys policies
CREATE POLICY api_keys_tenant_isolation ON tenants.api_keys
    FOR SELECT
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY api_keys_admin_write ON tenants.api_keys
    FOR ALL
    USING (tenants.is_admin());

-- Usage metrics policies
CREATE POLICY usage_metrics_tenant_read ON tenants.usage_metrics
    FOR SELECT
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY usage_metrics_system_write ON tenants.usage_metrics
    FOR ALL
    USING (tenants.is_admin());

-- Audit log policies
CREATE POLICY audit_log_tenant_read ON tenants.audit_log
    FOR SELECT
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY audit_log_insert_all ON tenants.audit_log
    FOR INSERT
    WITH CHECK (true); -- Anyone can insert audit logs

-- Create helper function for safe tenant switching
CREATE OR REPLACE FUNCTION tenants.switch_tenant(
    p_tenant_name VARCHAR(255)
) RETURNS TABLE (
    tenant_id UUID,
    name VARCHAR(255),
    display_name VARCHAR(255),
    is_active BOOLEAN
) AS $$
DECLARE
    v_tenant_id UUID;
BEGIN
    -- Find tenant by name
    SELECT t.tenant_id INTO v_tenant_id
    FROM tenants.tenants t
    WHERE t.name = p_tenant_name AND t.is_active = true;

    IF v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'Tenant not found or inactive: %', p_tenant_name;
    END IF;

    -- Set current tenant
    PERFORM tenants.set_current_tenant(v_tenant_id);

    -- Return tenant info
    RETURN QUERY
    SELECT t.tenant_id, t.name, t.display_name, t.is_active
    FROM tenants.tenants t
    WHERE t.tenant_id = v_tenant_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to clear tenant context
CREATE OR REPLACE FUNCTION tenants.clear_tenant_context()
RETURNS void AS $$
BEGIN
    -- Reset tenant context
    PERFORM set_config('app.current_tenant', NULL, false);
    PERFORM set_config('app.is_admin', 'false', false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create view for current tenant info
CREATE OR REPLACE VIEW tenants.current_tenant_info AS
SELECT
    t.tenant_id,
    t.name,
    t.display_name,
    t.is_active,
    t.settings,
    t.max_documents,
    t.max_storage_gb,
    t.max_api_calls_per_day,
    COALESCE(
        (SELECT COUNT(*) FROM registry.documents d WHERE d.tenant_id = t.tenant_id),
        0
    ) as document_count,
    COALESCE(
        (SELECT SUM(um.storage_used_mb) / 1024.0
         FROM tenants.usage_metrics um
         WHERE um.tenant_id = t.tenant_id
         AND um.date = CURRENT_DATE),
        0
    ) as storage_used_gb
FROM tenants.tenants t
WHERE t.tenant_id = tenants.current_tenant_id();

-- Grant permissions on new functions and views
GRANT EXECUTE ON FUNCTION tenants.switch_tenant(VARCHAR) TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.clear_tenant_context() TO PUBLIC;
GRANT SELECT ON tenants.current_tenant_info TO PUBLIC;

-- Create index to support RLS performance
CREATE INDEX IF NOT EXISTS idx_registry_documents_tenant ON registry.documents(tenant_id);
CREATE INDEX IF NOT EXISTS idx_registry_index_entries_tenant ON registry.index_entries(tenant_id);
CREATE INDEX IF NOT EXISTS idx_search_keyword_tenant ON search.keyword_search(tenant_id);
CREATE INDEX IF NOT EXISTS idx_search_metadata_tenant ON search.doc_metadata(tenant_id);
CREATE INDEX IF NOT EXISTS idx_jobs_queue_tenant ON jobs.queue(tenant_id);
CREATE INDEX IF NOT EXISTS idx_fingerprints_tenant ON fingerprints.fingerprints(tenant_id);
