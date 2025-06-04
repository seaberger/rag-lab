# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-ready datasheet ingestion and search pipeline that processes PDF datasheets and Markdown documents into a searchable vector database. The system extracts model/part number pairs from technical datasheets using OpenAI Vision API and provides hybrid search capabilities combining semantic and keyword matching.

## Core Architecture

The system follows a modular pipeline architecture with three distinct processing paths:

### Document Types & Processing
- **Datasheet PDFs** (`DocumentType.DATASHEET_PDF`): Extract model/part number pairs + convert to markdown using OpenAI Responses API
- **Generic PDFs** (`DocumentType.GENERIC_PDF`): Simple PDF → markdown conversion using OpenAI Vision API
- **Markdown files** (`DocumentType.MARKDOWN`): Direct file reading with optional keyword enhancement

### Pipeline Components
- **Pipeline Core** (`pipeline/core.py`): Main ingestion pipeline with document classification, parsing, caching, and indexing
- **Parsers** (`pipeline/parsers.py`): Document type detection and parsing logic with confidence scoring
- **Storage Layer**: 
  - Vector embeddings in Qdrant (`storage/vector_store.py`) with configurable embedding models
  - BM25 keyword index in SQLite (`storage/keyword_index.py`) for full-text search
  - JSON+LZ4 caching system (`storage/cache.py`) with content-based cache keys
- **Search Engine** (`search/`): Hybrid search combining vector similarity and BM25 keyword matching
- **Utils**: Configuration management, document chunking, keyword generation, validation, and monitoring

## Key Configuration

The system is configured via `config.yaml` which controls:
- OpenAI API models and settings (gpt-4o for vision, gpt-4o-mini for keywords, text-embedding-3-small for embeddings)
- Qdrant vector store settings (path: `./qdrant_data`, collection: `datasheets`, dimensions: 1536)
- Cache settings (enabled by default with 7-day TTL, LZ4 compression)
- Processing limits, batch settings, and retry logic

## Common Commands

```bash
# Install dependencies (from project root using uv)
uv sync

# Activate the virtual environment (REQUIRED before running any commands)
source .venv/bin/activate

# Set required environment variable
export OPENAI_API_KEY="sk-..."

# Run main ingestion pipeline
python cli_with_updated_doc_flow.py --src *.pdf --with_keywords --mode datasheet

# Search indexed documents  
python search/cli.py "query text" --mode hybrid --limit 5

# Run with different parsing modes
python cli_with_updated_doc_flow.py --src file.pdf --mode generic  # Generic PDF
python cli_with_updated_doc_flow.py --src file.md --mode auto     # Auto-detect
```

## Pipeline Processing Flow

### Document Flow Architecture
```
Input → Classification → Parsing → Caching → Document → Chunking → Keywords → Indexing
```

### Key Processing Steps
1. **Document Classification** (`DocumentClassifier.classify`): Determines processing method based on file extension and filename patterns
2. **Parsing Strategy Selection**: Routes to appropriate parser based on document type
3. **Content Extraction**: Uses OpenAI APIs for PDF processing or direct file reading for markdown
4. **Model/Part Pair Extraction**: For datasheets, extracts structured (model, part_number) tuples using JSON parsing with error handling
5. **Caching**: Stores parsed results with content-based cache keys to avoid redundant API calls
6. **Document Creation**: Creates LlamaIndex Document objects with comprehensive metadata
7. **Chunking**: Uses MarkdownNodeParser to preserve document structure
8. **Keyword Enhancement**: Optionally generates contextual keywords and **appends to node content** (Anthropic RAG best practice)
9. **Vector Indexing**: Creates searchable embeddings using configured OpenAI embedding model

## Important Implementation Notes

### ✅ **Production-Ready Features**
- **Datasheet Processing**: Uses specialized prompt (`datasheet_parsing_prompt.md`) to extract model/part number pairs with cable type handling
- **Document Classification**: Three parsing modes with confidence scoring and filename heuristics
- **Robust Error Handling**: Comprehensive exception handling with graceful degradation and retry logic
- **JSON Parsing**: Handles OpenAI response format inconsistencies (single vs double quotes)
- **Progress Monitoring**: Stage-by-stage tracking with detailed reporting
- **Dependencies**: Auto-discovery of Poppler utilities, robust OpenAI API integration

### ✅ **Advanced RAG Implementation**  
- **Keywords in Content**: Follows Anthropic's RAG best practices by appending keywords to node text content
- **Hybrid Search**: Combines vector similarity with BM25 keyword matching for optimal retrieval
- **Metadata Preservation**: Maintains document relationships, pair information, and processing metadata
- **Content-Based Caching**: Uses document content + prompt hash for intelligent cache invalidation

### ✅ **Storage & Artifacts**
- **JSONL Artifacts**: All processed documents create structured artifacts for auditability and debugging
- **JSON+LZ4 Caching**: Efficient compression with configurable TTL
- **Vector Database**: Qdrant integration with configurable dimensions and distance metrics
- **Keyword Index**: SQLite BM25 index for full-text search capabilities

## Development Workflow

- **Configuration**: Centralized in `config.yaml` with environment variable support
- **Monitoring**: Built-in progress tracking and performance reporting
- **Debugging**: Structured logging with artifact preservation
- **Testing**: Cache system allows rapid iteration during development
- **Modularity**: Clean separation of concerns across pipeline, storage, search, and utilities

## 🎉 Production Pipeline - Fully Operational ✅

