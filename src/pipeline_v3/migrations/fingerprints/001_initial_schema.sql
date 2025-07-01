-- Migration: 001_initial_schema
-- Description: Initial schema for fingerprint tracking

-- Fingerprints table
CREATE TABLE IF NOT EXISTS fingerprints (
    source TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    size INTEGER NOT NULL,
    modified_time REAL NOT NULL,
    metadata_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_seen REAL NOT NULL,
    doc_id TEXT,
    processing_status TEXT DEFAULT 'unknown'
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_fingerprints_content_hash 
ON fingerprints(content_hash);

CREATE INDEX IF NOT EXISTS idx_fingerprints_last_seen 
ON fingerprints(last_seen);

CREATE INDEX IF NOT EXISTS idx_fingerprints_doc_id
ON fingerprints(doc_id);

CREATE INDEX IF NOT EXISTS idx_fingerprints_processing_status
ON fingerprints(processing_status);