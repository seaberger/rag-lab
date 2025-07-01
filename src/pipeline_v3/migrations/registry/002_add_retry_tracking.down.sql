-- Rollback: 002_add_retry_tracking
-- Description: Remove retry tracking columns

-- Drop indexes first
DROP INDEX IF EXISTS idx_documents_retry_count;
DROP INDEX IF EXISTS idx_documents_last_retry_at;

-- SQLite doesn't support DROP COLUMN directly, need to recreate table
-- This is a complex operation that requires careful handling

-- Create temporary table without the new columns
CREATE TABLE documents_temp AS 
SELECT 
    doc_id,
    source,
    content_hash,
    size,
    modified_time,
    created_at,
    updated_at,
    state,
    vector_indexed,
    keyword_indexed,
    chunk_count,
    error_count,
    last_error,
    metadata
FROM documents;

-- Drop original table
DROP TABLE documents;

-- Rename temp table
ALTER TABLE documents_temp RENAME TO documents;

-- Recreate all original indexes
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(state);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);