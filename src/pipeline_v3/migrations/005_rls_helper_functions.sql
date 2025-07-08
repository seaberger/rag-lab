-- Migration: 005_rls_helper_functions.sql
-- Purpose: Create helper functions for RLS that were missing
-- Created: 2025-01-07

-- Create current_tenant_id function
CREATE OR REPLACE FUNCTION tenants.current_tenant_id()
RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.current_tenant_id', true), '')::UUID;
END;
$$ LANGUAGE plpgsql STABLE;

-- Create set_current_tenant function
CREATE OR REPLACE FUNCTION tenants.set_current_tenant(tenant_id UUID)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.current_tenant_id', tenant_id::text, false);
END;
$$ LANGUAGE plpgsql;

-- Create is_admin function
CREATE OR REPLACE FUNCTION tenants.is_admin()
RETURNS boolean AS $$
BEGIN
    RETURN COALESCE(current_setting('app.is_admin', true)::boolean, false);
END;
$$ LANGUAGE plpgsql STABLE;

-- Create set_admin_mode function
CREATE OR REPLACE FUNCTION tenants.set_admin_mode(is_admin boolean)
RETURNS void AS $$
BEGIN
    PERFORM set_config('app.is_admin', is_admin::text, false);
END;
$$ LANGUAGE plpgsql;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION tenants.current_tenant_id() TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.set_current_tenant(UUID) TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.is_admin() TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.set_admin_mode(boolean) TO rag_user;

-- Now create the RLS policies that depend on these functions
-- Documents table
CREATE POLICY tenant_isolation_documents ON registry.documents
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Index entries table
CREATE POLICY tenant_isolation_index_entries ON registry.index_entries
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Keyword search table
CREATE POLICY tenant_isolation_keyword_search ON search.keyword_search
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Document metadata table
CREATE POLICY tenant_isolation_doc_metadata ON search.doc_metadata
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Jobs queue table
CREATE POLICY tenant_isolation_jobs ON jobs.queue
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Fingerprints table
CREATE POLICY tenant_isolation_fingerprints ON fingerprints.fingerprints
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Tenants table (read-only for tenants, full access for admins)
CREATE POLICY tenant_self_read ON tenants.tenants
    FOR SELECT
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

CREATE POLICY tenant_admin_write ON tenants.tenants
    FOR ALL
    USING (tenants.is_admin());

-- API keys table
CREATE POLICY tenant_isolation_api_keys ON tenants.api_keys
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Usage metrics table
CREATE POLICY tenant_isolation_usage_metrics ON tenants.usage_metrics
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Audit log table
CREATE POLICY tenant_isolation_audit_log ON tenants.audit_log
    FOR ALL
    USING (tenant_id = tenants.current_tenant_id() OR tenants.is_admin());

-- Create helper view for current tenant info
CREATE OR REPLACE VIEW tenants.current_tenant_info AS
SELECT
    t.*,
    COALESCE(
        (SELECT COUNT(*) FROM registry.documents d WHERE d.tenant_id = t.tenant_id),
        0
    ) as current_document_count,
    COALESCE(
        (SELECT SUM(file_size) / 1024.0 / 1024.0 / 1024.0
         FROM registry.documents d
         WHERE d.tenant_id = t.tenant_id),
        0
    ) as current_storage_gb
FROM tenants.tenants t
WHERE t.tenant_id = tenants.current_tenant_id();

-- Grant access to the view
GRANT SELECT ON tenants.current_tenant_info TO PUBLIC;

-- Add comments
COMMENT ON FUNCTION tenants.current_tenant_id() IS 'Returns the current tenant ID from session context';
COMMENT ON FUNCTION tenants.set_current_tenant(UUID) IS 'Sets the current tenant ID in session context';
COMMENT ON FUNCTION tenants.is_admin() IS 'Returns true if current session is in admin mode';
COMMENT ON FUNCTION tenants.set_admin_mode(boolean) IS 'Enables or disables admin mode for current session';
