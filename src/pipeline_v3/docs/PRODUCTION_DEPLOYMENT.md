# Production Deployment Guide

## Critical Production Warning ⚠️

**THE #1 PRODUCTION ISSUE: Shell Command Timeouts**

Most production failures occur because users don't understand that:
- Shell commands timeout after **2 minutes**
- PDF processing takes **30-45 seconds per page**
- Therefore: Direct CLI can only handle **3-4 pages maximum**

**For production, you MUST use the queue system for everything except the smallest documents.**

## Production Readiness Checklist

Before deploying Pipeline v3 to production, ensure:

### ✅ Infrastructure Requirements

- [ ] **CPU**: Minimum 4 cores, recommended 8+ cores
- [ ] **RAM**: Minimum 8GB, recommended 16GB+ (2GB per worker)
- [ ] **Storage**: Fast SSD with 100GB+ free space
- [ ] **Network**: Stable internet, 50Mbps+ for multi-worker setups
- [ ] **OS**: Ubuntu 20.04+ or similar Linux distribution
- [ ] **Python**: 3.12+ with uv package manager installed

### ✅ Critical Configurations

- [ ] **Queue System**: Configured and tested
- [ ] **API Keys**: Securely stored in environment variables
- [ ] **Timeouts**: Adjusted for your document sizes
- [ ] **Workers**: Set based on available resources
- [ ] **Monitoring**: Logging and alerting configured
- [ ] **Backups**: Database and storage backup strategy

## Deployment Architecture

### Recommended Production Setup

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Load Balancer │────▶│  API Gateway    │────▶│  Queue Manager  │
│   (nginx/HAProxy)     │  (Rate Limiting) │     │  (Primary)      │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                          │
                              ┌───────────────────────────┴───────────────┐
                              │                                           │
                    ┌─────────▼────────┐                       ┌─────────▼────────┐
                    │  Worker Pool 1   │                       │  Worker Pool 2   │
                    │  (8 workers)     │                       │  (8 workers)     │
                    └──────────────────┘                       └──────────────────┘
                              │                                           │
                    ┌─────────▼────────┐                       ┌─────────▼────────┐
                    │  Shared Storage  │                       │  PostgreSQL DB   │
                    │  (NFS/S3)        │                       │  (Queue + Meta)  │
                    └──────────────────┘                       └──────────────────┘
```

## Step-by-Step Deployment

### Step 1: System Preparation

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv git postgresql nginx supervisor

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create application user
sudo useradd -m -s /bin/bash pipeline
sudo usermod -aG sudo pipeline
```

### Step 2: Application Setup

```bash
# Switch to pipeline user
sudo su - pipeline

# Clone repository
git clone https://github.com/youorg/rag-lab.git
cd rag-lab

# Install Python dependencies
uv sync

# Create required directories
mkdir -p logs backups temp

# Set permissions
chmod 750 logs backups
chmod 1777 temp
```

### Step 3: Environment Configuration

```bash
# Create production environment file
cat > .env.production << EOF
# API Keys (use secure vault in production)
OPENAI_API_KEY=your-production-key-here  # pragma: allowlist secret

# Database
DATABASE_URL=postgresql://pipeline:password@localhost/pipeline_v3  # pragma: allowlist secret

# Paths
LOG_DIR=/var/log/pipeline_v3
TEMP_DIR=/var/tmp/pipeline_v3
STORAGE_DIR=/mnt/storage/pipeline_v3

# Performance
WORKERS=8
BATCH_SIZE=20
TIMEOUT_PER_PAGE=45

# Monitoring
SENTRY_DSN=your-sentry-dsn
PROMETHEUS_PORT=9090
EOF

# Secure the file
chmod 600 .env.production
```

### Step 4: Database Setup

```bash
# Create PostgreSQL database
sudo -u postgres createuser pipeline
sudo -u postgres createdb pipeline_v3 -O pipeline

# Initialize schema
uv run python -m src.pipeline_v3.scripts.init_db

# Verify database
psql -U pipeline -d pipeline_v3 -c "SELECT version();"
```

### Step 5: Queue Service Configuration