### ✅ **Core Infrastructure (COMPLETED)**
- **LlamaIndex Integration**: All imports verified and working with latest versions
- **OpenAI APIs**: Responses API for multimodal processing, embedding API for vector creation
- **Document Processing**: Complete PDF→image→markdown pipeline with error recovery
- **Three Document Types**: Markdown (direct), Datasheet PDF (with pairs), Generic PDF (simple)
- **Configuration Management**: All components use centralized PipelineConfig
- **Progress Monitoring**: Real-time tracking with stage-by-stage performance metrics

### ✅ **Advanced Features (COMPLETED)**
- **Keyword Generation**: Full implementation with batch processing and cost optimization
  - Individual and batch keyword generation modes
  - Keywords appended to content for better retrieval (Anthropic best practice)
  - Configurable models and processing thresholds
- **Caching System**: Content-aware caching with compression and TTL management
- **Search Integration**: Hybrid search combining semantic and keyword matching
- **CLI Interface**: Complete command-line interface with argument validation and error handling

### ✅ **Production Enhancements (COMPLETED)**
- **Error Recovery**: Robust JSON parsing with quote normalization for OpenAI responses
- **Metadata Enhancement**: Comprehensive document metadata including file info, processing stats
- **Environment Setup**: Automatic .env discovery and API key validation
- **Dependency Management**: Auto-discovery of system utilities (Poppler) with fallback options
- **File Organization**: Clean module structure with outdated files moved to backups/

## Search Capabilities

Three search modes available via `search/cli.py`:
- **`hybrid`**: Combines vector similarity and BM25 keyword matching (recommended for best results)
- **`vector`**: Pure semantic search using OpenAI embeddings for conceptual matching
- **`keyword`**: BM25 full-text search for exact term matching

### Search Features
- **Rich Results**: Relevance scores, document IDs, source information, and text previews
- **Metadata Filtering**: Search within specific document types or sources
- **Configurable Limits**: Control number of results returned
- **Performance Optimized**: Efficient hybrid scoring and result ranking

### Example Search Usage
```bash
# Hybrid search (best for most queries)
python search/cli.py "PM10K power measurement accuracy" --mode hybrid --limit 5

# Vector search (conceptual matching)
python search/cli.py "laser sensor specifications" --mode vector --limit 3

# Keyword search (exact terms)
python search/cli.py "USB interface" --mode keyword --limit 5
```

## Active File Structure

### Core Pipeline Files
- `cli_with_updated_doc_flow.py` - Main CLI interface with argument parsing
- `config.yaml` - Centralized configuration for all components

### Pipeline Module (`pipeline/`)
- `core.py` - Main ingestion pipeline with document processing flow
- `parsers.py` - Document classification and parsing logic with OpenAI integration

### Storage Module (`storage/`)
- `cache.py` - JSON+LZ4 caching system with content-based keys
- `vector_store.py` - Qdrant vector database integration
- `keyword_index.py` - SQLite BM25 full-text search index

### Search Module (`search/`)
- `cli.py` - Search command-line interface
- `hybrid.py` - Hybrid search engine combining vector and keyword results

### Utils Module (`utils/`)
- `chunking_metadata.py` - Document→Node processing with keyword enhancement
- `config.py` - Configuration management and validation
- `common_utils.py` - Logging, retry logic, and utility functions
- `env_utils.py` - Environment setup and API key validation
- `monitoring.py` - Progress tracking and performance reporting
- `validation.py` - Input validation and error checking

### Backup Files (`backups/`)
- Contains outdated .py files moved during cleanup for reference

## Cache Management System

### Cache Components Architecture
The pipeline maintains multiple cache layers for performance and debugging:

| Component | Location | Purpose | Clear When |
|-----------|----------|---------|------------|
| **API Cache** | `cache/` | LZ4-compressed OpenAI responses | Change prompts/models |
| **Document Artifacts** | `storage_data/` | JSONL processing records | Reprocess documents |
| **Vector Database** | `qdrant_data/` | Searchable embeddings | Change embedding models |
| **Keyword Index** | `keyword_index.db` | BM25 search index | Rebuild search |
| **Reports/Logs** | `*.json`, `*.log` | Performance metrics | Fresh metrics needed |

### Cache Management Utility
Use `utils/cache_manager.py` for programmatic cache control:

```bash
# Check what's cached and sizes
python utils/cache_manager.py --status

# Clear everything for fresh start
python utils/cache_manager.py --clear-all --force

# Selective clearing
python utils/cache_manager.py --clear api storage --force
```

### Development Workflow Integration

**When testing prompt changes:**
```bash
python utils/cache_manager.py --clear api --force
python cli_with_updated_doc_flow.py --src test.pdf --mode datasheet
```

**When changing embedding models:**
```bash
python utils/cache_manager.py --clear vector keyword --force
# Update config.yaml with new embedding model
python cli_with_updated_doc_flow.py --src *.pdf --mode datasheet
```

**When debugging processing issues:**
```bash
python utils/cache_manager.py --clear storage --force
# Forces artifact regeneration without API calls
```

### Cache Location Resolution
- Paths are relative to execution directory (usually project root)
- Use `--status` to verify actual locations before clearing
- Cache keys use content hashes, so file modifications invalidate cache automatically

### Cache Benefits
- **API Cost Reduction**: Avoids redundant OpenAI calls during development
- **Development Speed**: Instant reprocessing with cached parsing results  
- **Debugging Support**: JSONL artifacts preserve all processing stages
- **Version Control**: Content-based keys handle file modifications automatically