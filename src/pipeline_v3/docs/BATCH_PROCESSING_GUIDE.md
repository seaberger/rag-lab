# Batch Processing Best Practices

## Overview

This guide provides best practices for processing multiple documents efficiently with Pipeline v3. Whether you're importing hundreds of datasheets or continuously processing incoming documents, following these patterns will ensure reliable, scalable operations.

## Critical: Understanding Processing Times ⚠️

### Processing Time Realities
- **PDF Page Processing**: ~30-45 seconds per page with OpenAI Vision API
- **Shell Command Timeout**: 2 minutes for any CLI command
- **Math**: You can only process ~3-4 pages via direct CLI before timeout

### When to Use Each Approach

| Scenario | Direct CLI | Queue System | Reason |
|----------|------------|--------------|---------|
| Single 2-page PDF | ✅ Use | Optional | Completes in ~60-90 seconds |
| Single 10-page PDF | ❌ Don't | ✅ Use | Would take ~5-7 minutes |
| 5 PDFs (any size) | ❌ Don't | ✅ Use | Sequential processing exceeds timeout |
| 100+ PDFs | ❌ Never | ✅ Always | Hours of processing time |
| Production workload | ❌ Never | ✅ Always | Reliability and monitoring required |

## Quick Decision Tree

```
Is it a single PDF?
├─ Yes → How many pages?
│  ├─ 1-3 pages → Direct CLI is OK
│  └─ 4+ pages → Use Queue
└─ No (multiple PDFs) → Always use Queue
```

## Batch Processing Patterns

### Pattern 1: One-Time Bulk Import

**Scenario**: Import 500 historical datasheets

```bash
# Step 1: Start queue with appropriate workers
uv run python -m src.pipeline_v3.cli_main queue start --workers 8

# Step 2: Submit all documents
uv run python -m src.pipeline_v3.cli_main add "datasheets/*.pdf" \
  --mode datasheet \
  --with-keywords \
  --metadata source=bulk_import date=2024-01

# Step 3: Monitor progress
watch -n 30 'uv run python -m src.pipeline_v3.cli_main queue status --detailed'

# Step 4: Check completion
uv run python -m src.pipeline_v3.cli_main queue status --completed > import_results.log
```

### Pattern 2: Daily Batch Processing

**Scenario**: Process new documents each morning

```bash
#!/bin/bash
# daily_import.sh

# Ensure queue is running
uv run python -m src.pipeline_v3.cli_main queue start --workers 4

# Process new documents
IMPORT_DIR="/mnt/shared/daily_docs"
PROCESSED_DIR="/mnt/shared/processed"

# Add documents with date metadata
TODAY=$(date +%Y-%m-%d)
uv run python -m src.pipeline_v3.cli_main add "$IMPORT_DIR/*.pdf" \
  --metadata import_date=$TODAY \
  --mode auto

# Wait for completion (with timeout)
TIMEOUT=7200  # 2 hours
START_TIME=$(date +%s)

while true; do
  PENDING=$(uv run python -m src.pipeline_v3.cli_main queue status --json | jq '.pending')
  if [ "$PENDING" -eq 0 ]; then
    echo "Batch processing completed"
    break
  fi
  
  ELAPSED=$(($(date +%s) - START_TIME))
  if [ $ELAPSED -gt $TIMEOUT ]; then
    echo "Timeout reached, check queue status"
    exit 1
  fi
  
  sleep 60
done

# Move processed files
mv "$IMPORT_DIR"/*.pdf "$PROCESSED_DIR/"
```

### Pattern 3: Continuous Processing

**Scenario**: Process documents as they arrive

```python
#!/usr/bin/env python
# continuous_processor.py

import time
import os
from pathlib import Path
from src.pipeline_v3.cli.management import process_document

WATCH_DIR = Path("/watch/incoming")
PROCESSED_DIR = Path("/watch/processed")
ERROR_DIR = Path("/watch/errors")

def process_new_documents():
    """Process any new PDFs in the watch directory."""
    for pdf_file in WATCH_DIR.glob("*.pdf"):
        try:
            # Submit to queue
            result = process_document(
                str(pdf_file),
                mode="auto",
                with_keywords=True,
                metadata={"source": "auto_import"}
            )
            
            # Move to processed
            pdf_file.rename(PROCESSED_DIR / pdf_file.name)
            print(f"Processed: {pdf_file.name}")
            
        except Exception as e:
            # Move to error directory
            pdf_file.rename(ERROR_DIR / pdf_file.name)
            print(f"Error processing {pdf_file.name}: {e}")

# Ensure queue is running
os.system("uv run python -m src.pipeline_v3.cli_main queue start --workers 4")

# Watch and process
while True:
    process_new_documents()
    time.sleep(30)  # Check every 30 seconds
```

