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
- **Storage Artifacts:** `./storage_data_v3/` - JSONL artifacts ✅

## Current Status 🎉

**Phase:** Production-Ready with Optimization Opportunities  
**Last Updated:** June 9, 2025  
**Latest Commit:** `a05cc7c` - JSONL storage artifact creation

### Core Functionality: ✅ COMPLETE
- ✅ **Issue #3:** Vector embedding generation (LlamaIndex integration)
- ✅ **Issue #4:** Document state update errors (shared registry pattern)  
- ✅ **Issue #6:** Storage artifacts creation (OpenAI Vision API integration)

### ✅ Major Completed Features:
- ✅ **Issue #9:** CLI Consolidation (**COMPLETED & MERGED**)
  - Single production CLI with full v2.1 feature parity
  - Document classification modes: `--mode datasheet|generic|auto`
  - Batch processing: `"docs/*.pdf" --workers 3`
  - Custom prompts: `--prompt custom.md`
  - URL support: Process HTTP/HTTPS documents
  - See [implementation docs](docs/ISSUE_9_CLI_CONSOLIDATION_PLAN.md)

### ⚠️ CRITICAL Issues Requiring Immediate Attention:

- 🚨 **Issue #16:** Restore chunking_metadata.py integration (CRITICAL)
  - V3 pipeline completely bypasses keyword enhancement from V2.1
  - Missing --with-keywords CLI parameter
  - All documents missing contextual keywords that improve retrieval
  - **ROOT CAUSE**: V3 uses basic SentenceSplitter instead of process_and_index_document()
  - **BLOCKS**: All other chunking improvements until resolved

- 🔥 **Issue #7:** Fix model/part number pair extraction (HIGH)
  - Multi-line JSON metadata not parsed correctly in both V2.1 & V3
  - Current logic only reads first line: `"Metadata: {"` instead of full JSON
  - **IDENTIFIED FIX**: Parse complete JSON block from "Metadata:" to "---" separator
  - All datasheet pair extraction currently broken

### 🔄 Active Enhancement Issues:
- ✅ **Issue #11:** Configurable timeout handling (**COMPLETED & MERGED**)
- 🆕 **Issue #14:** Document-type aware chunking strategies (High priority)
- 🆕 **Issue #13:** Hybrid PDF parsing: VLM for datasheets, Docling for regular docs (Medium priority)
- 🆕 **Issue #15:** Proper table extraction and LlamaIndex node handling (Medium priority)
- 🔄 **Issue #12:** Page-level content classification (Medium priority)
- 🔄 **Issue #8:** Missing get_status() method (Low priority)
- 🔄 **Issue #5:** Qdrant server upgrade for performance (Low priority)

### Production Readiness Status:
- ✅ **Document Processing:** Full PDF→markdown pipeline working
- ✅ **Storage System:** JSONL artifacts created in `storage_data_v3/`
- ✅ **Indexing:** Both vector and keyword search operational
- ✅ **Queue System:** Enterprise-grade processing with lifecycle management
- ✅ **User Experience:** Consolidated CLI with full v2.1 feature parity

## Essential Commands

### Document Operations

**Production CLI** (Enhanced with Issue #9 features):
```bash
# Enhanced document processing with modes
uv run python -m src.pipeline_v3.cli_main add document.pdf --mode datasheet
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf" --mode auto --workers 3
uv run python -m src.pipeline_v3.cli_main add /docs --recursive --mode generic

# Custom prompts and URL support
uv run python -m src.pipeline_v3.cli_main add doc.pdf --prompt custom.md
uv run python -m src.pipeline_v3.cli_main add https://example.com/doc.pdf

# Search with hybrid vector+keyword search
uv run python -m src.pipeline_v3.cli_main search "laser sensors" --type hybrid --top-k 5

# Update/Remove documents  
uv run python -m src.pipeline_v3.cli_main update document.pdf --force
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
# Test document processing end-to-end
uv run python -m src.pipeline_v3.cli_main add data/sample_docs/labmax-touch-ds.pdf

# Verify storage artifacts created
ls storage_data_v3/  # Should show JSONL files with full UUIDs

# Test search functionality
uv run python -m src.pipeline_v3.cli_main search "laser power" --type hybrid
```

### Development Priorities (Updated):

#### **URGENT: Critical Regressions** 🚨
1. **Issue #16**: Restore chunking_metadata.py integration (CRITICAL)
   - Replace direct index_manager.add_document() calls with process_and_index_document()
   - Restore --with-keywords CLI parameter
   - Re-integrate MarkdownNodeParser for structure-aware chunking

2. **Issue #7**: Fix pair extraction parsing (HIGH)
   - Update parsers.py to extract complete JSON block, not just first line
   - Parse from "Metadata:" through closing "}" before "---" separator

#### **Next Development Cycle**
- 🔧 **Data Quality**: Document-type aware chunking and table extraction
- 🚀 **Performance**: Hybrid parsing approach (VLM + Docling)
- 🏗️ **Infrastructure**: System monitoring and performance optimization

## Key Configuration

Configuration via `config.yaml`:
- **OpenAI Models:** gpt-4o for vision, text-embedding-3-small for embeddings
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

### Monitoring & Diagnostics:
- Real-time queue status and performance metrics
- Document state tracking and lifecycle management
- Comprehensive system health checks and maintenance tools
- Structured logging with artifact preservation

## Important Notes ⚠️

- **Use uv from project root:** Critical for proper environment and imports
- **Primary CLI:** Use `cli_main.py` for production with full v2.1 feature parity
- **CRITICAL REGRESSION:** V3 missing keyword enhancement from chunking_metadata.py (Issue #16)
- **BROKEN FEATURE:** Pair extraction fails due to multi-line JSON parsing (Issue #7)
- **37 PDFs available:** Mix of simple and complex datasheets for comprehensive testing  
- **Storage isolation:** All v3 components use v3-specific paths to avoid conflicts
- **Production status:** Core processing works but retrieval quality degraded vs V2.1

## Documentation References

- **📖 Complete User Guide:** [USER_MANUAL.md](./USER_MANUAL.md)
- **🚀 Daily Commands:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)  
- **🏗️ Technical Details:** [README.md](./README.md)
- **📋 Development Status:** [DEVELOPMENT_STATUS.md](./DEVELOPMENT_STATUS.md)

**Current Focus:** **URGENT** - Fix critical regressions in V3. Priority 1: Restore keyword enhancement (Issue #16). Priority 2: Fix pair extraction (Issue #7). These block all other improvements and degrade retrieval quality vs V2.1.