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

### ✅ Recently Resolved Critical Issues:

- ✅ **Issue #45:** URL Batch Processing (**COMPLETED**) 
  - Added comprehensive URL batch processing capabilities for enterprise workflows
  - Process collections of web documents from markdown/JSON files
  - New CLI batch commands: create-url-file, validate-urls, test-queue
  - Enhanced --url-file parameter for add command
  - Full integration with existing pipeline and queue system

- ✅ **Issue #27:** Cross-System Consistency Guarantees (**COMPLETED & MERGED**)
  - Implemented TransactionCoordinator with two-phase commit protocol
  - Added ConsistencyChecker for cross-system verification and repair planning
  - Prevents data corruption across multiple storage systems (SQLite, Qdrant, JSONL)
  - Distributed transaction-like behavior with automatic rollback on failures

- ✅ **Issues #20 & #21:** Vector indexing with keywords + doc_id consistency (**COMPLETED & MERGED**)
  - Fixed vector indexing failing when using --with-keywords flag
  - Resolved doc_id mismatch between keyword and vector indexes
  - Root cause: Document constructor not setting doc_id parameter correctly
  - All keyword-enhanced documents now properly indexed in vector store

- ✅ **Issue #16:** Restore chunking_metadata.py integration (**COMPLETED & MERGED**)
  - Fixed storage artifacts to contain keyword-enhanced markdown
  - Moved artifact creation to after keyword generation in pipeline
  - Storage JSONL files now include keywords when --with-keywords is used
  - Restored search quality improvement per Anthropic RAG best practices

- ✅ **Issue #7:** Fix model/part number pair extraction (**COMPLETED & MERGED**)
  - Fixed multi-line JSON metadata parsing in both V2.1 & V3
  - Now correctly parses complete JSON block from "Metadata:" to "---" separator
  - All datasheet pair extraction now working correctly

- ✅ **Issue #19:** Vector index deletion validation error (**COMPLETED & MERGED**)
  - Fixed QdrantVectorStore.delete() API usage for proper document updates
  - Eliminated MatchValue validation errors during reindexing

- ✅ **Issue #20:** Vector addition fails with --with-keywords (**COMPLETED & MERGED**)
  - Fixed Qdrant storage conflicts from multiple IndexManager instances
  - Vector indexing now works correctly with keyword enhancement

- ✅ **Issue #17:** Keyword generation JSON parsing failure (**COMPLETED & MERGED**)
  - Fixed OpenAI API response parsing (markdown code blocks around JSON)
  - Keyword generation now works perfectly with all OpenAI models
  - Enhanced search quality through proper keyword augmentation

- ✅ **Issue #26:** Database Schema Versioning and Migration Framework (**COMPLETED**)
  - Implemented comprehensive MigrationManager with version tracking and rollback
  - Created DatabaseBase class with automatic migration integration
  - Added initial schema migrations for all 4 databases (registry, fingerprints, keyword_index, jobs)
  - Built transaction-safe migration execution with checksum verification
  - Comprehensive test suite (unit, integration, regression tests)
  - Enables safe system evolution and prevents data loss on upgrades

### 🔄 Current Active Issues:

