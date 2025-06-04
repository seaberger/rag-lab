# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a datasheet ingestion and search pipeline that processes PDF datasheets and Markdown documents into a searchable vector database. The system extracts model/part number pairs from technical datasheets using OpenAI Vision API and provides hybrid search capabilities combining semantic and keyword matching.

## Core Architecture

The system follows a modular pipeline architecture:

- **Pipeline Core** (`pipeline/core.py`): Main ingestion pipeline with document classification, parsing, and indexing
- **Parsers** (`pipeline/parsers.py`): Document type detection and parsing logic for PDFs and Markdown
- **Storage Layer**: 
  - Vector embeddings in Qdrant (`storage/vector_store.py`)
  - BM25 keyword index in SQLite (`storage/keyword_index.py`) 
  - Document caching system (`storage/cache.py`)
- **Search Engine** (`search/`): Hybrid search combining vector similarity and keyword matching
- **Utils**: Configuration management, chunking, validation, and monitoring

## Key Configuration

The system is configured via `config.yaml` which controls:
- OpenAI API models and settings (gpt-4o for vision, text-embedding-3-small for embeddings)
- Qdrant vector store settings (path: `./qdrant_data`, collection: `datasheets`)
- Cache settings (enabled by default with 7-day TTL)
- Processing limits and batch settings

## Common Commands

```bash
# Install dependencies (from project root using uv)
uv sync

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

## Important Implementation Notes

- **Datasheet Processing**: Uses specialized prompt (`datasheet_parsing_prompt.md`) to extract model/part number pairs with cable type handling
- **Document Classification**: Three parsing modes - datasheet (with pair extraction), generic PDF, and Markdown (direct ingestion)
- **Error Handling**: The codebase contains many FIXME comments indicating incomplete implementations and placeholder code
- **Dependencies**: Requires Poppler utilities for PDF processing, OpenAI API access, and local Qdrant installation

## Development Workflow

- Configuration is centralized in `config.yaml` 
- All processed documents create artifacts in JSONL format for auditability
- Progress monitoring and error reporting built into pipeline
- Cache system prevents redundant API calls during development
- Vector embeddings use 1536 dimensions with OpenAI's text-embedding-3-small model

## 🎉 Phase 2 & 3 Complete: Production-Ready Pipeline ✅

**All Core Infrastructure Implemented:**

### ✅ **Phase 2: Document Processing (COMPLETED)**
- **LlamaIndex APIs Updated**: All imports verified and working with latest versions
- **Document Classification**: Robust classifier with confidence scoring and filename heuristics
- **PDF Processing**: Complete `_pdf_to_data_uris` implementation for OpenAI Vision API
- **Three Parsing Modes**: 
  - Markdown (direct ingestion, no API calls)
  - Datasheet PDF (with model/part number extraction)
  - Generic PDF (simple content extraction)
- **Configuration Integration**: All parsing paths use PipelineConfig for models, prompts, paths
- **Error Handling**: Comprehensive error handling with graceful degradation
- **Progress Monitoring**: Stage-by-stage tracking (classification, fetch, parsing, chunking, indexing)

### ✅ **Phase 3: Core Integration (COMPLETED)**
- **Keyword Generation**: Full implementation with batch processing and cost optimization
  - `KeywordGenerator` class with OpenAI integration
  - `batch_generate_keywords` for efficient processing
  - Configurable models and thresholds
- **Configuration Integration**: Removed all FIXME comments and hardcoded values
  - All modules now use PipelineConfig consistently
  - No more placeholder implementations
- **Working CLI**: Complete `cli_with_updated_doc_flow.py` implementation
  - Full argument parsing and validation
  - Async pipeline execution
  - Comprehensive error handling and logging

### 🏗️ **Ready-to-Run Components:**
- **`fetch_document`**: Handles URLs and local files with validation
- **`DatasheetArtefact`**: JSONL serialization with metadata and timestamps
- **`_resolve_prompt`**: File-based and fallback prompt loading
- **Complete Storage Layer**: Vector store, keyword index, and cache with config integration
- **End-to-End Pipeline**: From document ingestion to searchable index

### ✨ **Notebook-Inspired Improvements (COMPLETED)**
- **🛠️ Poppler Auto-Discovery**: Automatic detection of Poppler installation for PDF processing
- **⚡ OpenAI Responses API**: Upgraded from Chat Completions to Responses API for better multimodal handling
- **🎯 Enhanced Prompt Structure**: More explicit formatting instructions and better pair extraction
- **📁 Environment Setup**: Robust `.env` file discovery and API key validation
- **🔧 Configurable DPI**: PDF conversion quality configurable through config files

## Search Capabilities

Three search modes available:
- `hybrid`: Combines vector similarity and BM25 (recommended)
- `vector`: Pure semantic search using embeddings  
- `keyword`: BM25 full-text search only

Search results include relevance scores, document IDs, and text previews displayed in rich terminal tables.