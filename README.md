# RAG Lab - Enterprise Document Intelligence Engine 🚀

[![CI/CD Pipeline](https://github.com/seaberger/rag-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/seaberger/rag-lab/actions/workflows/ci.yml)
[![Pipeline v3 CI](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml/badge.svg)](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml)
[![Tests](https://img.shields.io/badge/tests-96%25%20passing-brightgreen)](./src/pipeline_v3/tests/)
[![Coverage](https://img.shields.io/badge/coverage-12%25-yellow)](./src/pipeline_v3/tests/)
[![Documentation](https://img.shields.io/badge/docs-comprehensive-blue)](./src/pipeline_v3/USER_MANUAL.md)

## 🎯 Vision

RAG Lab is a production-ready document intelligence engine designed to transform how SMBs and enterprises interact with their technical documentation. By combining state-of-the-art AI models with enterprise-grade infrastructure, RAG Lab enables organizations to instantly access and understand complex technical information across thousands of documents.

### Why RAG Lab?

In today's knowledge economy, critical business information is trapped in PDFs, datasheets, manuals, and presentations. RAG Lab liberates this information, making it instantly searchable, intelligently retrievable, and contextually understandable.

## 🏢 Enterprise-Grade Capabilities

### 🔍 **Intelligent Document Processing**
- **Multi-Modal AI Analysis**: Leverages OpenAI's Vision API to understand documents as humans do - tables, diagrams, text, and layout
- **Format Agnostic**: Seamlessly processes PDFs, Word documents, PowerPoint presentations, and web content
- **Structured Data Extraction**: Automatically identifies and extracts model numbers, part numbers, specifications, and relationships
- **Context Preservation**: Maintains document structure, relationships, and metadata throughout processing

### 🚀 **Production-Ready Infrastructure**
- **Scalable Queue Architecture**: Concurrent processing with job persistence, automatic retries, and resource management
- **Enterprise Search**: Hybrid vector + keyword search with adaptive fusion for optimal retrieval
- **Change Intelligence**: 6 types of document change detection with smart differential updates
- **Database Migration Framework**: Safe schema evolution with versioning and rollback support

### 🛡️ **Reliability & Performance**
- **Comprehensive Error Handling**: Multi-layer retry logic, graceful degradation, and detailed error reporting
- **Real-Time Monitoring**: Performance metrics, queue status, and system health tracking
- **API Cost Optimization**: Intelligent caching, batch processing, and request optimization
- **Production Hardening**: Rate limiting, timeout management, and resource pooling

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Enterprise Application Layer                  │
├─────────────────────────────────────────────────────────────────┤
│   Web UI   │   REST API   │   CLI Tools   │   Integrations     │
├─────────────────────────────────────────────────────────────────┤
│                  Document Intelligence Engine                    │
├─────────────────────────────────────────────────────────────────┤
│  Enhanced Pipeline  │  Change Detection  │  Index Management    │
├─────────────────────────────────────────────────────────────────┤
│                    Queue & Job Management                        │
├─────────────────────────────────────────────────────────────────┤
│  Async Workers  │  Job Storage  │  Progress Tracking  │  Retry  │
├─────────────────────────────────────────────────────────────────┤
│                      Storage Layer                               │
├─────────────────────────────────────────────────────────────────┤
│  Vector Store  │  Keyword Index  │  Document Registry  │  Cache │
├─────────────────────────────────────────────────────────────────┤
│                    External Services                             │
├─────────────────────────────────────────────────────────────────┤
│        OpenAI APIs       │        Qdrant        │      S3       │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

#### **Document Intelligence Engine**
- **EnhancedPipeline**: Orchestrates document processing with queue integration and lifecycle management
- **Multi-Modal Parser**: Uses OpenAI Vision API for intelligent document understanding
- **Metadata Extractor**: Identifies technical specifications, model numbers, and relationships
- **Change Detector**: Tracks 6 types of document changes for efficient updates

#### **Search & Retrieval System**
- **Hybrid Search Engine**: Combines semantic understanding with keyword precision
- **Vector Store**: Qdrant server-based embeddings for conceptual search (scalable, production-ready)
- **BM25 Index**: SQLite FTS5 for exact match and technical term retrieval
- **Fusion Algorithms**: Adaptive scoring for optimal result ranking

#### **Production Infrastructure**
- **Async Queue System**: Handles unlimited document volumes with configurable concurrency
- **Job Persistence**: SQLite-based job storage survives system restarts
- **Registry System**: Central source of truth for document state and metadata
- **Migration Framework**: Safe database schema evolution and rollback

## 🚀 Quick Start

### Prerequisites

```bash
# Python 3.11 or 3.12 required
# Install uv package manager (faster than pip)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone https://github.com/seaberger/rag-lab.git
cd rag-lab

# Install dependencies
uv sync

# Configure OpenAI API
echo "OPENAI_API_KEY=your-key-here" > .env

# Start Qdrant vector database server (REQUIRED)
./scripts/qdrant_server.sh start
# Dashboard available at: http://localhost:6333/dashboard
```

### Basic Usage

```bash
# Process a single document
uv run python -m src.pipeline_v3.cli_main add technical_manual.pdf

# Search across all documents
uv run python -m src.pipeline_v3.cli_main search "laser power specifications"

# Check system status
uv run python -m src.pipeline_v3.cli_main status --detailed
```

### Production Deployment

```bash
# Start the queue system for production workloads
uv run python -m src.pipeline_v3.cli_main queue start --workers 4

# Process an entire directory of documents
uv run python -m src.pipeline_v3.cli_main add /path/to/datasheets --recursive

# Monitor processing progress
uv run python -m src.pipeline_v3.cli_main queue status --watch

# Run system maintenance
uv run python -m src.pipeline_v3.cli_main maintenance --consistency-check
```

## 💼 Use Cases

### Technical Documentation Management
- **Engineering Teams**: Instant access to component datasheets and specifications
- **Support Organizations**: Quick retrieval of troubleshooting guides and manuals
- **R&D Departments**: Cross-reference capabilities and part compatibility

### Compliance & Regulatory
- **Standards Documentation**: Search across ISO, IEC, and industry standards
- **Audit Trail**: Complete document versioning and change tracking
- **Knowledge Preservation**: Capture institutional knowledge from legacy documents

### Sales & Marketing
- **Product Information**: Instant access to specifications for customer queries
- **Competitive Analysis**: Compare features across product lines
- **Proposal Generation**: Quick assembly of technical specifications

## 🔧 Advanced Features

### Document Processing
```bash
# Process with intelligent type detection
uv run python -m src.pipeline_v3.cli_main add document.pdf --mode auto

# Extract specific page ranges
uv run python -m src.pipeline_v3.cli_main add manual.pdf --pages "1-10,50-60"

# Batch process from URL list
uv run python -m src.pipeline_v3.cli_main batch add-urls --url-file sources.json

# Process with custom parsing instructions
uv run python -m src.pipeline_v3.cli_main add datasheet.pdf --prompt custom_prompt.md
```

### Enterprise Search
```bash
# Hybrid search with relevance tuning
uv run python -m src.pipeline_v3.cli_main search "power consumption" \
  --type hybrid --fusion-method weighted --alpha 0.7

# Export results for integration
uv run python -m src.pipeline_v3.cli_main search "USB interface" \
  --output results.json --format detailed

# Metadata filtering (coming soon)
uv run python -m src.pipeline_v3.cli_main search "sensor" \
  --filter "doc_type:datasheet" --filter "year:2024"
```

### System Management
```bash
# Configure for your environment
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 8
uv run python -m src.pipeline_v3.cli_main config set openai.retry_max 5

# Health monitoring
uv run python -m src.pipeline_v3.cli_main health --check-all

# Database migrations
uv run python -m src.pipeline_v3.cli_main migrate --check-status
```

## 📊 Performance & Scale

- **Document Processing**: 30-45 seconds per PDF page (OpenAI Vision API)
- **Search Latency**: <100ms for hybrid search across thousands of documents
- **Concurrent Processing**: Configurable workers (tested up to 10 concurrent)
- **Storage Efficiency**: ~1MB per document (compressed JSONL artifacts)
- **Index Size**: ~10% of source document size (combined vector + keyword)

## 🛡️ Security & Compliance

- **API Key Management**: Environment-based configuration, no hardcoded secrets
- **Data Privacy**: All processing can be done on-premises
- **Vector Storage**: Qdrant server mode (default) for production security and scalability
- **Access Control**: Ready for integration with enterprise auth systems
- **Audit Logging**: Complete operation tracking and document history
- **Input Validation**: Protection against SQL injection and path traversal
- **Security Scanning**: Pre-commit hooks and CI/CD include automated secret detection
- **Code Security**: Bandit scanning for Python vulnerabilities in every PR

## 🤝 Contributing

We welcome contributions! Areas of focus:

1. **Security Hardening** - Help fix identified vulnerabilities (#61, #62)
2. **Test Coverage** - Increase from 12% to 70% target
3. **Type Safety** - Fix mypy errors for better code quality
4. **Search Features** - Implement metadata filtering (#53, #54)
5. **Infrastructure** - Qdrant server mode for production (#71)

See [ROADMAP.md](ROADMAP.md) for current priorities and [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📚 Documentation

- **[User Manual](./src/pipeline_v3/USER_MANUAL.md)** - Comprehensive usage guide
- **[Quick Reference](./src/pipeline_v3/QUICK_REFERENCE.md)** - Command cheat sheet
- **[Architecture Guide](./src/pipeline_v3/docs/architecture.md)** - Technical design
- **[Queue System](./src/pipeline_v3/docs/QUEUE_SYSTEM_GUIDE.md)** - Production deployment
- **[API Documentation](./src/pipeline_v3/docs/API.md)** - Integration reference

## 🏆 Project Status

- ✅ **Core Engine**: Production-ready with 96% test pass rate
- ✅ **Document Formats**: PDF, Word, PowerPoint, URLs
- ✅ **Search System**: Hybrid vector + keyword with fusion
- ✅ **Queue System**: Scalable batch processing
- ✅ **CI/CD Pipeline**: Automated testing, quality checks, and security scanning
- ✅ **Qdrant Server Mode**: Default vector storage for production scalability
- 🚧 **In Progress**: Security hardening, test coverage improvements
- 🔜 **Planned**: Web UI, REST API, metadata filtering

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with best-in-class technologies:
- **OpenAI** - Vision API and embedding models
- **Qdrant** - High-performance vector database
- **LlamaIndex** - Document processing framework
- **SQLite** - Reliable embedded database
- **Python** - The language that makes it all possible

---

**Ready to transform your document intelligence?** Get started with the [Quick Start](#-quick-start) guide or dive into the [comprehensive documentation](./src/pipeline_v3/USER_MANUAL.md).

For questions, issues, or contributions, visit our [GitHub repository](https://github.com/seaberger/rag-lab).
