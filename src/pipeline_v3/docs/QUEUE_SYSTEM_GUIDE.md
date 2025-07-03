# Queue System Comprehensive Guide

## Overview

The Pipeline v3 Queue System is a production-grade, asynchronous document processing framework designed to handle large-scale batch operations reliably. It provides job persistence, automatic retry logic, and graceful failure handling - essential for processing hundreds or thousands of documents in enterprise environments.

## Why Use the Queue System?

### Critical: Shell Timeout Limitations ⚠️
**Direct CLI commands timeout after 2 minutes** due to shell limitations. Since PDF processing with OpenAI Vision API takes approximately 30-45 seconds per page:

- **Small PDFs (1-3 pages)**: Direct CLI is acceptable
- **Large PDFs (>5 pages)**: Queue system required OR use timeout workaround
- **Multiple PDFs**: Queue system strongly recommended
- **Production workloads**: Always use queue system

#### Timeout Workaround for Direct CLI
For situations where you need to process larger documents without using the queue:

```bash
# Extend timeout to 10 minutes (600 seconds)
uv run python -m src.pipeline_v3.cli_main add large_document.pdf --timeout 600

# Or use specific page ranges to reduce processing time
uv run python -m src.pipeline_v3.cli_main add large_document.pdf --pages 1-10
```

**Note**: The `--timeout` parameter extends the Bash command timeout, not the internal Python timeouts. This is useful for ad-hoc processing but the queue system remains the recommended approach for production workloads.

### Benefits of Queue Processing
1. **No timeout limitations** - Process for hours or days
2. **Job persistence** - Survives system restarts
3. **Automatic retries** - Handles transient failures
4. **Progress tracking** - Monitor long-running operations
5. **Resource management** - Control concurrent processing
6. **Error recovery** - Failed jobs can be retried

## Architecture

### Core Components

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────┐
│   CLI/API       │────▶│ Job Manager  │────▶│  Workers    │
│  (Submit Jobs)  │     │  (SQLite DB) │     │ (Processing)│
└─────────────────┘     └──────────────┘     └─────────────┘
                               │                     │
                               ▼                     ▼
                        ┌──────────────┐     ┌─────────────┐
                        │ Job Storage  │     │  Pipeline   │
                        │   (Persist)  │     │  (Execute)  │
                        └──────────────┘     └─────────────┘
```

### Job Lifecycle

```
NEW ──▶ PENDING ──▶ PROCESSING ──▶ COMPLETED
            │            │
            │            └────▶ FAILED ──▶ RETRYING
            │                      │
            └──────────────────────┘
```

### Job States Explained

| State | Description | Next States |
|-------|-------------|-------------|
| **NEW** | Job created but not queued | PENDING |
| **PENDING** | Queued and waiting for worker | PROCESSING |
| **PROCESSING** | Currently being processed | COMPLETED, FAILED |
| **COMPLETED** | Successfully finished | - |
| **FAILED** | Processing failed | RETRYING, FAILED (terminal) |
| **RETRYING** | Waiting for retry attempt | PROCESSING |

## Basic Usage

### Starting the Queue

```bash
# Start with default settings (4 workers)
uv run python -m src.pipeline_v3.cli_main queue start

# Start with custom worker count
uv run python -m src.pipeline_v3.cli_main queue start --workers 8

# Start in foreground (for debugging)
uv run python -m src.pipeline_v3.cli_main queue start --foreground
```

### Submitting Jobs

When you use the `add` command with multiple files or large documents, jobs are automatically queued:

```bash
# Queue single large document
uv run python -m src.pipeline_v3.cli_main add large_catalog.pdf --mode datasheet

# Queue multiple documents
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf" --with-keywords

# Queue with specific worker allocation
uv run python -m src.pipeline_v3.cli_main add "datasheets/*.pdf" --workers 6
```

### Monitoring Queue Status

```bash
# Basic status
uv run python -m src.pipeline_v3.cli_main queue status

# Detailed status with job breakdown
uv run python -m src.pipeline_v3.cli_main queue status --detailed

