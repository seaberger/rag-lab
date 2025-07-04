# RAG Lab - Document Processing Pipeline 🚀

A production-ready RAG pipeline that ingests real-world documents (PDF, Word, PowerPoint), extracts structured content using OpenAI's Vision API, and serves fast, citation-backed answers via a hybrid vector + keyword search system. Features include intelligent change detection, queue-based batch processing, and comprehensive CLI tools for document lifecycle management.

[![Pipeline v3 CI](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml/badge.svg)](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml)
[![Tests](https://img.shields.io/badge/tests-169%2F176%20passing-yellow)](./src/pipeline_v3/tests/)
[![Coverage](https://img.shields.io/badge/coverage-12%25-red)](./src/pipeline_v3/tests/)
[![Documentation](https://img.shields.io/badge/docs-complete-blue)](./src/pipeline_v3/USER_MANUAL.md)

## 🎯 Overview

RAG Lab is a comprehensive document processing pipeline designed for handling technical documentation at scale. It combines OpenAI's Vision API for document analysis with a hybrid vector/keyword search system, providing intelligent document lifecycle management and enterprise-ready features.

### Key Features

- **🔄 Intelligent Queue Management** - Scalable concurrent processing with job persistence
- **📄 Multi-Format Support** - PDF, Word (.docx), PowerPoint (.pptx), and URL batch processing
- **🔍 Hybrid Search** - Combined vector and keyword search with adaptive fusion
- **🎯 Smart Change Detection** - 6 types of document change tracking with intelligent updates
- **📊 Enterprise Features** - Office document support, page range processing, and batch operations
- **🛡️ Production Ready** - Comprehensive error handling, retry logic, and monitoring

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.11 or 3.12 required
# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/seaberger/rag-lab.git
cd rag-lab

# Install dependencies
uv sync

# Set up environment variables
echo "OPENAI_API_KEY=your-key-here" > .env
```

### Basic Usage

```bash
# Navigate to Pipeline v3
cd src/pipeline_v3

# Process documents
uv run python -m src.pipeline_v3.cli_main add document.pdf --with-keywords

# Search documents
uv run python -m src.pipeline_v3.cli_main search "laser sensors" --type hybrid

# Check system status
uv run python -m src.pipeline_v3.cli_main status --detailed
```

### Production Usage

For production workloads and batch processing:

```bash
# Start the queue system
uv run python -m src.pipeline_v3.cli_main queue start --workers 4

# Process multiple documents
uv run python -m src.pipeline_v3.cli_main add "docs/*.pdf" --with-keywords

# Monitor progress
uv run python -m src.pipeline_v3.cli_main queue status --watch
```

## 📚 Documentation

- **[User Manual](./src/pipeline_v3/USER_MANUAL.md)** - Complete guide with examples
- **[Quick Reference](./src/pipeline_v3/QUICK_REFERENCE.md)** - Command cheat sheet
- **[Architecture](./src/pipeline_v3/docs/architecture.md)** - Technical design details
- **[Queue System Guide](./src/pipeline_v3/docs/QUEUE_SYSTEM_GUIDE.md)** - Production deployment guide

## 🏗️ Architecture Overview

The system uses a modular architecture with clear separation of concerns:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   CLI Interface │────▶│ Enhanced Pipeline │────▶│  Index Manager  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │                       │                         │
         ▼                       ▼                         ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  Document Queue │     │  Change Detector  │     │  Vector Store   │
└─────────────────┘     └──────────────────┘     │  Keyword Index  │
                                                  └─────────────────┘
```

### Core Components

- **EnhancedPipeline** - Main orchestrator with queue integration
- **DocumentRegistry** - Central state tracking and consistency
- **IndexManager** - Manages both vector and keyword indexes
- **ChangeDetector** - Intelligent document lifecycle management
- **DocumentQueue** - Async processing with configurable concurrency

## 🔧 Advanced Features

### Document Processing Options

```bash
# Process with custom document type
uv run python -m src.pipeline_v3.cli_main add manual.pdf --mode manual

# Page range processing
uv run python -m src.pipeline_v3.cli_main add large_doc.pdf --pages "1-10,50-60"

# Batch URL processing
uv run python -m src.pipeline_v3.cli_main add dummy --url-file urls.json

# Directory processing with filters
uv run python -m src.pipeline_v3.cli_main add /docs --recursive --include "*.pdf"
```

### Search Capabilities

```bash
# Hybrid search (recommended)
uv run python -m src.pipeline_v3.cli_main search "power measurement" --type hybrid

# Pure vector search
uv run python -m src.pipeline_v3.cli_main search "laser concepts" --type vector

# Keyword search with filters
uv run python -m src.pipeline_v3.cli_main search "USB interface" --type keyword --top-k 10
```

### System Management

```bash
# Run maintenance checks
uv run python -m src.pipeline_v3.cli_main maintenance --repair

# Configure system
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 8

# Export search results
uv run python -m src.pipeline_v3.cli_main search "sensors" --output results.json
```

## 🧪 Testing

The project includes comprehensive test coverage:

```bash
# Run all tests
uv run pytest src/pipeline_v3/tests/

# Run specific test categories
uv run pytest src/pipeline_v3/tests/unit/        # Unit tests
uv run pytest src/pipeline_v3/tests/integration/ # Integration tests
uv run pytest src/pipeline_v3/tests/security/    # Security tests
```

## 🤝 Contributing

Contributions are welcome! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup

```bash
# Install development dependencies
uv sync --all-extras --dev

# Run linters
uv run ruff check src/pipeline_v3
uv run black src/pipeline_v3

# Run tests with coverage
uv run pytest --cov=src.pipeline_v3
```

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- OpenAI for the Vision API and embeddings
- Qdrant for vector storage capabilities
- The Python community for excellent libraries

---

For more information, visit the [project documentation](./src/pipeline_v3/USER_MANUAL.md) or check out our [GitHub repository](https://github.com/seaberger/rag-lab).
