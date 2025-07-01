-- Migration: 001_initial_schema
-- Description: Initial schema for job queue management

-- Jobs table
CREATE TABLE IF NOT EXISTS jobs (
    job_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    job_type TEXT NOT NULL,
    priority INTEGER NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    started_at REAL,
    completed_at REAL,
    status TEXT NOT NULL,
    progress REAL NOT NULL DEFAULT 0.0,
    worker_id TEXT,
    error_message TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    metadata TEXT,  -- JSON
    intermediate_state TEXT  -- JSON
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_priority ON jobs(priority DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_worker_id ON jobs(worker_id);
CREATE INDEX IF NOT EXISTS idx_jobs_source ON jobs(source);