# Pipeline v3 Quick Reference 🚀

## 🎉 **LATEST UPDATES** - Multi-Tenant Enterprise Architecture Ready!
- **✅ NEW: PostgreSQL Multi-Tenant Database**: Complete tenant isolation with Row-Level Security (January 2025)
- **✅ Database Setup Automation**: Full PostgreSQL + Qdrant setup with comprehensive documentation
- **✅ CRITICAL BUG FIX**: Vector search tenant filtering now works correctly (was bypassed before)
- **✅ Tenant-Specific CLI**: `--tenant-id` parameter for complete data isolation
- **✅ Enterprise CLI Parameters**: Consistent `--document-type`, `--processing-options`, `--profile`
- **✅ Enhanced Search**: Advanced hybrid fusion algorithms (RRF, Adaptive, Weighted)
- **✅ Production Ready**: Enterprise-grade multi-tenant architecture with complete data isolation

## ✅ Recent Features Added
- **January 2025**: 🆕 **Complete Multi-Tenant PostgreSQL Architecture** with RLS and tenant isolation
- **January 2025**: 🆕 **Database Setup Automation** - Complete PostgreSQL + Qdrant setup scripts and documentation
- **January 2025**: 🆕 **Critical Tenant Filtering Fix** - Vector search now properly respects tenant boundaries
- **January 2025**: 🆕 **CLI Tenant Support** - `--tenant-id` parameter for tenant-specific operations
- **Issue #36**: 🆕 Enterprise CLI parameter consistency (`--document-type`, `--processing-options`, `--profile`)
- **Issue #33**: 🆕 Enhanced directory parsing with filtering and Office document support
- **Issue #45**: 🆕 URL Batch Processing (process URLs from markdown/JSON files)
- **Issue #31**: 🆕 Microsoft Office document support (Word & PowerPoint)
- **Issue #22**: Enhanced search with advanced hybrid fusion methods

## ⚠️ **CRITICAL: Database Setup Required!** ⚠️

**Pipeline v3 uses multi-tenant PostgreSQL + Qdrant architecture!**

### Quick Setup (New Installations)
```bash
# ✅ OPTION 1: Automated setup (recommended)
./setup_databases.sh

# ✅ OPTION 2: Manual setup
# See: DATABASE_SETUP_GUIDE.md for detailed instructions

# ✅ Verify setup works
uv run python -m src.pipeline_v3.cli_main status --json
```

### Daily Usage (Services Already Setup)
```bash
# Start Qdrant server (if not running)
./scripts/qdrant_server.sh start

# PostgreSQL should be running as system service
# Dashboard available at: http://localhost:6333/dashboard
```

**For single-user local development only:**
```bash
# Use SQLite instead of PostgreSQL
uv run python -m src.pipeline_v3.cli_main --config config_local.yaml [command]
```

## ⚠️ **CRITICAL PRODUCTION WARNING** ⚠️

**Direct CLI commands timeout after 2 minutes!** Since PDF processing takes ~30-45 seconds per page:
- ✅ **Small PDFs (1-3 pages)**: Direct CLI is OK
- ❌ **Large PDFs (>4 pages)**: **MUST use queue system**
- ❌ **Multiple PDFs**: **MUST use queue system**
- ❌ **Production workloads**: **ALWAYS use queue system**

```bash
# ❌ WRONG - Will timeout
python cli_main.py add "docs/*.pdf"  # Fails after ~3-4 pages

# ✅ CORRECT - Use queue
python cli_main.py queue start --workers 4
python cli_main.py add "docs/*.pdf"  # Processes reliably
```

**Quick Rule: If processing > 4 pages total, use the queue system!**

## Essential Commands

### Quick Start Flow (<10 lines)
```bash
# 1. Setup databases (one-time setup)
./setup_databases.sh

# 2. Verify multi-tenant system works
uv run python -m src.pipeline_v3.cli_main status --json

# 3. Modern document processing with tenant isolation
uv run python -m src.pipeline_v3.cli_main add document.pdf --document-type datasheet --processing-options keywords

# 4. Multi-tenant search with complete data isolation
uv run python -m src.pipeline_v3.cli_main search "laser sensors" --fusion-method adaptive --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e

# 5. Directory processing with tenant context
uv run python -m src.pipeline_v3.cli_main add /docs --recursive --include-pattern "*.pdf" --exclude-pattern "**/test/**"

# 6. Test tenant isolation (should return different results)
uv run python -m src.pipeline_v3.cli_main search "test" --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e
uv run python -m src.pipeline_v3.cli_main search "test" --tenant-id 4a58b5b8-9c7e-4e5a-8c3b-7f9e6d2a1c8e
```