```bash
# Create systemd service
sudo tee /etc/systemd/system/pipeline-queue.service << EOF
[Unit]
Description=Pipeline v3 Queue Service
After=network.target postgresql.service
Requires=postgresql.service

[Service]
Type=simple
User=pipeline
Group=pipeline
WorkingDirectory=/home/pipeline/rag-lab
Environment="PATH=/home/pipeline/.local/bin:/usr/local/bin:/usr/bin:/bin"
EnvironmentFile=/home/pipeline/rag-lab/.env.production

# Important: Increase timeout for queue service
TimeoutStartSec=300
TimeoutStopSec=300

# Main process
ExecStart=/home/pipeline/.local/bin/uv run python -m src.pipeline_v3.cli_main queue start --workers 8

# Restart policy
Restart=always
RestartSec=10
StartLimitInterval=300
StartLimitBurst=5

# Resource limits
LimitNOFILE=65536
LimitNPROC=4096
MemoryLimit=80%

# Logging
StandardOutput=append:/var/log/pipeline_v3/queue.log
StandardError=append:/var/log/pipeline_v3/queue-error.log

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable pipeline-queue
sudo systemctl start pipeline-queue
```

### Step 6: Web API Setup (Optional)

```bash
# Install FastAPI dependencies
uv add fastapi uvicorn

# Create API service
sudo tee /etc/systemd/system/pipeline-api.service << EOF
[Unit]
Description=Pipeline v3 API Service
After=network.target

[Service]
Type=simple
User=pipeline
Group=pipeline
WorkingDirectory=/home/pipeline/rag-lab
EnvironmentFile=/home/pipeline/rag-lab/.env.production

ExecStart=/home/pipeline/.local/bin/uv run uvicorn src.pipeline_v3.api.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 4 \
  --log-level info

Restart=always

[Install]
WantedBy=multi-user.target
EOF

# Configure nginx reverse proxy
sudo tee /etc/nginx/sites-available/pipeline-api << EOF
server {
    listen 80;
    server_name your-domain.com;

    # Important: Increase timeouts for large documents
    proxy_read_timeout 3600;
    proxy_connect_timeout 3600;
    proxy_send_timeout 3600;
    send_timeout 3600;

    # Increase body size for file uploads
    client_max_body_size 500M;
    client_body_timeout 3600;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_cache_bypass \$http_upgrade;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -s /etc/nginx/sites-available/pipeline-api /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl restart nginx
```

## Critical Production Patterns

### Pattern 1: Never Use Direct CLI in Production

❌ **WRONG - Will Timeout**:
```bash
# This WILL fail in production
python -m src.pipeline_v3.cli_main add "production_docs/*.pdf"
```

✅ **CORRECT - Use Queue**:
```bash
# Start queue if not running
systemctl status pipeline-queue || systemctl start pipeline-queue

# Submit to queue
python -m src.pipeline_v3.cli_main add "production_docs/*.pdf"

# Monitor from separate session
watch -n 30 'python -m src.pipeline_v3.cli_main queue status'
```

### Pattern 2: Production Monitoring Setup

```bash
# Create monitoring script
cat > /home/pipeline/monitor_pipeline.sh << 'EOF'
#!/bin/bash

# Check queue health
QUEUE_STATUS=$(uv run python -m src.pipeline_v3.cli_main queue status --json)
PENDING=$(echo $QUEUE_STATUS | jq '.pending')
FAILED=$(echo $QUEUE_STATUS | jq '.failed')
WORKERS=$(echo $QUEUE_STATUS | jq '.active_workers')

# Alert if issues
if [ $PENDING -gt 1000 ]; then
    echo "WARNING: High queue depth: $PENDING pending jobs" | mail -s "Pipeline Alert" admin@company.com
fi

if [ $FAILED -gt 100 ]; then
    echo "ERROR: High failure count: $FAILED failed jobs" | mail -s "Pipeline Error" admin@company.com
fi

if [ $WORKERS -eq 0 ] && [ $PENDING -gt 0 ]; then
    echo "CRITICAL: No workers active but jobs pending!" | mail -s "Pipeline Critical" admin@company.com
    systemctl restart pipeline-queue
fi

# Log metrics
echo "$(date),${PENDING},${FAILED},${WORKERS}" >> /var/log/pipeline_v3/metrics.csv
EOF

chmod +x /home/pipeline/monitor_pipeline.sh

# Add to crontab
(crontab -l ; echo "*/5 * * * * /home/pipeline/monitor_pipeline.sh") | crontab -
```

