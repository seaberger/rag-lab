-- Migration: 001_initial_schema
-- Description: Initial schema for keyword search index

-- FTS5 virtual table for full-text search
CREATE VIRTUAL TABLE IF NOT EXISTS documents USING fts5(
    doc_id,
    chunk_id,
    text,
    keywords,
    metadata,
    tokenize='porter unicode61'
);

-- Metadata table for document info
CREATE TABLE IF NOT EXISTS doc_metadata (
    doc_id TEXT PRIMARY KEY,
    source TEXT,
    pairs TEXT,  -- JSON array
    chunk_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create indexes for metadata table
CREATE INDEX IF NOT EXISTS idx_doc_metadata_source ON doc_metadata(source);
CREATE INDEX IF NOT EXISTS idx_doc_metadata_created_at ON doc_metadata(created_at);
