-- Fix ambiguous column reference in get_tenant_info function
-- The issue is that 'tenant_id' in the subquery could refer to either
-- the column in registry.documents or the function parameter

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
        SELECT d.tenant_id, COUNT(*) as count
        FROM registry.documents d
        WHERE d.tenant_id = tenant_uuid
        GROUP BY d.tenant_id
    ) doc_count ON t.tenant_id = doc_count.tenant_id
    WHERE t.tenant_id = tenant_uuid;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Also fix any other functions that might have similar issues
-- Check if there are similar issues in other tenant functions

-- Grant necessary permissions
GRANT EXECUTE ON FUNCTION tenants.get_tenant_info(UUID) TO rag_lab_admin;