#### **IMMEDIATE NEXT: Production Readiness** 🚀
**Current Priority**: OpenAI API Integration Hardening (Issues #28 & #29)
- Bulletproof AI client with exponential backoff and circuit breaker patterns
- Production-ready API operations with proper timeout handling
- Core AI functionality reliability improvements

#### **PRODUCTION READINESS PIPELINE** 🚨
**Progress Update**: ✅ Issues #25, #26, #27 completed - Reliability & Robustness next!
- **✅ Issue #27**: Cross-System Consistency Guarantees (**COMPLETED**)
  - ✅ Implemented distributed transaction-like behavior with rollback capabilities
  - ✅ Prevents data corruption across storage systems (SQLite, Qdrant, JSONL)
  - ✅ ConsistencyChecker provides cross-system verification and repair planning
  
- **Issues #28 & #29:** OpenAI API Integration Hardening (**ROBUSTNESS**)
  - **Impact**: Makes the system production-ready for AI operations
  - **Why Critical**: Core AI functionality has initialization and timeout issues
  - **Deliverable**: Bulletproof OpenAI client with exponential backoff and circuit breaker patterns

#### **HIGH Priority Feature Issues** 🔥
- **Issue #7:** Fix model/part number pair extraction
  - Multi-line JSON metadata parsing broken
  - All datasheet pair extraction currently failing
  
- **Issue #14:** Document-type aware chunking strategies (Medium priority)
- **Issue #13:** Hybrid PDF parsing: VLM for datasheets, Docling for regular docs (Medium priority)

#### **Enhancement Issues** 🆕
- **Issue #21:** doc_id mismatch between keyword and vector indexes (Low priority)
- **Issue #15:** Proper table extraction and LlamaIndex node handling (Medium priority)
- **Issue #12:** Page-level content classification (Medium priority)
- **Issue #8:** Missing get_status() method (Low priority)
- **Issue #5:** Qdrant server upgrade for performance (Low priority)

#### **📋 Comprehensive Architecture Review**
**28 Fundamental Gaps Identified**: See [../../ISSUES.md](../../ISSUES.md)
- Security vulnerabilities (SQL injection, SSRF, path traversal)
- Error handling architecture gaps
- Data persistence and backup missing
- Configuration management issues
- Testing infrastructure deficiencies  
- Observability and monitoring absent

### Production Readiness Status:

#### **✅ Core Functionality Complete:**
- ✅ **Document Processing:** Full PDF→markdown pipeline working with OpenAI Vision API
- ✅ **Storage System:** JSONL artifacts created in `storage_data_v3/`
- ✅ **Indexing:** Both vector and keyword search fully operational
- ✅ **Keyword Enhancement:** --with-keywords integration restored and working
- ✅ **Queue System:** Enterprise-grade processing with lifecycle management
- ✅ **User Experience:** Consolidated CLI with full v2.1 feature parity

#### **⚠️ Production Gaps Identified:**
- ❌ **Error Handling:** No top-level exception handling (Issue #25)
- ✅ **Data Safety:** Database migration framework implemented (Issue #26) ✅
- ❌ **Data Consistency:** Cross-system transaction failures (Issue #27)
- ❌ **Security:** Multiple vulnerabilities identified (SQL injection, SSRF, path traversal)
- ❌ **Testing:** No formal testing framework or CI/CD
- ❌ **Monitoring:** No observability infrastructure (metrics, tracing, health checks)
- ❌ **Backup/Recovery:** No data backup or disaster recovery capabilities

#### **🎯 Development Status Assessment:**
**Current State**: Core functionality complete + error handling + database migration framework  
**Feature Development**: Ready to expand with Word & PPT document support  
**Production Pipeline**: Reliability & robustness improvements (Issues #27-29) for enterprise deployment  
**Recent Progress**: ✅ Error handling (Issue #25) + database schema versioning (Issue #26) completed

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

### Development Priorities (Updated):

#### **Next Development Sprint** 🎯
1. **✅ Word & PPT Document Support**: (**COMPLETED**)
   - ✅ Microsoft Office format support implemented
   - ✅ Enterprise document workflow foundation established
   - ✅ .docx and .pptx files now supported alongside PDFs

2. **✅ Issue #27**: Cross-System Consistency Guarantees (**COMPLETED**)
   - ✅ Distributed transaction-like behavior with rollback implemented
   - ✅ Prevents data corruption across storage systems

3. **Issues #28 & #29**: OpenAI API Integration Hardening (**IMMEDIATE NEXT**)
   - Bulletproof AI client with circuit breaker patterns
   - Production-ready API operations with proper error handling

#### **Future Enhancement Cycle** 🚀
- 🔧 **Data Quality**: Document-type aware chunking strategies (Issue #14)
- 🚀 **Performance**: Hybrid parsing approach - VLM + Docling (Issue #13)
- 📊 **Data Integrity**: Fix doc_id consistency between indexes (Issue #21)
- 🏗️ **Infrastructure**: Table extraction and system monitoring

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

## Important Notes ⚠️

- **Use uv from project root:** Critical for proper environment and imports
- **Primary CLI:** Use `cli_main.py` for production with full v2.1 feature parity
- **Keyword Enhancement:** --with-keywords now working, use for better search quality
- **CLI Workaround:** For update with keywords, use `add --force` until Issue #18 resolved
- **37 PDFs available:** Mix of simple and complex datasheets for comprehensive testing  
- **Storage isolation:** All v3 components use v3-specific paths to avoid conflicts
- **Production status:** Full functionality restored with enhanced search capabilities

## Documentation References

- **📖 Complete User Guide:** [USER_MANUAL.md](./USER_MANUAL.md)
- **🚀 Daily Commands:** [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)  
- **🏗️ Technical Details:** [README.md](./README.md)
- **📋 Development Status:** [DEVELOPMENT_STATUS.md](./DEVELOPMENT_STATUS.md)
- **🆕 Page Range Feature:** [docs/PAGE_RANGE_FEATURE.md](./docs/PAGE_RANGE_FEATURE.md)
- **🆕 API Hardening:** [docs/API_HARDENING.md](./docs/API_HARDENING.md)

**Current Focus:** **FEATURE EXPANSION & RELIABILITY** - Core functionality + error handling + database migrations complete. Next: Word & PPT support, then reliability & robustness improvements (Issues #27-29). See [../../ISSUES.md](../../ISSUES.md) for comprehensive development roadmap.