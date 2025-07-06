# RAG Lab - Production Document Intelligence Engine 🚀

[![CI/CD Pipeline](https://github.com/seaberger/rag-lab/actions/workflows/ci.yml/badge.svg)](https://github.com/seaberger/rag-lab/actions/workflows/ci.yml)
[![Pipeline v3 CI](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml/badge.svg)](https://github.com/seaberger/rag-lab/actions/workflows/pipeline_v3_ci.yml)
[![Tests](https://img.shields.io/badge/tests-359%20passing-brightgreen)](./src/pipeline_v3/tests/)
[![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)](./src/pipeline_v3/tests/)
[![Documentation](https://img.shields.io/badge/docs-comprehensive-blue)](./src/pipeline_v3/USER_MANUAL.md)

## 🎯 Vision

RAG Lab is evolving from a production-ready document intelligence engine to a full **enterprise multi-tenant platform** designed to transform how organizations interact with their technical documentation. By combining state-of-the-art AI models with enterprise-grade infrastructure, RAG Lab enables instant access to complex technical information across thousands of documents.

### Current State → Future Vision

**Today**: Single-user document processing with hybrid search
**Tomorrow**: Multi-tenant platform with per-organization MCP servers, advanced multi-vector search (ColBERT, SPLADE), and agentic workflows

### Why RAG Lab?

In today's knowledge economy, critical business information is trapped in PDFs, datasheets, manuals, and presentations. RAG Lab liberates this information, making it instantly searchable, intelligently retrievable, and contextually understandable—with enterprise-grade security and tenant isolation.

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
- **Qdrant Server Mode**: Default vector storage for production scalability and concurrent access

### 🛡️ **Reliability & Performance**
- **Comprehensive Error Handling**: Multi-layer retry logic, graceful degradation, and detailed error reporting
- **Real-Time Monitoring**: Performance metrics, queue status, and system health tracking
- **API Cost Optimization**: Intelligent caching, batch processing, and request optimization
- **Production Hardening**: Rate limiting, timeout management, and resource pooling

## 🏗️ System Architecture

### Current Architecture (v3)
```
┌─────────────────────────────────────────────────────────────────┐
│                        Interface Layer                           │
├─────────────────────────────────────────────────────────────────┤
│              CLI Tools (Management & Operations)                 │
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
│   (Qdrant)     │  (SQLite FTS5) │    (SQLite)       │  (LZ4)  │
├─────────────────────────────────────────────────────────────────┤
│                    External Services                             │
├─────────────────────────────────────────────────────────────────┤
│            OpenAI APIs           │        Qdrant Server          │
│    (Vision, Embeddings, LLM)     │    (localhost:6333)          │
└─────────────────────────────────────────────────────────────────┘
```

### 🚀 Future Enterprise Architecture (v4)
```
┌─────────────────────────────────────────────────────────────────┐
│            🔐 API Gateway & Authentication Layer                 │
├─────────────────────────────────────────────────────────────────┤
│         Per-Tenant MCP Servers │ Agentic Workflows              │
├─────────────────────────────────────────────────────────────────┤
│    Tenant-Specific Search Pipelines │ Multi-Vector Search       │
├─────────────────────────────────────────────────────────────────┤
│              PostgreSQL (All Metadata & Keywords)                │
├─────────────────────────────────────────────────────────────────┤
│      Qdrant Server (Dense, Sparse, ColBERT Vectors)            │
├─────────────────────────────────────────────────────────────────┤
│    Document Security │ Audit Logs │ Usage Analytics            │
└─────────────────────────────────────────────────────────────────┘
```

**Key Architecture Changes:**
- **SQLite → PostgreSQL**: Enable concurrent multi-tenant access
- **Single Collection → Tenant Isolation**: Complete data separation
- **Basic Auth → API Keys**: Rate limiting and RBAC
- **Fixed Search → Adaptive Pipelines**: Per-tenant optimization
- **Single Vector → Multi-Vector**: ColBERT, SPLADE, BGE-M3

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

#### **Security Components**
- **Input Validation**: Path traversal protection and input sanitization
- **URL Security**: SSRF protection with private IP blocking and protocol restrictions
- **API Key Management**: Secure handling with masked logging and environment validation
- **SQL Protection**: Parameterized queries and FTS5 query sanitization
- **Security Testing**: Comprehensive test suite with 33 security-focused tests

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

# Enhance documents with keyword extraction for better search
uv run python -m src.pipeline_v3.cli_main add document.pdf --processing-options keywords
```

### Enterprise Search
```bash
# Hybrid search with relevance tuning
uv run python -m src.pipeline_v3.cli_main search "power consumption" \
  --type hybrid --top-k 10

# Export results for integration
uv run python -m src.pipeline_v3.cli_main search "USB interface" \
  --output results.json --format detailed

# Different search modes for different needs
uv run python -m src.pipeline_v3.cli_main search "sensor" --type vector     # Semantic search
uv run python -m src.pipeline_v3.cli_main search "PM10K" --type keyword     # Exact term search
uv run python -m src.pipeline_v3.cli_main search "laser power" --type hybrid # Best of both
```

### System Management
```bash
# Configure for your environment
uv run python -m src.pipeline_v3.cli_main config set queue.max_workers 8
uv run python -m src.pipeline_v3.cli_main config set openai.retry_max 5

# Health monitoring
uv run python -m src.pipeline_v3.cli_main status --detailed --json

# Database migrations and maintenance
uv run python -m src.pipeline_v3.cli_main maintenance --consistency-check
uv run python -m src.pipeline_v3.cli_main maintenance --repair
```

## ✨ Key Features

### 🔄 **Queue-Based Processing**
- Scalable concurrent document processing with job persistence
- Automatic retries and progress tracking
- Configurable workers and resource management
- Handles unlimited document volumes reliably

### 📋 **Document Lifecycle Management**
- Intelligent add/update/remove with change detection
- 6 types of change detection for efficient updates
- Complete document state tracking and consistency checking
- Smart differential updates preserve existing work

### 🔍 **Advanced Search**
- **Hybrid Search**: Combines vector similarity with keyword precision
- **Vector Search**: Semantic understanding for conceptual queries
- **Keyword Search**: BM25 full-text search for exact terms
- **Relevance Fusion**: Adaptive scoring for optimal results

### 💻 **Production CLI**
- Complete command-line interface for all operations
- JSON output support for automation and integration
- Comprehensive error handling and user guidance
- Real-time status monitoring and progress tracking

### 🗄️ **Vector Storage Options**
1. **Server Mode (Default)** - Production-ready Qdrant server
   - Requires: `./scripts/qdrant_server.sh start`
   - Dashboard: http://localhost:6333/dashboard
   - Best for: Production, parallel processing, multiple clients

2. **Local Mode** - File-based storage for development
   - Usage: `--config config_local.yaml`
   - Storage: `./qdrant_data_v3/`
   - Best for: Offline development, simple testing

## 📊 Performance & Scale

- **Document Processing**: 30-45 seconds per PDF page (OpenAI Vision API)
- **Search Latency**: <100ms for hybrid search across thousands of documents
- **Concurrent Processing**: Configurable workers (tested up to 10 concurrent)
- **Storage Efficiency**: ~1MB per document (compressed JSONL artifacts)
- **Index Size**: ~10% of source document size (combined vector + keyword)
- **Test Coverage**: 88% with 359 passing tests

## 🛡️ Security & Compliance

- **API Key Management**: Environment-based configuration, no hardcoded secrets
- **Data Privacy**: All processing can be done on-premises
- **Vector Storage**: Qdrant server mode (default) for production security and scalability
- **Access Control**: Ready for integration with enterprise auth systems
- **Audit Logging**: Complete operation tracking and document history
- **Input Validation**: Protection against SQL injection and path traversal
- **Security Scanning**: Pre-commit hooks and CI/CD include automated secret detection
- **Code Security**: Bandit scanning for Python vulnerabilities in every PR

## 📚 Documentation

### 📖 **Complete User Guide**
- **[User Manual](./src/pipeline_v3/USER_MANUAL.md)** - Comprehensive usage guide with installation, configuration, and best practices
- **[Quick Reference](./src/pipeline_v3/QUICK_REFERENCE.md)** - Essential commands cheat sheet for daily use

### 🏗️ **Technical Documentation**
- **[Development Status](./src/pipeline_v3/DEVELOPMENT_STATUS.md)** - Complete implementation history and current status
- **[Architecture Guide](./src/pipeline_v3/docs/architecture.md)** - Technical system design and component details
- **[Queue System Guide](./src/pipeline_v3/docs/QUEUE_SYSTEM_GUIDE.md)** - Production deployment and queue management
- **[API Documentation](./src/pipeline_v3/docs/API.md)** - Integration reference and automation guides

### 📋 **Project Management**
- **[ROADMAP.md](./ROADMAP.md)** - Current development priorities and active issues
- **[ISSUES.md](./ISSUES.md)** - Critical architecture gaps and security considerations
- **[Enterprise Implementation](./src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md)** - Complete multi-tenant platform vision

## 🏆 Project Status

### ✅ **Production Ready**
- **Core Engine**: 359 tests passing with 88% coverage
- **Document Formats**: PDF, Word, PowerPoint, URLs, and web content
- **Search System**: Hybrid vector + keyword with adaptive fusion
- **Queue System**: Scalable batch processing with job persistence
- **CI/CD Pipeline**: Automated testing, quality checks, and security scanning
- **Qdrant Server Mode**: Default vector storage for production scalability
- **Database Migrations**: Schema versioning with rollback support

### 🚧 **In Progress**
- Security hardening and vulnerability fixes ([Issue #61](https://github.com/seaberger/rag-lab/issues/61), [Issue #62](https://github.com/seaberger/rag-lab/issues/62))
- PostgreSQL migration for multi-tenancy ([Issue #77](https://github.com/seaberger/rag-lab/issues/77))

### 🔜 **Enterprise Roadmap (v4)**
- **Multi-Tenant Platform**: PostgreSQL backend, complete tenant isolation
- **API Authentication**: Secure API keys with rate limiting ([Issue #78](https://github.com/seaberger/rag-lab/issues/78))
- **MCP Servers**: Per-tenant servers for agentic workflows ([Issue #81](https://github.com/seaberger/rag-lab/issues/81))
- **Advanced Search**: ColBERT, SPLADE, multi-vector fusion ([Issue #84](https://github.com/seaberger/rag-lab/issues/84))
- **Document Security**: Fine-grained access control ([Issue #79](https://github.com/seaberger/rag-lab/issues/79))
- **Adaptive Optimization**: Usage-based search tuning ([Issue #85](https://github.com/seaberger/rag-lab/issues/85))

See [ROADMAP.md](./ROADMAP.md) for complete details and [Enterprise Implementation Guide](./src/pipeline_v3/docs/ENTERPRISE_MULTI_TENANT_IMPLEMENTATION.md) for the full vision.

## 🤝 Contributing

We welcome contributions! Current priorities:

1. **Security First**: Review and help fix security vulnerabilities ([#61](https://github.com/seaberger/rag-lab/issues/61), [#62](https://github.com/seaberger/rag-lab/issues/62))
2. **CI/CD Infrastructure**: Resolve GitHub Actions infrastructure issues ([#75](https://github.com/seaberger/rag-lab/issues/75))
3. **Search Features**: Implement metadata filtering ([#53](https://github.com/seaberger/rag-lab/issues/53), [#54](https://github.com/seaberger/rag-lab/issues/54))
4. **Type Safety**: Help fix mypy errors for better code quality
5. **Document Processing**: Improve chunking strategies ([#14](https://github.com/seaberger/rag-lab/issues/14), [#15](https://github.com/seaberger/rag-lab/issues/15))

See [ROADMAP.md](ROADMAP.md) for detailed priorities and [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

### Development Workflow
- Pre-commit hooks run automatically for code quality
- Quick CI provides feedback in ~3 minutes
- Comprehensive CI runs full 359-test suite
- All PRs require passing CI checks

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

Built with best-in-class technologies:
- **OpenAI** - Vision API and embedding models for intelligent document understanding
- **Qdrant** - High-performance vector database for semantic search
- **LlamaIndex** - Document processing framework and chunking strategies
- **SQLite** - Reliable embedded database for metadata and job persistence
- **Python** - The language that makes enterprise AI accessible

---

**Ready to transform your document intelligence?** Get started with the [Quick Start](#-quick-start) guide or dive into the [comprehensive documentation](./src/pipeline_v3/USER_MANUAL.md).

For questions, issues, or contributions, visit our [GitHub repository](https://github.com/seaberger/rag-lab) or check our [active issues](https://github.com/seaberger/rag-lab/issues).