### Pattern 4: Prioritized Batch Processing

**Scenario**: Process urgent documents first

```bash
# High priority documents
uv run python -m src.pipeline_v3.cli_main add "urgent/*.pdf" \
  --metadata priority=high \
  --workers 8

# Normal priority documents  
uv run python -m src.pipeline_v3.cli_main add "standard/*.pdf" \
  --metadata priority=normal \
  --workers 4

# Low priority/archival
uv run python -m src.pipeline_v3.cli_main add "archive/*.pdf" \
  --metadata priority=low \
  --workers 2
```

## Performance Optimization

### Optimal Worker Configuration

#### Calculate Your Worker Count

```
Optimal Workers = MIN(
  Available CPU Cores - 2,
  Available RAM (GB) / 2,
  Network Bandwidth (Mbps) / 10
)
```

#### Examples by System

| System | CPU | RAM | Network | Optimal Workers | Reasoning |
|--------|-----|-----|---------|----------------|-----------|
| Laptop | 8 cores | 16GB | 100Mbps | 6 | CPU limited |
| Workstation | 16 cores | 32GB | 1Gbps | 14 | CPU limited |
| VM (small) | 4 cores | 8GB | 100Mbps | 2 | CPU limited |
| VM (large) | 32 cores | 64GB | 10Gbps | 30 | Balanced |

### Memory Management

Each worker requires:
- **Base**: 500MB for Python and libraries
- **Per PDF page**: 50-100MB during processing
- **Safety margin**: 20% headroom

```bash
# Calculate max workers based on memory
MAX_WORKERS = (TOTAL_RAM_GB * 0.8) / 2

# Example: 16GB system
# MAX_WORKERS = (16 * 0.8) / 2 = 6.4 → 6 workers
```

### Network Considerations

API calls to OpenAI require bandwidth:
- **Upload**: ~1-2MB per PDF page (base64 encoded)
- **Download**: ~10-50KB per page (text response)
- **Concurrent calls**: Can saturate slow connections

```bash
# Test your effective bandwidth
uv run python -m src.pipeline_v3.cli_main test-bandwidth

# Adjust workers based on results
# If bandwidth < 50Mbps: max 4 workers
# If bandwidth < 10Mbps: max 2 workers
```

## Error Handling Strategies

### Automatic Retry Configuration

```yaml
# config.yaml
queue:
  retry_attempts: 3          # Number of retries
  retry_delay: 60           # Initial delay (seconds)
  retry_backoff: 2.0        # Exponential backoff multiplier
  retry_max_delay: 3600     # Maximum delay between retries
```

### Handling Different Failure Types

| Error Type | Automatic Action | Manual Response |
|------------|-----------------|-----------------|
| API Timeout | Retry with longer timeout | Reduce page count per request |
| Rate Limit | Backoff and retry | Reduce worker count |
| Network Error | Retry immediately | Check connectivity |
| Invalid PDF | Mark as failed | Review and fix document |
| Out of Memory | Retry with fewer workers | Increase RAM or reduce workers |

### Failed Job Recovery

```bash
# View all failed jobs with reasons
uv run python -m src.pipeline_v3.cli_main queue failed --detailed

# Retry all failed jobs
uv run python -m src.pipeline_v3.cli_main queue retry-failed

# Retry specific job with modifications
uv run python -m src.pipeline_v3.cli_main queue retry <job_id> \
  --override-params '{"timeout_per_page": 60}'

# Export failed jobs for analysis
uv run python -m src.pipeline_v3.cli_main queue export-failed > failed_jobs.csv
```

## Monitoring and Alerting

### Real-Time Monitoring Dashboard

```bash
#!/bin/bash
# monitor_queue.sh

while true; do
  clear
  echo "=== Pipeline v3 Queue Monitor ==="
  echo "Time: $(date)"
  echo ""
  
  # Get queue status
  STATUS=$(uv run python -m src.pipeline_v3.cli_main queue status --json)
  
  # Parse and display
  echo "Active Workers: $(echo $STATUS | jq '.active_workers')"
  echo "Pending Jobs: $(echo $STATUS | jq '.pending')"
  echo "Processing: $(echo $STATUS | jq '.processing')"
  echo "Completed: $(echo $STATUS | jq '.completed')"
  echo "Failed: $(echo $STATUS | jq '.failed')"
  echo ""
  echo "Processing Rate: $(echo $STATUS | jq '.rate_per_minute') jobs/min"
  echo "Average Time: $(echo $STATUS | jq '.average_job_time') seconds"
  
  sleep 5
done
```

### Alerting Script

