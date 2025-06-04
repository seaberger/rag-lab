# Datasheet Ingestion Pipeline

A production-ready document processing pipeline that converts technical datasheets and PDFs into a searchable vector database with model/part number extraction and hybrid search capabilities.

## Architecture Overview

This pipeline follows a modular architecture with three main processing paths:
- **Datasheet PDFs**: Extract model/part number pairs + convert to markdown
- **Generic PDFs**: Simple PDF → markdown conversion  
- **Markdown files**: Direct ingestion with optional keyword enhancement

## Quick Start

### 1. Environment Setup
```bash
# Install dependencies (from project root using uv)
uv sync

# Activate the virtual environment (REQUIRED before running any commands)
source .venv/bin/activate

# Set required environment variable
export OPENAI_API_KEY="sk-..."
```

### 2. Run the Pipeline

#### Process Documents
```bash
# Process a datasheet PDF with model/part extraction
python cli_with_updated_doc_flow.py --src datasheet.pdf --mode datasheet --with_keywords

# Process generic PDF without pair extraction
python cli_with_updated_doc_flow.py --src document.pdf --mode generic

# Auto-detect document type
python cli_with_updated_doc_flow.py --src file.pdf --mode auto

# Process markdown files directly
python cli_with_updated_doc_flow.py --src document.md --with_keywords
```

#### Search Indexed Documents
```bash
# Hybrid search (recommended)
python search/cli.py "PM10K laser sensor specifications" --mode hybrid --limit 5

# Vector-only search
python search/cli.py "power measurement" --mode vector --limit 3

# Keyword-only search
python search/cli.py "USB interface" --mode keyword --limit 5
```

## Core Components

### Pipeline Architecture
```
Input → Classification → Parsing → Caching → Document → Chunking → Keywords → Indexing
```

### Active Files Structure
```
├── cli_with_updated_doc_flow.py     # Main CLI interface
├── config.yaml                     # Pipeline configuration
├── pipeline/
│   ├── core.py                     # Main ingestion pipeline
│   └── parsers.py                  # Document classification & parsing
├── storage/
│   ├── cache.py                    # JSON+LZ4 caching system
│   ├── vector_store.py             # Qdrant vector storage
│   └── keyword_index.py            # BM25 keyword index
├── search/
│   ├── cli.py                      # Search CLI
│   └── hybrid.py                   # Hybrid search engine
├── utils/
│   ├── chunking_metadata.py        # Document→Node processing
│   ├── config.py                   # Configuration management
│   ├── common_utils.py             # Logging & utilities
│   ├── env_utils.py                # Environment setup
│   ├── monitoring.py               # Progress tracking
│   └── validation.py               # Input validation
└── backups/                        # Outdated files (moved here)
```

## Document Processing Flow

### 1. Classification (`pipeline/parsers.py`)
```python
DocumentType.DATASHEET_PDF   # → Model/part extraction + markdown
DocumentType.GENERIC_PDF     # → Simple markdown conversion  
DocumentType.MARKDOWN        # → Direct processing
```

### 2. Parsing Methods
- **Datasheet PDFs**: OpenAI Responses API with structured prompts for pair extraction
- **Generic PDFs**: OpenAI Vision API for markdown conversion
- **Markdown**: Direct file reading

### 3. Model/Part Number Extraction
For datasheets, extracts structured pairs like:
```python
[("PM10K+ USB", "2293937"), ("PM30 RS-232", "1174258")]
```

### 4. Keyword Enhancement (Anthropic RAG Best Practice)
When `--with_keywords` is enabled:
- Generates contextual keywords using OpenAI GPT-4o-mini
- **Appends keywords to node content** (not just metadata) for better retrieval
- Format: `\n\n---\nKeywords: technical, laser, power, sensor, USB`

### 5. Caching System
- **Format**: JSON with LZ4 compression (not pickle files)
- **Location**: `./cache/{doc_hash}_{prompt_hash}.cache`
- **TTL**: 7 days (configurable)
- **Key**: Hash of document content + prompt

### 6. Storage Formats
- **Artifacts**: JSONL files in `./storage_data/{doc_id}.jsonl`
- **Vector DB**: Qdrant database in `./qdrant_data/`
- **Keyword Index**: SQLite BM25 index in `./keyword_index.db`

## Cache Management

### Cache Components Overview
The pipeline creates several cache and storage components:

| Component | Location | Purpose | Format |
|-----------|----------|---------|---------|
| **API Cache** | `./cache/` | OpenAI API responses | LZ4-compressed JSON |
| **Storage Artifacts** | `./storage_data/` | Processed documents | JSONL files |
| **Vector Database** | `./qdrant_data/` | Embeddings & search index | Qdrant binary |
| **Keyword Index** | `./keyword_index.db` | BM25 full-text search | SQLite database |
| **Processing Reports** | `./processing_report.json` | Pipeline performance metrics | JSON |
| **Pipeline Logs** | `./pipeline.log` | Execution logs | Plain text |

### Cache Status and Clearing

#### Check Cache Status
```bash
# View current cache status and sizes
python utils/cache_manager.py --status
```

#### Clear All Cache (Fresh Start)
```bash
# Clear everything - use for complete reset
python utils/cache_manager.py --clear-all

# Skip confirmation prompt
python utils/cache_manager.py --clear-all --force
```

#### Selective Cache Clearing
```bash
# Clear only API cache (force fresh parsing)
python utils/cache_manager.py --clear api --force

# Clear documents but keep vector database
python utils/cache_manager.py --clear storage --force

# Clear vector database and keyword index
python utils/cache_manager.py --clear vector keyword --force

# Clear logs and reports
python utils/cache_manager.py --clear logs reports --force
```

