# Qdrant Server Setup Guide

This guide explains how to set up and use Qdrant in server mode for production deployments.

## 🚀 Quick Start

### 1. Start Qdrant Server

```bash
# From project root
./scripts/qdrant_server.sh start
```

This will:
- Start Qdrant server in Docker on port 6333
- Create persistent storage in `./qdrant_server_data`
- Wait for server to be ready
- Display dashboard URL: http://localhost:6333/dashboard

### 2. Configure Pipeline for Server Mode

```bash
# Use the server configuration
export PIPELINE_CONFIG=config_server.yaml

# Or specify directly
uv run python -m src.pipeline_v3.cli_main --config config_server.yaml status
```

### 3. Process Documents

Everything works the same as local mode:

```bash
# Start queue
uv run python -m src.pipeline_v3.cli_main queue start --workers 4

# Add documents
uv run python -m src.pipeline_v3.cli_main add document.pdf
```

## 📦 Migration from Local Mode

### Automatic Migration

```bash
# Migrate all collections
uv run python src/pipeline_v3/scripts/migrate_to_server.py

# Migrate specific collection
uv run python src/pipeline_v3/scripts/migrate_to_server.py \
  --collection datasheets_v3 \
  --verify
```

### Manual Migration

1. Export from local:
   ```bash
   # Use Qdrant's snapshot feature (if available)
   ```

2. Import to server:
   ```bash
   # Restore snapshot
   ```

## 🔧 Server Management

### Check Status
```bash
./scripts/qdrant_server.sh status
```

### View Logs
```bash
./scripts/qdrant_server.sh logs
```

### Restart Server
```bash
./scripts/qdrant_server.sh restart
```

### Reset Data (⚠️ Warning: Deletes all data!)
```bash
./scripts/qdrant_server.sh reset
```

## 🏢 Production Deployment

### Docker Compose

The included `docker-compose.yml` provides:
- Persistent volume mapping
- Health checks
- Automatic restart
- Port configuration

### Environment Variables

```bash
# Optional API key for security
export QDRANT_API_KEY=your-secure-key

# Custom server location
export QDRANT_HOST=qdrant.example.com
export QDRANT_PORT=6333
```

### Kubernetes Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: qdrant
spec:
  replicas: 1
  selector:
    matchLabels:
      app: qdrant
  template:
    metadata:
      labels:
        app: qdrant
    spec:
      containers:
      - name: qdrant
        image: qdrant/qdrant:latest
        ports:
        - containerPort: 6333
        volumeMounts:
        - name: qdrant-storage
          mountPath: /qdrant/storage
      volumes:
      - name: qdrant-storage
        persistentVolumeClaim:
          claimName: qdrant-pvc
```

## 🎯 Benefits of Server Mode

### Immediate Benefits
- ✅ **No file lock conflicts** - Multiple clients can connect
- ✅ **Test stability** - Parallel tests without resource conflicts
- ✅ **Better performance** - Optimized for concurrent access
- ✅ **Web dashboard** - Visual collection management

### Production Benefits
- 🚀 **Horizontal scaling** - Add more Qdrant nodes
- 🚀 **High availability** - Clustering and replication
- 🚀 **Multi-tenant** - Separate collections per customer
- 🚀 **Monitoring** - Prometheus metrics, health checks

## 🔍 Troubleshooting

### Server Won't Start
```bash
# Check if port is in use
lsof -i :6333

# Check Docker logs
docker logs rag_lab_qdrant

# Try different port
QDRANT__SERVICE__HTTP_PORT=6334 docker-compose up -d
```

### Connection Refused
```bash
# Verify server is running
curl http://localhost:6333/readyz

# Check firewall
sudo ufw allow 6333/tcp  # Ubuntu/Debian
```

### Migration Issues
```bash
# Check collection compatibility
uv run python -c "
from qdrant_client import QdrantClient
client = QdrantClient(path='./qdrant_data_v3')
print(client.get_collections())
"
```

## 📊 Performance Tuning

### Memory Configuration
```yaml
# docker-compose.yml
environment:
  - QDRANT__STORAGE__MEMORY_MAP_THRESHOLD=20000
  - QDRANT__STORAGE__PERFORMANCE__MAX_SEARCH_THREADS=0  # Use all CPU cores
```

### Collection Optimization
```python
# Optimize for search speed
client.update_collection(
    collection_name="datasheets_v3",
    optimizer_config=models.OptimizersConfigDiff(
        indexing_threshold=20000,
        max_segment_size=200000,
    )
)
```

## 🔐 Security

### Enable Authentication
```yaml
# docker-compose.yml
environment:
  - QDRANT__SERVICE__API_KEY=${QDRANT_API_KEY}
```

### TLS/SSL
```yaml
# For production
environment:
  - QDRANT__SERVICE__ENABLE_TLS=true
  - QDRANT__TLS__CERT=/path/to/cert.pem
  - QDRANT__TLS__KEY=/path/to/key.pem
```

## 📚 Additional Resources

- [Qdrant Documentation](https://qdrant.tech/documentation/)
- [Docker Hub: qdrant/qdrant](https://hub.docker.com/r/qdrant/qdrant)
- [Qdrant Cloud](https://cloud.qdrant.io/) - Managed service option
