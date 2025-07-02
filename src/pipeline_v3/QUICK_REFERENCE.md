# Pipeline v3 Quick Reference 🚀

## 🎉 **LATEST UPDATES** - Issue #22 RESOLVED
- **✅ Enhanced Search**: Advanced hybrid fusion algorithms (RRF, Adaptive, Weighted)
- **✅ CLI Search Fixed**: All search types working (vector, keyword, hybrid)
- **✅ Vector Search**: Proper LlamaIndex integration with VectorStoreQuery
- **✅ Basic Filtering**: Document ID filtering implemented
- **✅ Production Ready**: All core functionality restored and enhanced

## ✅ Recent Features Added
- **Issue #45**: 🆕 URL Batch Processing (process URLs from markdown/JSON files)
- **Issue #31**: 🆕 Microsoft Office document support (Word & PowerPoint)
- **Issue #22**: Enhanced search with advanced hybrid fusion methods
- **Issue #17**: Fixed keyword generation JSON parsing (OpenAI compatibility)
- **Issue #20**: Fixed vector indexing with keyword enhancement
- **Issue #19**: Fixed vector index deletion during document updates
- **Issue #18**: Removed redundant update command (use add with --force)
- **Issue #11**: Configurable timeout handling with `--timeout` and `--timeout-per-page`
- **Issue #9**: Consolidated CLI with full v2.1 feature parity

## Essential Commands

### Document Operations
```bash
# Enhanced Add Commands (Issue #9 Features)
python cli_main.py add document.pdf --mode datasheet
python cli_main.py add "data/*.pdf" --mode auto --workers 3
python cli_main.py add /docs --recursive --mode generic
python cli_main.py add doc.pdf --prompt custom.md
python cli_main.py add https://example.com/doc.pdf

# 🆕 Office Document Support (Issue #31)
python cli_main.py add report.docx --with-keywords
python cli_main.py add presentation.pptx --mode auto
python cli_main.py add "docs/*.docx" --workers 3
python cli_main.py add slides.ppt --metadata type=training

# 🆕 URL Batch Processing (Issue #45)
python cli_main.py add dummy --url-file urls.json --with-keywords    # Process URLs from batch file
python cli_main.py add local.pdf --url-file web_docs.md --workers 3  # Mix local + web docs

# Enhanced Search (Issue #22)
python cli_main.py search "keyword"                                    # Hybrid RRF (default)
python cli_main.py search "PM10K specs" --fusion-method adaptive       # Smart weighting
python cli_main.py search "calibration" --type keyword --top-k 5       # Exact matching
python cli_main.py search "sensor tech" --type vector                  # Semantic search
python cli_main.py search "laser" --filter '{"doc_ids": ["abc123"]}'   # Filtered search

# Update documents (re-add with change detection)
python cli_main.py add document.pdf --force  # Force reprocess
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

### 🆕 Batch Operations (Issue #45)
```bash
# Create URL batch files
python cli_main.py batch create-url-file "https://site.com/doc1.pdf" "https://site.com/doc2.pdf" --output batch.json
python cli_main.py batch create-url-file "https://site.com/doc1.pdf" "https://site.com/doc2.pdf" --output batch.md

# Validate URL batch files
python cli_main.py batch validate-urls batch.json

# Test queue performance with URLs
python cli_main.py batch test-queue batch.json --workers 2 --with-keywords
```

## Advanced Search Guide

### Search Types & When to Use

| Type | Best For | Example |
|------|----------|---------|
| `hybrid` | **General use** (recommended) | `search "laser calibration"` |
| `keyword` | Model numbers, exact terms | `search "PM10K specifications" --type keyword` |
| `vector` | Concepts, related topics | `search "measurement accuracy" --type vector` |

### Hybrid Fusion Methods

| Method | Intelligence | Best For |
|--------|-------------|----------|
| `rrf` | Ranking-based fusion (default) | **Most reliable**, general use |
| `adaptive` | **Auto-adjusts weights** | Varied queries, "smart" behavior |
| `weighted` | Score-based with boosting | Fine-tuned control |

```bash
# Smart fusion that adapts to your query
python cli_main.py search "PM10K calibration" --fusion-method adaptive

# Most robust for general use  
python cli_main.py search "thermopile sensor" --fusion-method rrf

# Advanced score control
python cli_main.py search "laser measurement" --fusion-method weighted
```

### Query Optimization Tips

```bash
# Model Numbers → Use keyword or adaptive
python cli_main.py search "LabMax Touch PN 2256258" --type keyword

# Technical Concepts → Use vector or adaptive  
python cli_main.py search "thermopile calibration methodology" --type vector

# Mixed Queries → Use hybrid with RRF
python cli_main.py search "PM10K sensor accuracy specifications" --fusion-method rrf
```

### Basic Filtering

```bash
# Search within specific documents
python cli_main.py search "calibration" --filter '{"doc_ids": ["abc123", "def456"]}'
```

**🚀 Advanced Filtering:** See Issue #23 for upcoming enhanced filtering (metadata, content, dates, etc.)

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