### Pattern 3: Graceful Shutdown and Maintenance

```bash
# Create maintenance mode script
cat > /home/pipeline/maintenance_mode.sh << 'EOF'
#!/bin/bash

case "$1" in
  enter)
    echo "Entering maintenance mode..."
    # Stop accepting new jobs
    touch /home/pipeline/rag-lab/MAINTENANCE_MODE

    # Wait for current jobs to complete
    while true; do
      PROCESSING=$(uv run python -m src.pipeline_v3.cli_main queue status --json | jq '.processing')
      if [ "$PROCESSING" -eq 0 ]; then
        break
      fi
      echo "Waiting for $PROCESSING jobs to complete..."
      sleep 30
    done

    # Stop queue
    systemctl stop pipeline-queue
    echo "Maintenance mode active"
    ;;

  exit)
    echo "Exiting maintenance mode..."
    rm -f /home/pipeline/rag-lab/MAINTENANCE_MODE
    systemctl start pipeline-queue
    echo "Normal operation resumed"
    ;;

  status)
    if [ -f /home/pipeline/rag-lab/MAINTENANCE_MODE ]; then
      echo "Status: Maintenance mode ACTIVE"
    else
      echo "Status: Normal operation"
    fi
    ;;
esac
EOF

chmod +x /home/pipeline/maintenance_mode.sh
```

## Performance Tuning

### System Kernel Parameters

```bash
# Optimize for high throughput
sudo tee -a /etc/sysctl.conf << EOF
# Network optimizations
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.ipv4.ip_local_port_range = 1024 65535
net.ipv4.tcp_tw_reuse = 1

# Memory optimizations
vm.swappiness = 10
vm.dirty_ratio = 15
vm.dirty_background_ratio = 5

# File handle limits
fs.file-max = 2097152
EOF

sudo sysctl -p
```

### Application Tuning

```yaml
# production_config.yaml
pipeline:
  max_concurrent: 16
  timeout_seconds: 3600

queue:
  max_workers: 8
  batch_size: 20
  job_timeout: 3600
  retry_attempts: 3
  retry_delay: 60

storage:
  cache_enabled: true
  cache_size_gb: 50
  compression: true

openai:
  timeout_base: 60
  timeout_per_page: 45
  max_retries: 5
  client_timeout: 120

performance:
  connection_pool_size: 20
  thread_pool_size: 32
  async_io: true
```

## Monitoring and Observability

### Prometheus Metrics

```python
# Add to your application
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Define metrics
jobs_processed = Counter('pipeline_jobs_processed_total', 'Total processed jobs')
jobs_failed = Counter('pipeline_jobs_failed_total', 'Total failed jobs')
processing_time = Histogram('pipeline_processing_seconds', 'Job processing time')
queue_depth = Gauge('pipeline_queue_depth', 'Current queue depth')
active_workers = Gauge('pipeline_active_workers', 'Active worker count')

# Start metrics server
start_http_server(9090)
```

### Logging Configuration

```python
# logging_config.py
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'json': {
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(name)s %(levelname)s %(message)s'
        }
    },
    'handlers': {
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/pipeline_v3/application.log',
            'maxBytes': 104857600,  # 100MB
            'backupCount': 10,
            'formatter': 'detailed'
        },
        'json_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': '/var/log/pipeline_v3/application.json',
            'maxBytes': 104857600,
            'backupCount': 10,
            'formatter': 'json'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['file', 'json_file']
    }
}
```

## Backup and Recovery

### Automated Backup Script