### Document Operations
```bash
# Modern Document Type Classification with Multi-Tenant Support
uv run python -m src.pipeline_v3.cli_main add datasheet.pdf --document-type datasheet --processing-options keywords
uv run python -m src.pipeline_v3.cli_main add manual.pdf --document-type manual --processing-options enhanced-metadata
uv run python -m src.pipeline_v3.cli_main add spec.pdf --document-type specification --metadata version=2.0
uv run python -m src.pipeline_v3.cli_main add unknown.pdf --document-type auto  # Automatic detection

# Tenant-Specific Document Management (Enterprise)
uv run python -m src.pipeline_v3.cli_main add document.pdf --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e
uv run python -m src.pipeline_v3.cli_main add confidential.pdf --tenant-id 4a58b5b8-9c7e-4e5a-8c3b-7f9e6d2a1c8e

# Processing Profiles (Predefined Configurations)
uv run python -m src.pipeline_v3.cli_main add catalog.pdf --profile comprehensive
uv run python -m src.pipeline_v3.cli_main add datasheet.pdf --profile standard-datasheet
uv run python -m src.pipeline_v3.cli_main add quick_scan.pdf --profile quick-scan

# Advanced Directory Processing with Patterns
uv run python -m src.pipeline_v3.cli_main add /company_docs --recursive --dry-run                      # Preview files
uv run python -m src.pipeline_v3.cli_main add /docs --include-pattern "*.pdf" --exclude-pattern "**/test/**"
uv run python -m src.pipeline_v3.cli_main add /reports --include-pattern "*.docx" --include-pattern "*.pptx"
uv run python -m src.pipeline_v3.cli_main add /data --recursive --exclude-pattern "*.tmp" --exclude-pattern ".git/**"

# URL Batch Processing (Modern)
python cli_main.py add dummy --url-file batch_urls.json --processing-options keywords
python cli_main.py add local.pdf --url-file web_docs.md --workers 3 --document-type auto

# Page-Range Processing for Cost Optimization
python cli_main.py add large_manual.pdf --pages "1-10" --document-type manual
python cli_main.py add catalog.pdf --pages "1-5,20-30" --processing-options keywords
python cli_main.py add spec.pdf --pages "1,3,5,10-15" --profile standard-datasheet

# Advanced Search with Multiple Fusion Methods and Tenant Isolation
uv run python -m src.pipeline_v3.cli_main search "laser measurement" --fusion-method adaptive --top-k 10
uv run python -m src.pipeline_v3.cli_main search "PM10K specifications" --type keyword --filter '{"doc_ids": ["abc123"]}'
uv run python -m src.pipeline_v3.cli_main search "calibration procedures" --type hybrid --fusion-method rrf
uv run python -m src.pipeline_v3.cli_main search "thermopile sensor" --type vector --top-k 5

# Multi-Tenant Search (Complete Data Isolation)
uv run python -m src.pipeline_v3.cli_main search "sensor" --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e
uv run python -m src.pipeline_v3.cli_main search "sensor" --tenant-id 4a58b5b8-9c7e-4e5a-8c3b-7f9e6d2a1c8e  # Different results

# Document Management
uv run python -m src.pipeline_v3.cli_main add document.pdf --force  # Force reprocess with change detection
uv run python -m src.pipeline_v3.cli_main remove document.pdf       # Remove from all indexes

# Tenant-Specific Document Management
uv run python -m src.pipeline_v3.cli_main remove document.pdf --tenant-id 081f2c7d-20be-4fc6-b8e2-113b9629db8e
```

### Queue Management
```bash
# Start/Stop processing queue
uv run python -m src.pipeline_v3.cli_main queue start --workers 4
uv run python -m src.pipeline_v3.cli_main queue stop --wait
uv run python -m src.pipeline_v3.cli_main queue status --detailed
```

### System Status
```bash
# Check system status (shows tenant context and PostgreSQL backend)
uv run python -m src.pipeline_v3.cli_main status
uv run python -m src.pipeline_v3.cli_main status --detailed --json

# Run maintenance
uv run python -m src.pipeline_v3.cli_main maintenance --repair
uv run python -m src.pipeline_v3.cli_main maintenance --consistency-check
```

### Configuration
```bash
# View/Set configuration
uv run python -m src.pipeline_v3.cli_main config list
uv run python -m src.pipeline_v3.cli_main config get queue.max_workers
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 8

# View tenant configuration
uv run python -m src.pipeline_v3.cli_main config get database.postgresql.default_tenant_id
```

