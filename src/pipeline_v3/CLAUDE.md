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

### Sample Documents (7 PDFs):
```
data/sample_docs/
├── COHR_Air-CooledThermopileSensors_DB25_DS_1119_3.pdf
├── COHR_Air-CooledThermopileSensors_USB_RS232_DS_1119_3.pdf  
├── COHR_OP-2_LM-2_OpticalSensors_DS_1119_2.pdf
├── COHR_PowerMax-USB_UV-VIS_DS_0920_2.pdf
├── FieldMaxII-Meter-Family-Data-Sheet_FORMFIRST.pdf
├── labmax-touch-ds.pdf
└── pm10k-plus-ds.pdf
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
- **Storage Artifacts:** `./storage_data_v3/` - JSONL artifacts ❌ **Issue #6**

## Current Status 🔄

**Active Issue:** #6 - Document storage artifacts not created  
**Last Updated:** June 9, 2025

### Recently Fixed Issues:
- ✅ **Issue #3:** Vector embedding generation failure (LlamaIndex integration)
- ✅ **Issue #4:** Document state update errors (shared registry pattern)

### Issue #6 Details:
**Problem:** Two CLI entry points with different behaviors:
- `cli_v3.py` ✅ Creates JSONL artifacts correctly
- `cli_main.py` ❌ Missing artifact creation logic (production CLI)

**Root Cause:** Enhanced Pipeline lacks JSONL artifact creation from original pipeline

**Files to Fix:**
1. `/src/pipeline_v3/pipeline/enhanced_core.py` - Add artifact creation
2. Reference: `/src/pipeline_v3/core/pipeline.py` lines 290-307 (working implementation)

## Essential Commands

### Document Operations
```bash
# Add documents (currently has Issue #6)
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf

# Working alternative for testing artifacts
uv run python src/pipeline_v3/cli_v3.py --src data/sample_docs/labmax-touch-ds.pdf --mode datasheet

# Search documents
uv run python -m src.pipeline_v3.cli_main search "laser sensors" --type hybrid --top-k 5

# Update/Remove documents  
uv run python -m src.pipeline_v3.cli_main update document.pdf --force
uv run python -m src.pipeline_v3.cli_main remove document.pdf
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

### Cache Management
```bash
# Clear storage cache for testing
uv run python src/pipeline_v3/utils/cache_manager.py --clear storage --force

# Clear all caches for fresh start
uv run python src/pipeline_v3/utils/cache_manager.py --clear all --force

# Check cache status
uv run python src/pipeline_v3/utils/cache_manager.py --status
```

## Debugging Issue #6

### Problem Verification:
```bash
# This should create artifacts but doesn't (Issue #6)
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf

# Check if storage directory exists
ls storage_data_v3/  # Currently returns "No such file or directory"

# This working command creates artifacts correctly  
uv run python src/pipeline_v3/cli_v3.py --src data/sample_docs/labmax-touch-ds.pdf --mode datasheet
ls storage_data_v3/  # Should show JSONL files
```

### Development Workflow for Fix:
1. **Compare implementations:** `enhanced_core.py` vs `pipeline.py` 
2. **Add artifact creation:** Port JSONL logic to enhanced pipeline
3. **Test storage creation:** Verify directory and files are created
4. **Validate content:** Ensure artifacts contain proper datasheet metadata

## Key Configuration

Configuration via `config.yaml`:
- **OpenAI Models:** gpt-4o for vision, text-embedding-3-small for embeddings
- **Qdrant Settings:** `./qdrant_data_v3`, collection: `datasheets_v3`, dimensions: 1536
- **Storage:** `./storage_data_v3` (currently not created due to Issue #6)
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

### Monitoring & Diagnostics:
- Real-time queue status and performance metrics
- Document state tracking and lifecycle management
- Comprehensive system health checks and maintenance tools
- Structured logging with artifact preservation

## Important Notes ⚠️

- **Use uv from project root:** Critical for proper environment and imports
- **Two CLI interfaces:** `cli_main.py` (production, has Issue #6) vs `cli_v3.py` (working)
- **37 PDFs available:** Mix of simple and complex datasheets for comprehensive testing
- **Storage isolation:** All v3 components use v3-specific paths to avoid conflicts
- **Issue #6 priority:** Artifact creation is critical for production deployment

## Documentation References

- **📖 Complete User Guide:** [USER_MANUAL.md](./USER_MANUAL.md)
- **🚀 Daily Commands:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)  
- **🏗️ Technical Details:** [README.md](./README.md)
- **📋 Development Status:** [DEVELOPMENT_STATUS.md](./DEVELOPMENT_STATUS.md)

**Focus:** Complete Issue #6 fix to enable proper JSONL artifact persistence in Pipeline v3's production CLI interface.