#### Available Components for Selective Clearing
- `api`, `cache` - API response cache (LZ4 files)
- `storage`, `artifacts` - Document artifacts (JSONL files)  
- `vector`, `qdrant` - Vector database
- `keyword`, `bm25` - Keyword search index
- `logs`, `reports` - Processing logs and reports

### When to Clear Cache

**🔄 Force Fresh Processing:**
```bash
# Process document with fresh API calls
python utils/cache_manager.py --clear api --force
python cli_with_updated_doc_flow.py --src document.pdf --mode datasheet
```

**🗄️ Reset Vector Database:**
```bash
# Rebuild search index with new embeddings
python utils/cache_manager.py --clear vector keyword --force
python cli_with_updated_doc_flow.py --src *.pdf --mode datasheet
```

**🧹 Complete Reset:**
```bash
# Start completely fresh
python utils/cache_manager.py --clear-all --force
```

### Cache Location Notes
- All paths are relative to where you run the CLI command
- If running from project root: cache appears in `./cache/`, `./storage_data/`, etc.
- If running from pipeline directory: cache appears relative to that location
- Use `--status` to verify actual cache locations before clearing

## Configuration

### config.yaml Structure
```yaml
pipeline:
  max_concurrent: 5
  timeout_seconds: 300

openai:
  vision_model: gpt-4o              # For PDF parsing
  keyword_model: gpt-4o-mini        # For keyword generation
  embedding_model: text-embedding-3-small
  dimensions: 1536

qdrant:
  path: ./qdrant_data
  collection_name: datasheets

cache:
  enabled: true
  directory: ./cache
  ttl_days: 7
  compress: true
```

## Example Output

### Document Artifact (JSONL)
```json
{
  "doc_id": "pm10k-plus-ds_95197d94_f7448efb",
  "source": "data/sample_docs/pm10k-plus-ds.pdf",
  "pairs": [["PM10K+ USB", "2293937"], ["PM10K+ RS-232", "2293938"]],
  "markdown": "# PM10K+ LASER POWER SENSOR\n\n## Specifications...",
  "metadata": {
    "source_type": "datasheet_pdf",
    "extracted_pairs": 2,
    "file_name": "pm10k-plus-ds.pdf",
    "file_size": 487239,
    "content_length": 4565,
    "parse_method": "openai_vision"
  },
  "created_at": "2025-06-04T11:52:22.536286",
  "markdown_length": 4565,
  "pairs_count": 2
}
```

### Search Results
```json
{
  "results": [
    {
      "node_id": "pm10k_chunk_1",
      "score": 0.892,
      "text": "PM10K+ specifications include USB interface...\n\n---\nKeywords: laser, power, sensor, USB, specifications",
      "metadata": {
        "doc_id": "pm10k-plus-ds_95197d94_f7448efb",
        "pairs": [["PM10K+ USB", "2293937"]],
        "chunk_index": 1
      }
    }
  ]
}
```

## Key Features

### ✅ Production Ready
- Comprehensive error handling and retry logic
- Progress monitoring with detailed reporting
- Configurable timeouts and batch processing
- Full logging with structured output

### ✅ OpenAI Integration
- Uses latest Responses API for multimodal processing
- Automatic model selection from configuration
- Rate limiting and error handling
- Cost-optimized keyword generation

### ✅ Advanced RAG Implementation
- **Keywords in content** (Anthropic best practice)
- Hybrid search combining vector similarity + BM25
- Structured metadata for enhanced filtering
- Preserves document relationships and pairs

### ✅ Robust Caching
- Content-based cache keys (handles file modifications)
- LZ4 compression for efficiency
- Configurable TTL and cleanup
- Cache hit reporting

### ✅ Document Type Intelligence
- Automatic classification by filename patterns
- Confidence scoring for classification decisions
- Support for manual mode override
- Extensible classification rules

## Search Capabilities

### Hybrid Search (Recommended)
Combines vector similarity with keyword matching for optimal results:
```bash
python search/cli.py "PM10K power measurement accuracy" --mode hybrid --limit 5
```

### Vector Search
Pure semantic search using embeddings:
```bash
python search/cli.py "laser sensor specifications" --mode vector --limit 3
```

### Keyword Search
BM25 full-text search:
```bash
python search/cli.py "USB interface" --mode keyword --limit 5
```

## Troubleshooting

### Common Issues

**Import Errors**: Ensure virtual environment is activated
```bash
source .venv/bin/activate
```

**PDF Processing**: Install Poppler utilities
```bash
# macOS
brew install poppler

# Ubuntu/Debian  
sudo apt-get install poppler-utils
```

**OpenAI API**: Verify API key and model access
- Key format: `sk-proj_...` or `sk-...`
- Required models: `gpt-4o`, `text-embedding-3-small`
- Check rate limits and quotas

**Dependency Issues**: Install missing package
```bash
uv add package-name
```

## Development

### Adding New Document Types
1. Add enum to `DocumentType` in `pipeline/parsers.py`
2. Implement classification logic in `DocumentClassifier`
3. Add parsing function following existing patterns
4. Update configuration and documentation

### Extending Search
1. Modify `search/hybrid.py` for new search modes
2. Add CLI options in `search/cli.py`
3. Update result formatting and ranking

### Custom Prompts
1. Create prompt file (e.g., `custom_prompt.md`)
2. Use `--prompt custom_prompt.md` flag
3. Follow existing prompt structure for consistency

## Next Steps

The extracted content can be integrated into:
- **Enterprise Search**: Full-text and semantic search across technical documents
- **Product Catalogs**: Automated part number and specification extraction
- **Knowledge Bases**: Structured technical documentation systems
- **API Services**: RESTful interfaces for document queries
- **Analytics**: Document processing and extraction reporting