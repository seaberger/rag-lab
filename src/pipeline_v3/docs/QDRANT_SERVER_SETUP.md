# Qdrant Server Setup Guide

⚡ **UPDATE**: Server mode is now the DEFAULT for Pipeline v3! This guide explains how to set up and manage the Qdrant server.

## Server Mode is Now Default

As of the latest update, Pipeline v3 uses Qdrant server mode by default instead of local file storage. This provides:
- Better performance and scalability
- No file lock conflicts during parallel operations
- Production-ready architecture from the start
- Easy transition to cloud deployments

To use the legacy local mode, use: `--config config_local.yaml`

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

### 2. Pipeline Configuration

```bash
# Server mode is now the default!
uv run python -m src.pipeline_v3.cli_main status

# To use local mode instead (file-based storage):
uv run python -m src.pipeline_v3.cli_main --config config_local.yaml status

# To explicitly use server config (optional, as it's the default):
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

## ⚠️ Important: Document Update Behavior

When updating documents in server mode, the system ensures complete chunk removal:

### How It Works

1. **Server Mode** (Default): Uses filter-based deletion to ensure ALL chunks are removed:
   ```python
   # Deletes all chunks with matching doc_id
   client.delete(
       collection_name=collection_name,
       points_selector={
           "filter": {"must": [{"key": "doc_id", "match": {"value": doc_id}}]}
       }
   )
   ```

2. **Local Mode**: Uses LlamaIndex's delete method for file-based storage

### Why This Matters

- When you update a document (e.g., using `--force`), the system:
  1. Detects the document already exists (via fingerprint hash)
  2. Removes ALL old chunks from Qdrant
  3. Adds new chunks from the updated content

- This prevents:
  - Mixed old/new content in search results
  - Orphaned chunks taking up space
  - Inconsistent search behavior

### Example: Updating a Document

```bash
# Initial processing
uv run python -m src.pipeline_v3.cli_main add datasheet_v1.pdf

# Document gets updated externally...

# Force reprocess to update all chunks
uv run python -m src.pipeline_v3.cli_main add datasheet_v1.pdf --force

# The system will:
# 1. Remove all old chunks
# 2. Process the new version
# 3. Add fresh chunks
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
