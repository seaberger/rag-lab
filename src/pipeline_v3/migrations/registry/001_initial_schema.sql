-- Migration: 001_initial_schema
-- Description: Initial schema for document registry

-- Documents table
CREATE TABLE IF NOT EXISTS documents (
    doc_id TEXT PRIMARY KEY,
    source TEXT UNIQUE NOT NULL,
    content_hash TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_time REAL NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    state TEXT NOT NULL,
    vector_indexed BOOLEAN NOT NULL DEFAULT 0,
    keyword_indexed BOOLEAN NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    metadata TEXT  -- JSON
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source);
CREATE INDEX IF NOT EXISTS idx_documents_state ON documents(state);
CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_updated_at ON documents(updated_at);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

-- Index consistency tracking table
CREATE TABLE IF NOT EXISTS index_consistency (
    doc_id TEXT PRIMARY KEY,
    vector_present BOOLEAN NOT NULL DEFAULT 0,
    keyword_present BOOLEAN NOT NULL DEFAULT 0,
    checked_at REAL NOT NULL,
    FOREIGN KEY (doc_id) REFERENCES documents(doc_id) ON DELETE CASCADE
);