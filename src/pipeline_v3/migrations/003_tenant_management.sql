-- Migration: 003_tenant_management.sql
-- Purpose: Create tenant management tables and enhance RLS
-- Created: 2025-01-07

-- Create tenants schema if not exists
CREATE SCHEMA IF NOT EXISTS tenants;

-- Create tenants table
CREATE TABLE IF NOT EXISTS tenants.tenants (
    tenant_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    display_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true,

    -- Settings and configuration
    settings JSONB DEFAULT '{}',

    -- Resource limits
    max_documents INTEGER DEFAULT 10000,
    max_storage_gb INTEGER DEFAULT 100,
    max_api_calls_per_day INTEGER DEFAULT 100000,

    -- Contact information
    admin_email VARCHAR(255),
    admin_name VARCHAR(255),

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Create indexes
CREATE INDEX idx_tenants_name ON tenants.tenants(name);
CREATE INDEX idx_tenants_active ON tenants.tenants(is_active);
CREATE INDEX idx_tenants_settings ON tenants.tenants USING GIN(settings);

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
    rate_limit_per_hour INTEGER DEFAULT 1000,

    -- Usage tracking
    usage_count BIGINT DEFAULT 0,

    -- Metadata
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for API keys
CREATE INDEX idx_api_keys_tenant ON tenants.api_keys(tenant_id);
CREATE INDEX idx_api_keys_hash ON tenants.api_keys(key_hash);
CREATE INDEX idx_api_keys_active ON tenants.api_keys(is_active, expires_at);

-- Create tenant usage tracking table
CREATE TABLE IF NOT EXISTS tenants.usage_metrics (
    metric_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    date DATE NOT NULL,

    -- Document metrics
    documents_processed INTEGER DEFAULT 0,
    documents_total INTEGER DEFAULT 0,
    storage_used_mb BIGINT DEFAULT 0,

    -- API metrics
    api_calls INTEGER DEFAULT 0,
    search_queries INTEGER DEFAULT 0,

    -- Performance metrics
    avg_processing_time_ms INTEGER,
    avg_search_time_ms INTEGER,

    -- Constraints
    UNIQUE(tenant_id, date)
);

-- Create index for usage queries
CREATE INDEX idx_usage_metrics_tenant_date ON tenants.usage_metrics(tenant_id, date DESC);

-- Create audit log table
CREATE TABLE IF NOT EXISTS tenants.audit_log (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants.tenants(tenant_id) ON DELETE CASCADE,
    timestamp TIMESTAMPTZ DEFAULT NOW(),

    -- Action details
    action VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50),
    resource_id VARCHAR(255),

    -- User/API information
    api_key_id UUID REFERENCES tenants.api_keys(key_id),
    ip_address INET,
    user_agent TEXT,

    -- Results
    status VARCHAR(20) NOT NULL, -- success, failure, error
    error_message TEXT,

    -- Additional context
    metadata JSONB DEFAULT '{}'
);

-- Create indexes for audit queries
CREATE INDEX idx_audit_log_tenant_time ON tenants.audit_log(tenant_id, timestamp DESC);
CREATE INDEX idx_audit_log_action ON tenants.audit_log(action, timestamp DESC);
CREATE INDEX idx_audit_log_resource ON tenants.audit_log(resource_type, resource_id);

-- Add foreign key constraints to existing tables
-- This assumes tables exist from previous migrations

-- Update registry.documents
ALTER TABLE registry.documents
    ADD CONSTRAINT fk_documents_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

-- Update registry.index_entries
ALTER TABLE registry.index_entries
    ADD CONSTRAINT fk_index_entries_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

-- Update search tables
ALTER TABLE search.keyword_search
    ADD CONSTRAINT fk_keyword_search_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

ALTER TABLE search.doc_metadata
    ADD CONSTRAINT fk_doc_metadata_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

-- Update jobs.queue
ALTER TABLE jobs.queue
    ADD CONSTRAINT fk_jobs_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

-- Update fingerprints.fingerprints
ALTER TABLE fingerprints.fingerprints
    ADD CONSTRAINT fk_fingerprints_tenant
    FOREIGN KEY (tenant_id)
    REFERENCES tenants.tenants(tenant_id);

-- Create or replace tenant context functions
CREATE OR REPLACE FUNCTION tenants.current_tenant_id()
RETURNS UUID AS $$
BEGIN
    -- Try to get tenant ID from config
    RETURN current_setting('app.current_tenant', true)::UUID;
EXCEPTION
    WHEN OTHERS THEN
        -- Return NULL if not set
        RETURN NULL;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE FUNCTION tenants.set_current_tenant(tenant_uuid UUID)
RETURNS void AS $$
BEGIN
    -- Verify tenant exists and is active
    IF NOT EXISTS (
        SELECT 1 FROM tenants.tenants
        WHERE tenant_id = tenant_uuid AND is_active = true
    ) THEN
        RAISE EXCEPTION 'Invalid or inactive tenant: %', tenant_uuid;
    END IF;

    -- Set the current tenant
    PERFORM set_config('app.current_tenant', tenant_uuid::text, false);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Create function to check if current user is admin
CREATE OR REPLACE FUNCTION tenants.is_admin()
RETURNS BOOLEAN AS $$
BEGIN
    -- Check if current role is admin
    RETURN current_setting('app.is_admin', true)::boolean;
EXCEPTION
    WHEN OTHERS THEN
        RETURN false;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Insert default tenant for development
INSERT INTO tenants.tenants (
    tenant_id,
    name,
    display_name,
    admin_email,
    settings
) VALUES (
    '00000000-0000-0000-0000-000000000000'::UUID,
    'default',
    'Default Development Tenant',
    'admin@localhost',
    '{"environment": "development"}'::JSONB
) ON CONFLICT (tenant_id) DO NOTHING;

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION tenants.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Add updated_at triggers
CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants.tenants
    FOR EACH ROW
    EXECUTE FUNCTION tenants.update_updated_at_column();

-- Grant necessary permissions
GRANT USAGE ON SCHEMA tenants TO PUBLIC;
GRANT SELECT ON tenants.tenants TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.current_tenant_id() TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.set_current_tenant(UUID) TO PUBLIC;
GRANT EXECUTE ON FUNCTION tenants.is_admin() TO PUBLIC;
