-- Migration: 002_add_retry_tracking
-- Description: Add retry tracking columns for better error recovery

-- Add retry tracking columns
ALTER TABLE documents ADD COLUMN retry_count INTEGER DEFAULT 0;
ALTER TABLE documents ADD COLUMN last_retry_at REAL;
ALTER TABLE documents ADD COLUMN retry_strategy TEXT;

-- Create index for retry queries
CREATE INDEX IF NOT EXISTS idx_documents_retry_count ON documents(retry_count);
CREATE INDEX IF NOT EXISTS idx_documents_last_retry_at ON documents(last_retry_at);