### Advanced Batch Example (Production)
```bash
# Start persistent queue for production workloads
python cli_main.py queue start --workers 8

# Batch process mixed document types with comprehensive filtering
python cli_main.py add /company_docs --recursive \
  --include-pattern "*.pdf" --include-pattern "*.docx" \
  --exclude-pattern "**/archive/**" --exclude-pattern "*.tmp" \
  --document-type auto --processing-options keywords,enhanced-metadata \
  --metadata source=production batch_date=$(date +%Y%m%d)

# URL batch processing with profiles
python cli_main.py add dummy --url-file external_docs.json \
  --profile quick-scan --workers 4 --metadata source=external

# Page-range batch for large document collections
python cli_main.py add "catalogs/*.pdf" --pages "1-10" \
  --document-type datasheet --processing-options keywords --workers 6

# Monitor production batch progress
python cli_main.py queue status --detailed --json

# Create and validate URL batch files
python cli_main.py batch create-url-file "https://site.com/doc1.pdf" "https://site.com/doc2.pdf" --output batch.json
python cli_main.py batch validate-urls batch.json
python cli_main.py batch test-queue batch.json --workers 2 --processing-options keywords
```

## 🏭 Modern CLI Parameter Guide

### Document Type Classification (`--document-type`)
| Type | Purpose | Example |
|------|---------|----------|
| `datasheet` | Technical datasheets with specifications | `--document-type datasheet` |
| `manual` | User manuals and guides | `--document-type manual` |
| `specification` | Technical specifications | `--document-type specification` |
| `generic` | General documents | `--document-type generic` |
| `auto` | Automatic detection (default) | `--document-type auto` |

### Processing Options (`--processing-options`)
| Option | Purpose | Usage |
|--------|---------|-------|
| `keywords` | Generate keywords for enhanced search | `--processing-options keywords` |
| `enhanced-metadata` | Extract additional metadata | `--processing-options enhanced-metadata` |
| `fast-mode` | Speed-optimized processing | `--processing-options fast-mode` |
| **Combined** | Multiple options | `--processing-options keywords,enhanced-metadata` |

### Processing Profiles (`--profile`)
| Profile | Description | Best For |
|---------|-------------|----------|
| `standard-datasheet` | Datasheet with keyword enhancement | Technical datasheets |
| `quick-scan` | Fast processing with reduced timeout | Quick document previews |
| `comprehensive` | All enhancements with extended timeout | Important documents |

### Directory Filtering
| Option | Purpose | Example |
|--------|---------|---------|
| `--recursive` | Scan subdirectories | `add data/docs --recursive` |
| `--dry-run` | Preview files without processing | `add data/docs --dry-run` |
| `--include-pattern` | Only include matching files | `--include-pattern "*.pdf"` |
| `--exclude-pattern` | Skip matching files/dirs | `--exclude-pattern "**/test/**"` |

### Page Range Selection (`--pages`)
| Format | Description | Example |
|--------|-------------|---------|
| `"1-10"` | Pages 1 through 10 | `--pages "1-10"` |
| `"1,3,5"` | Specific pages only | `--pages "1,3,5"` |
| `"1-5,10-15"` | Multiple ranges | `--pages "1-5,10-15"` |

### URL Batch Processing (`--url-file`)
```bash
# JSON format batch file
python cli_main.py add dummy --url-file batch.json --workers 3

# Markdown format batch file
python cli_main.py add dummy --url-file batch.md --processing-options keywords

# Mix local files with URL batch
python cli_main.py add local.pdf --url-file web_docs.json --document-type auto
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

### Query Optimization Examples

```bash
# Model Numbers → Use keyword or adaptive fusion
python cli_main.py search "LabMax Touch PN 2256258" --type keyword --top-k 5
python cli_main.py search "PM10K specifications" --fusion-method adaptive

# Technical Concepts → Use vector or adaptive search
python cli_main.py search "thermopile calibration methodology" --type vector --top-k 10
python cli_main.py search "laser measurement accuracy" --fusion-method adaptive

# Mixed Queries → Use hybrid with RRF (most reliable)
python cli_main.py search "PM10K sensor accuracy specifications" --fusion-method rrf --top-k 8
python cli_main.py search "optical sensor calibration procedures" --type hybrid

# Filtered Search → Combine with document filtering
python cli_main.py search "calibration" --filter '{"doc_ids": ["datasheet_123", "manual_456"]}'
python cli_main.py search "specifications" --type keyword --filter '{"doc_ids": ["specific_doc"]}'
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
# Qdrant server issues
./scripts/qdrant_server.sh status   # Check if running
./scripts/qdrant_server.sh logs     # View server logs
./scripts/qdrant_server.sh restart  # Restart if needed

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