# JSON output for monitoring systems
uv run python -m src.pipeline_v3.cli_main queue status --json
```

### Managing the Queue

```bash
# Stop queue gracefully (waits for current jobs)
uv run python -m src.pipeline_v3.cli_main queue stop --wait

# Stop queue immediately
uv run python -m src.pipeline_v3.cli_main queue stop

# Clear all pending jobs
uv run python -m src.pipeline_v3.cli_main queue clear --confirm

# Retry failed jobs
uv run python -m src.pipeline_v3.cli_main queue retry-failed
```

## Advanced Configuration

### Worker Configuration

Workers are the parallel processors that handle jobs. Configure based on your system:

```yaml
# config.yaml
queue:
  max_workers: 4           # Number of parallel workers
  batch_size: 10          # Jobs fetched per worker cycle
  poll_interval: 2.0      # Seconds between job checks
  job_timeout: 3600       # Maximum seconds per job (1 hour)
  retry_attempts: 3       # Retries for failed jobs
  retry_delay: 60         # Seconds between retries
```

#### Optimal Worker Count

| System Type | RAM | CPU Cores | Recommended Workers |
|------------|-----|-----------|-------------------|
| Development | 8GB | 4 | 2-3 |
| Standard | 16GB | 8 | 4-6 |
| High-End | 32GB | 16 | 8-12 |
| Server | 64GB+ | 32+ | 16-24 |

**Note**: Each worker can consume 1-2GB RAM when processing large PDFs.

### Performance Tuning

#### For Throughput (Many Small Documents)
```yaml
queue:
  max_workers: 8          # More workers
  batch_size: 20         # Larger batches
  job_timeout: 600       # Shorter timeout
```

#### For Large Documents
```yaml
queue:
  max_workers: 2          # Fewer workers (memory constraints)
  batch_size: 5          # Smaller batches
  job_timeout: 7200      # Longer timeout (2 hours)
```

#### For Mixed Workloads
```yaml
queue:
  max_workers: 4          # Balanced
  batch_size: 10         # Default
  job_timeout: 3600      # 1 hour
  adaptive_timeout: true  # Adjust based on document size
```

## Production Deployment

### System Requirements

- **Persistent Storage**: Queue database must be on persistent storage
- **Memory**: 2GB base + 1-2GB per worker
- **CPU**: 1 core per 2 workers recommended
- **Disk**: Fast SSD for cache and temporary files

### Deployment Checklist

1. **Configure Queue Settings**
   ```bash
   uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 8
   uv run python -m src.pipeline_v3.cli_main config set queue.job_timeout 7200
   ```

2. **Set Up Monitoring**
   ```bash
   # Create monitoring script
   #!/bin/bash
   while true; do
     uv run python -m src.pipeline_v3.cli_main queue status --json > queue_status.json
     sleep 60
   done
   ```

3. **Configure Logging**
   ```yaml
   logging:
     level: INFO
     file: pipeline_queue.log
     max_size: 100MB
     retention: 7
   ```

4. **Set Up Auto-Start**
   ```bash
   # systemd service example
   [Unit]
   Description=Pipeline v3 Queue Service
   After=network.target

   [Service]
   Type=simple
   User=pipeline
   WorkingDirectory=/path/to/rag_lab
   ExecStart=/usr/bin/uv run python -m src.pipeline_v3.cli_main queue start
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

### Handling Failures

#### Automatic Recovery
The queue system automatically handles:
- **Transient API failures**: Retried with exponential backoff
- **Worker crashes**: Jobs returned to queue
- **System restarts**: Jobs persist in SQLite database

#### Manual Intervention
For persistent failures:

```bash
# View failed jobs
uv run python -m src.pipeline_v3.cli_main queue status --failed

# Retry specific job
uv run python -m src.pipeline_v3.cli_main queue retry <job_id>

# Clear failed jobs
uv run python -m src.pipeline_v3.cli_main queue clear-failed --confirm
```

## Common Patterns

### Pattern 1: Batch Import
```bash
# Start queue
uv run python -m src.pipeline_v3.cli_main queue start --workers 6

# Submit all PDFs
uv run python -m src.pipeline_v3.cli_main add "/imports/2024/*.pdf" --mode auto

# Monitor progress
watch -n 5 'uv run python -m src.pipeline_v3.cli_main queue status'
```

