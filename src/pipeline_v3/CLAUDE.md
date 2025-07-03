# CLAUDE.md - Pipeline v3

This file provides guidance to Claude Code (claude.ai/code) when working with Pipeline v3 in this repository.

## Project Overview

Pipeline v3 is a production-ready document processing system with enterprise-grade features including queue-based processing, intelligent change detection, and comprehensive index lifecycle management. It processes PDF datasheets and documents into a searchable hybrid vector/keyword database with advanced metadata extraction.

## Environment Setup ⚙️

**Critical:** Always run from project root using uv:

```bash
# Working directory
cd /Users/seanbergman/Repositories/rag_lab

# All commands use uv from project root
uv run python -m src.pipeline_v3.cli_main [command]
```

**Virtual Environment:** Pipeline v3 uses uv package manager
- Install: `uv sync` (from project root)
- Environment is automatically managed by uv

**Environment Variables:**
- `OPENAI_API_KEY`: Required for document processing (set in `.env` at project root)

## Document Locations 📁

### Sample Documents (9 files):
```
data/sample_docs/
├── COHR_Air-CooledThermopileSensors_DB25_DS_1119_3.pdf
├── COHR_Air-CooledThermopileSensors_USB_RS232_DS_1119_3.pdf
├── COHR_OP-2_LM-2_OpticalSensors_DS_1119_2.pdf
├── COHR_PowerMax-USB_UV-VIS_DS_0920_2.pdf
├── FieldMaxII-Meter-Family-Data-Sheet_FORMFIRST.pdf
├── labmax-touch-ds.pdf
├── pm10k-plus-ds.pdf
├── Understanding-ISO-17025-Test-Document.docx (🆕 Word)
└── ISO-17025-Calibration-Standards-Presentation.pptx (🆕 PowerPoint)
```

### LMC Documents (30 PDFs):
```
data/lmc_docs/datasheets/
├── COHR_*.pdf (multiple sensor datasheets)
├── EnergyMax-*.pdf (energy measurement sensors)
├── FieldMate-Data-Sheet.pdf
├── LabMax-Pro-Data-Sheet_FORMFIRST.pdf
└── [25+ additional technical datasheets]
```

**Total:** 37 PDFs available for testing

## Core Architecture

### Pipeline v3 Components
- **EnhancedPipeline** (`pipeline/enhanced_core.py`): Main processing coordinator with job queue integration
- **DocumentRegistry** (`core/registry.py`): Central state tracking with consistency checking
- **IndexManager** (`core/index_manager.py`): Advanced CRUD for vector/keyword indexes with embeddings
- **ChangeDetector** (`core/change_detector.py`): Intelligent document lifecycle management
- **DocumentQueue** (`job_queue/manager.py`): Async processing with configurable concurrency
- **CLI Management** (`cli/management.py`): Complete command-line interface

### Storage Isolation (v3-specific paths)
- **Cache:** `./cache_v3/` - LZ4 compressed API responses ✅
- **Vector Store:** `./qdrant_data_v3/` - Qdrant embeddings ✅
- **Keyword Index:** `./keyword_index_v3.db` - SQLite FTS5 search ✅
- **Registry:** `./document_registry_v3.db` - Document state tracking ✅
- **Jobs:** `./jobs_v3.db` - Queue management ✅
- **Fingerprints:** `./fingerprints_v3.db` - Change detection ✅
- **Storage Artifacts:** `./storage_data_v3/` - JSONL artifacts ✅

## Current Status 🎉

**Phase:** Production-Ready
**Core Functionality:** Complete and tested
**Enterprise Features:** Queue management, batch processing, Office documents, URL processing