```bash
#!/bin/bash
# backup_pipeline.sh

BACKUP_DIR="/mnt/backups/pipeline_v3"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup databases
pg_dump -U pipeline pipeline_v3 | gzip > "$BACKUP_DIR/$DATE/database.sql.gz"
cp /home/pipeline/rag-lab/*.db "$BACKUP_DIR/$DATE/"

# Backup storage
tar -czf "$BACKUP_DIR/$DATE/storage.tar.gz" -C /mnt/storage pipeline_v3/

# Backup configuration
cp -r /home/pipeline/rag-lab/.env* "$BACKUP_DIR/$DATE/"
cp -r /home/pipeline/rag-lab/config "$BACKUP_DIR/$DATE/"

# Keep only last 7 days
find "$BACKUP_DIR" -type d -mtime +7 -exec rm -rf {} \;

echo "Backup completed: $BACKUP_DIR/$DATE"
```

### Disaster Recovery Plan

1. **Database Recovery**:
   ```bash
   # Restore PostgreSQL
   gunzip < backup/database.sql.gz | psql -U pipeline pipeline_v3

   # Restore SQLite databases
   cp backup/*.db /home/pipeline/rag-lab/
   ```

2. **Storage Recovery**:
   ```bash
   # Restore document storage
   tar -xzf backup/storage.tar.gz -C /mnt/storage/
   ```

3. **Queue Recovery**:
   ```bash
   # Reset stuck jobs
   uv run python -m src.pipeline_v3.cli_main queue reset-stuck

   # Retry failed jobs
   uv run python -m src.pipeline_v3.cli_main queue retry-failed
   ```

## Security Hardening

### API Key Management

```bash
# Use HashiCorp Vault or AWS Secrets Manager
# Example with Vault
vault kv put secret/pipeline/prod \
  openai_api_key="sk-..." \  # pragma: allowlist secret
  database_password="..."  # pragma: allowlist secret

# Application retrieves secrets
export OPENAI_API_KEY=$(vault kv get -field=openai_api_key secret/pipeline/prod)
```

### Network Security

```bash
# Firewall rules
sudo ufw allow 22/tcp  # SSH
sudo ufw allow 80/tcp  # HTTP
sudo ufw allow 443/tcp # HTTPS
sudo ufw allow from 10.0.0.0/8 to any port 5432  # PostgreSQL internal only
sudo ufw enable
```

### File Permissions

```bash
# Secure file permissions
chmod 750 /home/pipeline/rag-lab
chmod 640 /home/pipeline/rag-lab/.env*
chmod 750 /var/log/pipeline_v3
chown -R pipeline:pipeline /home/pipeline/rag-lab
```

## Troubleshooting Production Issues

### Issue: Queue Service Won't Start

```bash
# Check service status
systemctl status pipeline-queue

# Check logs
journalctl -u pipeline-queue -n 100

# Common fixes
sudo -u pipeline uv sync  # Update dependencies
chmod 664 /home/pipeline/rag-lab/*.db  # Fix permissions
```

### Issue: High Memory Usage

```bash
# Check memory per worker
ps aux | grep "queue start" | awk '{sum+=$6} END {print sum/NR/1024 " MB per worker"}'

# Reduce workers
systemctl stop pipeline-queue
sed -i 's/--workers 8/--workers 4/' /etc/systemd/system/pipeline-queue.service
systemctl daemon-reload
systemctl start pipeline-queue
```

### Issue: Slow Processing

```bash
# Check system resources
iostat -x 1
iotop
htop

# Check API latency
uv run python -m src.pipeline_v3.cli_main test-api-latency

# Optimize
# 1. Increase workers if CPU available
# 2. Check network bandwidth
# 3. Review document complexity
```

## Production Checklist Summary

Before going live:

- [ ] Queue system tested with 100+ documents
- [ ] Monitoring and alerting configured
- [ ] Backup strategy implemented and tested
- [ ] Security hardening completed
- [ ] Performance baseline established
- [ ] Runbook created for operations team
- [ ] Disaster recovery plan tested
- [ ] Load testing completed
- [ ] Documentation updated for your environment
- [ ] Team trained on queue vs direct CLI usage

Remember: **In production, always use the queue system!**
