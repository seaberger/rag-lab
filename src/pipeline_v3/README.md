# Production Document Pipeline v3

A production-ready document processing pipeline with advanced queue management, document lifecycle operations, and enterprise-grade index management capabilities.

## Architecture Overview

This pipeline extends the stable v2.1 foundation with production features:

- **Queue-based processing** with configurable concurrency
- **Document lifecycle management** (add/update/remove)
- **Content fingerprinting** for change detection
- **Index consistency management** across vector and keyword stores
- **Persistent job tracking** with resume capability
- **Enterprise CLI tools** for batch operations and monitoring

## Module Structure

```
src/pipeline_v3/
├── README.md              # This file
├── docs/                  # Development documentation
│   ├── development_plan.md # Detailed development roadmap
│   ├── architecture.md    # Technical architecture
│   └── api_reference.md   # API documentation
├── config.yaml           # Enhanced configuration
├── core/                  # Core pipeline logic
│   ├── pipeline.py        # Enhanced main pipeline
│   ├── document.py        # Document lifecycle management
│   └── fingerprint.py     # Content tracking & change detection
├── queue/                 # Queue & job management
│   ├── manager.py         # Queue management
│   ├── job.py             # Job persistence & tracking
│   └── scheduler.py       # Batch scheduling & concurrency
├── index/                 # Index lifecycle management
│   ├── manager.py         # Index lifecycle operations
│   ├── vector.py          # Enhanced vector operations
│   ├── keyword.py         # Enhanced keyword operations
│   └── consistency.py     # Index consistency checking
├── cli/                   # Command-line interfaces
│   ├── batch.py           # Batch processing CLI
│   ├── manage.py          # Index management CLI
│   └── monitor.py         # Status & monitoring CLI
├── storage/               # Enhanced storage layer
├── search/                # Enhanced search capabilities
└── utils/                 # Enhanced utilities
```

## Key Features

### ✅ Queue-Based Processing
- Configurable concurrency (1-50 workers)
- Priority-based job scheduling
- Progress tracking with ETA
- Automatic retry on failures
- Resume interrupted processing

### ✅ Document Lifecycle Management  
- Content fingerprinting for change detection
- Update existing documents in indexes
- Remove obsolete documents
- Version tracking and rollback
- Batch add/update/remove operations

### ✅ Enterprise Index Management
- Dual index consistency checking (vector + keyword)
- Index backup and restore
- Selective index rebuilding
- Performance monitoring and optimization
- Storage usage tracking

### ✅ Production CLI Tools
```bash
# Batch processing with queue management
python cli/batch.py --src "docs/**/*.pdf" --max-concurrent 10

# Document lifecycle operations
python cli/manage.py --update doc_id --src new_version.pdf
python cli/manage.py --add new_document.pdf --with-keywords
python cli/manage.py --remove obsolete_doc_id

# Index management and monitoring
python cli/monitor.py --status --verify-consistency
python cli/manage.py --backup ./backups/2025-06-04/
python cli/manage.py --rebuild-index vector
```

## Development Status

| Phase | Component | Status | Lines | Tokens |
|-------|-----------|--------|-------|--------|
| 1 | Queue & Fingerprinting | 🚧 Planning | ~2,000 | ~70k |
| 1 | Enhanced Configuration | 🚧 Planning | ~400 | ~15k |
| 2 | Index Lifecycle | 📋 TODO | ~1,500 | ~80k |
| 2 | Consistency Management | 📋 TODO | ~400 | ~20k |
| 3 | CLI Tools | 📋 TODO | ~1,200 | ~50k |
| 3 | Documentation | 📋 TODO | ~400 | ~15k |

**Total Estimated**: ~6,000 lines, ~250k tokens

## Quick Start

*Note: This is a development branch. Stable functionality is available in `src/parsing/refactored_2_1/`*

### Development Setup
```bash
# Switch to development branch
git checkout feature/production-pipeline-v3

# Install dependencies
uv sync

# Activate environment
source .venv/bin/activate

# Run development pipeline (when ready)
python cli/batch.py --help
```

### Migration from v2.1

The v3 pipeline maintains compatibility with v2.1 configurations and data formats:

- **Artifacts**: Uses same JSONL format as v2.1
- **Vector Store**: Compatible with existing Qdrant collections
- **Keyword Index**: Compatible with existing SQLite FTS5 databases
- **Configuration**: Extends v2.1 config.yaml with new sections

## Contributing

See `docs/development_plan.md` for detailed implementation roadmap and contribution guidelines.

## License

Same license as parent project.