### 🎯 Development Planning
For current priorities and active issues, see:
- **[ROADMAP.md](../../ROADMAP.md)** - Active development priorities and issue tracking
- **[ISSUES.md](../../ISSUES.md)** - Comprehensive architecture gap analysis
- **[GitHub Issues](https://github.com/seaberger/rag-lab/issues)** - Live issue tracking

## Essential Commands

### Document Operations

**Production CLI** (Enhanced with Issue #9 features):
```bash
# Enhanced document processing with modes
uv run python -m src.pipeline_v3.cli_main add document.pdf --mode datasheet
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf" --mode auto --workers 3
uv run python -m src.pipeline_v3.cli_main add /docs --recursive --mode generic

# Keyword enhancement for improved search quality
uv run python -m src.pipeline_v3.cli_main add document.pdf --with-keywords --mode datasheet

# Custom prompts and URL support
uv run python -m src.pipeline_v3.cli_main add doc.pdf --prompt custom.md
uv run python -m src.pipeline_v3.cli_main add https://example.com/doc.pdf

# Search with hybrid vector+keyword search
uv run python -m src.pipeline_v3.cli_main search "laser sensors" --type hybrid --top-k 5

# Update/Remove documents
uv run python -m src.pipeline_v3.cli_main add document.pdf --with-keywords --force  # Force reprocess with enhancement
uv run python -m src.pipeline_v3.cli_main add document.pdf --force  # Force reprocess without enhancement
uv run python -m src.pipeline_v3.cli_main remove document.pdf
```

**Legacy CLI** (Deprecated - moved to `legacy_backup/`):
```bash
# ⚠️ DEPRECATED: Use main CLI instead
# Legacy interface archived in legacy_backup/cli_v3.py
```

### Queue Management
```bash
# Start/Stop processing queue
uv run python -m src.pipeline_v3.cli_main queue start --workers 2
uv run python -m src.pipeline_v3.cli_main queue stop --wait
uv run python -m src.pipeline_v3.cli_main queue status --detailed
```

### System Status & Maintenance
```bash
# Check system status
uv run python -m src.pipeline_v3.cli_main status --detailed --json

# Run maintenance
uv run python -m src.pipeline_v3.cli_main maintenance --repair --consistency-check

# Configuration
uv run python -m src.pipeline_v3.cli_main config list
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 4
```

### Database Migrations (New in v3)
```bash
# Check migration status for all databases
uv run python -c "
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.core.keyword_index import KeywordIndex
from src.pipeline_v3.core.fingerprint import FingerprintStore
from src.pipeline_v3.job_queue.storage import JobStorage

# Check each database's migration status
registry = DocumentRegistry()
print(f'Registry DB version: {registry.get_schema_version()}')

keyword_idx = KeywordIndex()
print(f'Keyword DB version: {keyword_idx.get_schema_version()}')

fingerprints = FingerprintStore()
print(f'Fingerprints DB version: {fingerprints.get_schema_version()}')

job_storage = JobStorage()
print(f'Jobs DB version: {job_storage.get_schema_version()}')
"

# Run migration tests
uv run python src/pipeline_v3/tests/unit/test_migrations.py
uv run python src/pipeline_v3/tests/integration/test_migrations_integration.py
uv run python src/pipeline_v3/tests/regression/test_migrations_regression.py
```

### Cache Management
```bash
# Clear storage cache for testing
uv run python src/pipeline_v3/utils/cache_manager.py --clear storage --force

# Clear all caches for fresh start
uv run python src/pipeline_v3/utils/cache_manager.py --clear all --force

# Check cache status
uv run python src/pipeline_v3/utils/cache_manager.py --status
```

## Development & Debugging

### Verify System Status:
```bash
# Test document processing end-to-end with keyword enhancement
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf --with-keywords

# Verify storage artifacts created
ls storage_data_v3/  # Should show JSONL files with full UUIDs

# Test search functionality (all types working)
uv run python -m src.pipeline_v3.cli_main search "laser power" --type hybrid
uv run python -m src.pipeline_v3.cli_main search "thermopile sensor" --type vector
uv run python -m src.pipeline_v3.cli_main search "PM10" --type keyword
```


## Key Configuration

Configuration via `config.yaml`:
- **OpenAI Models:** gpt-4.1 for vision, gpt-4.1-mini for keywords, text-embedding-3-small for embeddings
- **Qdrant Settings:** `./qdrant_data_v3`, collection: `datasheets_v3`, dimensions: 1536
- **Storage:** `./storage_data_v3` (JSONL artifacts with full datasheet content)
- **Cache:** LZ4 compression, configurable TTL
- **Queue:** Configurable workers, async processing

## Search Capabilities

Three search modes via CLI:
- **`hybrid`**: Vector + BM25 keyword (recommended)
- **`vector`**: Pure semantic search
- **`keyword`**: BM25 full-text search

```bash
# Hybrid search (best results)
uv run python -m src.pipeline_v3.cli_main search "PM10K power measurement" --type hybrid --top-k 5

# Vector search (conceptual)
uv run python -m src.pipeline_v3.cli_main search "laser sensor specs" --type vector --top-k 3

# Keyword search (exact terms)
uv run python -m src.pipeline_v3.cli_main search "USB interface" --type keyword --top-k 5
```

## Production Features

### Enterprise Capabilities:
- **Queue-Based Processing:** Configurable concurrency with job persistence
- **Intelligent Change Detection:** 6 change types with smart update strategies
- **Index Consistency:** Automatic verification and repair
- **Hybrid Search:** Vector + keyword with score normalization
- **Production Scalability:** Enterprise-grade error handling and recovery
- **Database Migration Framework:** Version tracking, rollback support, and safe schema evolution

### Monitoring & Diagnostics:
- Real-time queue status and performance metrics
- Document state tracking and lifecycle management
- Comprehensive system health checks and maintenance tools
- Structured logging with artifact preservation

## Production Patterns ⚠️

### Critical: Shell Timeout Limitations
**Direct CLI commands timeout after 2 minutes!** This is crucial to understand:
- PDF processing: ~30-45 seconds per page
- Shell timeout: 120 seconds total
- Result: Direct CLI can only handle 3-4 pages max

### Pattern 1: Always Use Queue for Production
```bash
# ❌ WRONG - Will timeout in production
uv run python -m src.pipeline_v3.cli_main add "production/*.pdf"

# ✅ CORRECT - Queue handles unlimited documents
uv run python -m src.pipeline_v3.cli_main queue start --workers 4
uv run python -m src.pipeline_v3.cli_main add "production/*.pdf"
```

### Pattern 2: Large Document Processing
```bash
# For documents > 5 pages, queue is mandatory
uv run python -m src.pipeline_v3.cli_main queue start --workers 2
uv run python -m src.pipeline_v3.cli_main add "manual_300pages.pdf" --mode generic
uv run python -m src.pipeline_v3.cli_main queue status --watch
```

### Pattern 3: Batch Import Workflow
```bash
# Standard batch import pattern
uv run python -m src.pipeline_v3.cli_main queue start --workers 8
uv run python -m src.pipeline_v3.cli_main add "/import/batch_2024/*.pdf" --with-keywords
watch -n 30 'uv run python -m src.pipeline_v3.cli_main queue status --detailed'
```

### Pattern 4: Development vs Production
```bash
# Development (small test files)
uv run python -m src.pipeline_v3.cli_main add test.pdf  # OK for 1-2 pages

# Production (real documents)
uv run python -m src.pipeline_v3.cli_main queue start
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf"  # Always use queue
```

### Key Production Rules:
1. **Default to Queue**: When in doubt, use the queue system
2. **Monitor Progress**: Queue provides real-time feedback
3. **Handle Failures**: Queue automatically retries failed jobs
4. **Resource Management**: Queue prevents system overload
5. **Persistent Jobs**: Queue survives system restarts

### Production Documentation:
- [QUEUE_SYSTEM_GUIDE.md](docs/QUEUE_SYSTEM_GUIDE.md) - Complete queue reference
- [BATCH_PROCESSING_GUIDE.md](docs/BATCH_PROCESSING_GUIDE.md) - Batch patterns
- [PRODUCTION_DEPLOYMENT.md](docs/PRODUCTION_DEPLOYMENT.md) - Production setup

## Important Notes ⚠️

- **Use uv from project root:** Critical for proper environment and imports
- **Primary CLI:** Use `cli_main.py` for production with full v2.1 feature parity
- **Enterprise CLI:** New parameters `--document-type`, `--processing-options`, `--profile` (Issue #36)
- **Keyword Enhancement:** Use `--processing-options keywords` for better search quality
- **CLI Workaround:** For update with keywords, use `add --force` until Issue #18 resolved
- **37 PDFs available:** Mix of simple and complex datasheets for comprehensive testing
- **Storage isolation:** All v3 components use v3-specific paths to avoid conflicts
- **Production status:** Full functionality restored with enhanced search capabilities

## Documentation References

- **📖 Complete User Guide:** [USER_MANUAL.md](./USER_MANUAL.md)
- **🚀 Daily Commands:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)
- **🏗️ Technical Details:** [README.md](./README.md)
- **🆕 Page Range Feature:** [docs/PAGE_RANGE_FEATURE.md](./docs/PAGE_RANGE_FEATURE.md)
- **🆕 API Hardening:** [docs/API_HARDENING.md](./docs/API_HARDENING.md)

**Current Focus:** See [ROADMAP.md](../../ROADMAP.md) for development priorities and [ISSUES.md](../../ISSUES.md) for architecture gaps.