```python
#!/usr/bin/env python
# queue_alerts.py

import json
import subprocess
import smtplib
from email.mime.text import MIMEText

def check_queue_health():
    """Check queue status and send alerts if needed."""
    
    # Get queue status
    result = subprocess.run(
        ["uv", "run", "python", "-m", "src.pipeline_v3.cli_main", 
         "queue", "status", "--json"],
        capture_output=True, text=True
    )
    
    status = json.loads(result.stdout)
    
    alerts = []
    
    # Check for issues
    if status['pending'] > 1000:
        alerts.append(f"High queue depth: {status['pending']} pending jobs")
    
    if status['failed'] > status['completed'] * 0.05:
        alerts.append(f"High failure rate: {status['failed']} failed jobs")
    
    if status['active_workers'] == 0 and status['pending'] > 0:
        alerts.append("No active workers but jobs are pending!")
    
    # Send alerts
    if alerts:
        send_alert("\n".join(alerts))

def send_alert(message):
    """Send email alert."""
    msg = MIMEText(message)
    msg['Subject'] = 'Pipeline v3 Queue Alert'
    msg['From'] = 'pipeline@example.com'
    msg['To'] = 'admin@example.com'
    
    # Send email (configure SMTP settings)
    # s = smtplib.SMTP('localhost')
    # s.send_message(msg)
    # s.quit()
    
    print(f"ALERT: {message}")

if __name__ == "__main__":
    check_queue_health()
```

## Cost Optimization

### Estimating Processing Costs

```
Cost per PDF = (
  Number of Pages × 
  Cost per Page × 
  (1 + Retry Rate)
)

OpenAI Vision API costs (as of 2024):
- ~$0.01 per page for standard quality
- ~$0.03 per page for high quality
```

### Cost Optimization Strategies

1. **Use Page Ranges for Testing**
   ```bash
   # Test with first 5 pages before full processing
   uv run python -m src.pipeline_v3.cli_main add "test.pdf" --pages "1-5"
   ```

2. **Process Only Relevant Pages**
   ```bash
   # Skip table of contents and appendices
   uv run python -m src.pipeline_v3.cli_main add "manual.pdf" --pages "10-90"
   ```

3. **Batch Similar Documents**
   ```bash
   # Process similar documents together for better cache utilization
   uv run python -m src.pipeline_v3.cli_main add "datasheets/model_x/*.pdf"
   ```

## Common Pitfalls and Solutions

### Pitfall 1: Overloading the System

**Problem**: Setting workers too high causes memory exhaustion

**Solution**:
```bash
# Start conservative
uv run python -m src.pipeline_v3.cli_main queue start --workers 2

# Monitor resources
top -b -n 1 | head -20

# Gradually increase if resources allow
uv run python -m src.pipeline_v3.cli_main queue stop
uv run python -m src.pipeline_v3.cli_main queue start --workers 4
```

### Pitfall 2: Not Monitoring Progress

**Problem**: Queue runs for hours without supervision

**Solution**:
```bash
# Set up automated monitoring
crontab -e
# Add: */5 * * * * /path/to/check_queue_health.sh

# Enable notifications
uv run python -m src.pipeline_v3.cli_main config set notifications.enabled true
uv run python -m src.pipeline_v3.cli_main config set notifications.webhook "https://..."
```

### Pitfall 3: Ignoring Failed Jobs

**Problem**: Failed jobs accumulate and are forgotten

**Solution**:
```bash
# Daily failed job review
0 9 * * * /usr/bin/uv run python -m src.pipeline_v3.cli_main queue failed --email admin@example.com

# Automatic retry with backoff
uv run python -m src.pipeline_v3.cli_main config set queue.auto_retry true
uv run python -m src.pipeline_v3.cli_main config set queue.retry_schedule "0,3600,7200,86400"
```

## Batch Processing Checklist

Before starting any batch processing:

- [ ] **Estimate Processing Time**: Pages × 30-45 seconds
- [ ] **Choose Approach**: Direct CLI (<4 pages) or Queue (everything else)
- [ ] **Check Resources**: Available RAM, CPU, disk space
- [ ] **Configure Workers**: Based on system capacity
- [ ] **Set Up Monitoring**: Dashboard or automated checks
- [ ] **Plan Error Handling**: Retry strategy and failure notifications
- [ ] **Test Small First**: Process 5-10 documents before full batch
- [ ] **Schedule Appropriately**: Off-hours for large batches
- [ ] **Prepare Recovery**: Backup strategy for failures
- [ ] **Document Process**: Keep notes for future runs

## Next Steps

- Read [QUEUE_SYSTEM_GUIDE.md](./QUEUE_SYSTEM_GUIDE.md) for detailed queue architecture
- See [PRODUCTION_DEPLOYMENT.md](./PRODUCTION_DEPLOYMENT.md) for production setup
- Check [USER_MANUAL.md](../USER_MANUAL.md) for general usage

---

Remember: **When in doubt, use the queue system!** It's always safer for production workloads.