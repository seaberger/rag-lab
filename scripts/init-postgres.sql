-- Initial PostgreSQL setup for RAG Lab
-- This file is automatically run when the PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- Grant all privileges to rag_user on the rag_lab database
GRANT ALL PRIVILEGES ON DATABASE rag_lab TO rag_user;

-- Create application role for row-level security (if needed)
DO $$
BEGIN
    CREATE ROLE rag_app_role;
EXCEPTION WHEN duplicate_object THEN
    RAISE NOTICE 'Role rag_app_role already exists';
END $$;

-- Grant connection privilege to rag_app_role
GRANT CONNECT ON DATABASE rag_lab TO rag_app_role;