### Pattern 2: Continuous Processing
```bash
# Set up watch folder
while true; do
  for file in /watch-folder/*.pdf; do
    if [ -f "$file" ]; then
      uv run python -m src.pipeline_v3.cli_main add "$file"
      mv "$file" /processed/
    fi
  done
  sleep 10
done
```

### Pattern 3: Scheduled Batch
```bash
# Cron job for nightly processing
0 2 * * * cd /path/to/rag_lab && uv run python -m src.pipeline_v3.cli_main add "/daily-docs/*.pdf"
```

## Troubleshooting

### Queue Won't Start
```bash
# Check if already running
ps aux | grep "queue start"

# Check lock file
ls -la jobs_v3.db-journal

# Force cleanup
uv run python -m src.pipeline_v3.cli_main queue cleanup
```

### Jobs Stuck in PROCESSING
```bash
# View stuck jobs
uv run python -m src.pipeline_v3.cli_main queue status --processing

# Force retry
uv run python -m src.pipeline_v3.cli_main queue reset-stuck

# Check worker health
uv run python -m src.pipeline_v3.cli_main queue health
```

### High Memory Usage
```bash
# Reduce worker count
uv run python -m src.pipeline_v3.cli_main queue stop
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 2
uv run python -m src.pipeline_v3.cli_main queue start
```

### Performance Issues

1. **Check System Resources**
   ```bash
   top -n 1
   df -h
   free -m
   ```

2. **Analyze Queue Metrics**
   ```bash
   uv run python -m src.pipeline_v3.cli_main queue metrics
   ```

3. **Review Logs**
   ```bash
   tail -f pipeline_queue.log | grep ERROR
   ```

## Best Practices

### DO ✅
- Always use queue for production workloads
- Monitor queue status regularly
- Configure workers based on system resources
- Test with small batches first
- Keep queue database on fast storage
- Set up proper logging and monitoring

### DON'T ❌
- Don't use direct CLI for large batches
- Don't set workers higher than CPU cores
- Don't ignore failed jobs
- Don't stop queue during processing
- Don't delete queue database without backup
- Don't process without monitoring

## Queue Metrics and Monitoring

### Key Metrics to Track

| Metric | Description | Alert Threshold |
|--------|-------------|----------------|
| Queue Depth | Pending jobs | > 1000 |
| Processing Rate | Jobs/minute | < 1 |
| Failure Rate | Failed/Total | > 5% |
| Worker Utilization | Active/Total | < 50% |
| Average Job Time | Seconds | > 600 |

### Monitoring Commands

```bash
# Real-time metrics
uv run python -m src.pipeline_v3.cli_main queue metrics --watch

# Export metrics
uv run python -m src.pipeline_v3.cli_main queue metrics --export metrics.csv

# Health check endpoint
curl http://localhost:8080/queue/health
```

## Integration Examples

### Python Script Integration
```python
from src.pipeline_v3.job_queue.manager import JobQueueManager

# Submit jobs programmatically
queue = JobQueueManager()
job_id = queue.submit_job("add", {"path": "document.pdf", "mode": "auto"})
print(f"Submitted job: {job_id}")

# Check status
status = queue.get_job_status(job_id)
print(f"Job status: {status}")
```

### REST API Integration
```bash
# Submit via API
curl -X POST http://localhost:8080/api/queue/jobs \
  -H "Content-Type: application/json" \
  -d '{"type": "add", "params": {"path": "doc.pdf"}}'

# Check status
curl http://localhost:8080/api/queue/status
```

## Appendix: Queue Database Schema

```sql
-- jobs_v3.db schema
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    job_type TEXT NOT NULL,
    params TEXT NOT NULL,  -- JSON
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error TEXT,
    retry_count INTEGER DEFAULT 0,
    metadata TEXT  -- JSON
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created ON jobs(created_at);
```

---

For more information:
- [BATCH_PROCESSING_GUIDE.md](./BATCH_PROCESSING_GUIDE.md) - Batch processing patterns
- [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) - Production setup
- [USER_MANUAL.md](../USER_MANUAL.md) - General usage
