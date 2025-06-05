# Pipeline v3 Quick Reference 🚀

## Essential Commands

### Document Operations
```bash
# Add documents
python cli_main.py add document.pdf
python cli_main.py add *.pdf --metadata type=manual

# Search documents  
python cli_main.py search "keyword"
python cli_main.py search "query" --type hybrid --top-k 5

# Update/Remove documents
python cli_main.py update document.pdf --force
python cli_main.py remove document.pdf
```

### Queue Management
```bash
# Start/Stop processing queue
python cli_main.py queue start --workers 4
python cli_main.py queue stop --wait
python cli_main.py queue status --detailed
```

### System Status
```bash
# Check system status
python cli_main.py status
python cli_main.py status --detailed --json

# Run maintenance
python cli_main.py maintenance --repair
python cli_main.py maintenance --consistency-check
```

### Configuration
```bash
# View/Set configuration
python cli_main.py config list
python cli_main.py config get queue.max_workers
python cli_main.py config set queue.max_workers 8
```

## Search Types

| Type | Use Case | Example |
|------|----------|---------|
| `keyword` | Exact matches, technical terms | `search "API reference" --type keyword` |
| `vector` | Semantic search, concepts | `search "troubleshooting guide" --type vector` |
| `hybrid` | Best of both (recommended) | `search "installation steps" --type hybrid` |

## Common Metadata

```bash
# Technical documents
--metadata type=manual category=technical version=1.0

# Research papers  
--metadata type=research author=smith year=2024

# Policy documents
--metadata type=policy department=HR effective_date=2024-01-01
```

## Performance Tips

```bash
# Optimize for speed
python cli_main.py config set queue.max_workers 8
python cli_main.py config set chunking.chunk_size 512

# Optimize for accuracy
python cli_main.py config set chunking.chunk_size 1024
python cli_main.py config set chunking.chunk_overlap 128
```

## Troubleshooting

```bash
# Debug issues
python cli_main.py --verbose status
python cli_main.py maintenance --repair --cleanup

# Reset configuration
python cli_main.py config reset --confirm
```

## JSON Output for Automation

```bash
# Machine-readable output
python cli_main.py status --json
python cli_main.py search "query" --json
python cli_main.py queue status --json
```

---
📖 **Full Documentation:** [USER_MANUAL.md](./USER_MANUAL.md) | 🏗️ **Architecture:** [README.md](./README.md)