-- Migration: 003_tenant_management_fixed.sql
-- Purpose: Enhance existing tenant tables for full tenant management
-- Created: 2025-01-07

-- Alter existing tenants table to add missing columns
ALTER TABLE tenants.tenants
ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true,
ADD COLUMN IF NOT EXISTS max_api_calls_per_day INTEGER DEFAULT 100000,
ADD COLUMN IF NOT EXISTS admin_email VARCHAR(255),
ADD COLUMN IF NOT EXISTS admin_name VARCHAR(255),
ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}';

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_tenants_name ON tenants.tenants(name);
CREATE INDEX IF NOT EXISTS idx_tenants_active ON tenants.tenants(is_active);
CREATE INDEX IF NOT EXISTS idx_tenants_settings ON tenants.tenants USING GIN(settings);

-- Create tenant API keys table
CREATE TABLE IF NOT EXISTS tenants.api_keys (
    key_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL UNIQUE, -- Store hashed API key
    key_prefix VARCHAR(10) NOT NULL, -- First few chars for identification
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ,
    is_active BOOLEAN DEFAULT true,

    -- Permissions and scopes
    scopes TEXT[] DEFAULT ARRAY['read', 'write'],

    -- Rate limiting
    rate_limit_per_minute INTEGER DEFAULT 100,
    rate_limit_per_day INTEGER DEFAULT 10000,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Create indexes
CREATE INDEX idx_api_keys_tenant ON tenants.api_keys(tenant_id);
CREATE INDEX idx_api_keys_prefix ON tenants.api_keys(key_prefix);
CREATE INDEX idx_api_keys_active ON tenants.api_keys(is_active);
CREATE INDEX idx_api_keys_expires ON tenants.api_keys(expires_at);

-- Create usage metrics table
CREATE TABLE IF NOT EXISTS tenants.usage_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    metric_date DATE NOT NULL DEFAULT CURRENT_DATE,

    -- Usage counters
    document_count INTEGER DEFAULT 0,
    storage_bytes BIGINT DEFAULT 0,
    api_calls INTEGER DEFAULT 0,
    vector_searches INTEGER DEFAULT 0,
    keyword_searches INTEGER DEFAULT 0,

    -- Performance metrics
    avg_search_latency_ms DECIMAL(10,2),
    avg_index_latency_ms DECIMAL(10,2),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Unique constraint for one entry per tenant per day
    UNIQUE(tenant_id, metric_date)
);

-- Create indexes
CREATE INDEX idx_usage_metrics_tenant_date ON tenants.usage_metrics(tenant_id, metric_date);
CREATE INDEX idx_usage_metrics_date ON tenants.usage_metrics(metric_date);

-- Create audit log table
CREATE TABLE IF NOT EXISTS tenants.audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    user_id VARCHAR(255),
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),

    -- Request details
    ip_address INET,
    user_agent TEXT,
    api_key_id UUID REFERENCES tenants.api_keys(key_id) ON DELETE SET NULL,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Additional data
    metadata JSONB DEFAULT '{}'
);

-- Create indexes
CREATE INDEX idx_audit_log_tenant ON tenants.audit_log(tenant_id);
CREATE INDEX idx_audit_log_action ON tenants.audit_log(action);
CREATE INDEX idx_audit_log_created ON tenants.audit_log(created_at);
CREATE INDEX idx_audit_log_api_key ON tenants.audit_log(api_key_id);

-- Add foreign key constraints to existing tables
DO $$
BEGIN
    -- Add tenant_id foreign key to documents if not exists
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'documents_tenant_id_fkey'
        AND table_schema = 'registry'
        AND table_name = 'documents'
    ) THEN
        ALTER TABLE registry.documents
        ADD CONSTRAINT documents_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;

    -- Similar for other tables
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'index_entries_tenant_id_fkey'
        AND table_schema = 'registry'
        AND table_name = 'index_entries'
    ) THEN
        ALTER TABLE registry.index_entries
        ADD CONSTRAINT index_entries_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;

    -- search.keyword_search
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'keyword_search_tenant_id_fkey'
        AND table_schema = 'search'
        AND table_name = 'keyword_search'
    ) THEN
        ALTER TABLE search.keyword_search
        ADD CONSTRAINT keyword_search_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;

    -- search.doc_metadata
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'doc_metadata_tenant_id_fkey'
        AND table_schema = 'search'
        AND table_name = 'doc_metadata'
    ) THEN
        ALTER TABLE search.doc_metadata
        ADD CONSTRAINT doc_metadata_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;

    -- jobs.queue
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'queue_tenant_id_fkey'
        AND table_schema = 'jobs'
        AND table_name = 'queue'
    ) THEN
        ALTER TABLE jobs.queue
        ADD CONSTRAINT queue_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;

    -- fingerprints.fingerprints
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fingerprints_tenant_id_fkey'
        AND table_schema = 'fingerprints'
        AND table_name = 'fingerprints'
    ) THEN
        ALTER TABLE fingerprints.fingerprints
        ADD CONSTRAINT fingerprints_tenant_id_fkey
        FOREIGN KEY (tenant_id) REFERENCES tenants.tenants(tenant_id);
    END IF;
END$$;

-- Grant usage on tenants schema to application role
GRANT USAGE ON SCHEMA tenants TO rag_app_role;
GRANT SELECT ON ALL TABLES IN SCHEMA tenants TO rag_app_role;
GRANT INSERT, UPDATE ON tenants.usage_metrics TO rag_app_role;
GRANT INSERT ON tenants.audit_log TO rag_app_role;

-- Comment on tables
COMMENT ON TABLE tenants.tenants IS 'Multi-tenant registry with resource limits and settings';
COMMENT ON TABLE tenants.api_keys IS 'API keys for tenant authentication and authorization';
COMMENT ON TABLE tenants.usage_metrics IS 'Daily usage metrics and statistics per tenant';
COMMENT ON TABLE tenants.audit_log IS 'Audit trail of all tenant actions';
