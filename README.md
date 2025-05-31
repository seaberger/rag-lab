# 📚 Datasheet Ingestion Pipeline

A production-ready ETL pipeline that ingests PDF datasheets and Markdown documents into a searchable vector database with hybrid search capabilities.

## ✨ Key Features

- **Multi-format Support**: PDF datasheets, generic PDFs, and Markdown files
- **Intelligent Parsing**: 
  - Extracts model/part number pairs from datasheets using OpenAI Vision API
  - Direct Markdown ingestion without API calls
- **Hybrid Search**: Combines vector embeddings (semantic) with BM25 (keyword) search
- **Production Ready**: Caching, progress tracking, error handling, and retry logic
- **Cost Optimized**: Disk-based caching to avoid redundant API calls

## 🚀 Quick Start

### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt

# Install Poppler for PDF processing
# macOS
brew install poppler
# Ubuntu  
sudo apt-get install poppler-utils

# Set OpenAI API key
export OPENAI_API_KEY="sk-..."
```

### Basic Usage

```bash
# Process PDF datasheets with keyword augmentation
python datasheet_ingest_pipeline.py --src *.pdf --with_keywords

# Process mixed document types
python datasheet_ingest_pipeline.py --src docs/*.pdf docs/*.md

# Search the indexed documents
python search_cli.py "PM10K laser sensor" --mode hybrid --limit 10
```

## 📁 Project Structure

```
datasheet-ingestion-pipeline/
├── datasheet_ingest_pipeline.py    # Main pipeline
├── search_cli.py                   # Search interface
├── hybrid_search.py                # Combined search
├── keyword_index.py                # BM25 indexing
├── cache_manager.py                # Document caching
├── progress_monitor.py             # Progress tracking
├── config.yaml                     # Configuration
├── artefacts/                      # Processed documents
├── qdrant_data/                    # Vector embeddings
└── cache/                          # Cached parsed docs
```

## 🔧 Configuration

Edit `config.yaml` to customize:

- API models and retry settings
- Cache and batch processing options
- File size and validation limits
- Search parameters

## 📊 Data Flow

```
PDF/Markdown → Parse → Extract Pairs → Chunk → Keywords → Embed → Index → Search
```

## 🔍 Search Modes

- **Hybrid**: Combines vector and keyword search (recommended)
- **Vector**: Semantic search using embeddings
- **Keyword**: BM25 full-text search

## 📝 Example Usage

```bash
# Batch process from file list
python datasheet_ingest_pipeline.py --src @urls.txt --with_keywords

# Search by part number
python search_cli.py "2293937" --mode keyword

# Semantic concept search
python search_cli.py "high precision optical measurement" --mode vector
```

## 🛠 Requirements

- Python 3.8+
- OpenAI API key
- Poppler utilities
- 2GB+ disk space for vector storage

## 📖 Documentation

See the documentation files for detailed information:
- `datasheet_ingest_overview.md` - Pipeline architecture
- `updated_document_ingestion_pipeline.md` - Enhanced features

## 📄 License

[MIT](https://choosealicense.com/licenses/mit/)

---

**Note**: This pipeline is optimized for technical datasheets but works with any PDF or Markdown content.