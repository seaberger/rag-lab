# Pipeline v3 User Manual 📖

A comprehensive guide to using the Production Document Processing Pipeline v3 for enterprise-grade document management, search, and processing.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Installation & Setup](#installation--setup)
3. [Basic Operations](#basic-operations)
4. [Advanced Features](#advanced-features)
5. [CLI Reference](#cli-reference)
6. [Configuration](#configuration)
7. [Troubleshooting](#troubleshooting)
8. [Best Practices](#best-practices)
9. [Examples & Use Cases](#examples--use-cases)

---

## Quick Start

### 5-Minute Setup

```bash
# 1. Navigate to project root
cd /path/to/rag_lab

# 2. Add your first document (with new Issue #9 features)
uv run python -m src.pipeline_v3.cli_main add my_document.pdf --mode auto --metadata type=manual

# 3. Search for content
uv run python -m src.pipeline_v3.cli_main search "important keyword" --top-k 5

# 4. Check system status
uv run python -m src.pipeline_v3.cli_main status
```

### 🆕 New CLI Features (Issue #9)
- **Document Modes**: `--mode datasheet|generic|auto` for intelligent classification
- **Batch Processing**: `"docs/*.pdf"` for multiple files at once
- **Custom Prompts**: `--prompt custom.md` for specialized parsing
- **Concurrent Workers**: `--workers N` for faster batch processing
- **URL Support**: Process documents directly from HTTP/HTTPS sources

**That's it!** Your document is now indexed and searchable.

---

## Installation & Setup

### Prerequisites

- **Python 3.12+**
- **UV package manager** (recommended)
- **API Keys** for enhanced features

### Environment Setup

1. **Install Dependencies:**
   ```bash
   # From project root
   uv sync
   ```

2. **Configure Environment Variables:**
   ```bash
   # Copy and edit .env file
   cp .env.example .env
   
   # Required for vector search
   OPENAI_API_KEY=your_openai_key_here
   
   # Optional for parsing
   LLAMA_CLOUD_API_KEY=your_llama_key_here
   ```

3. **Verify Installation:**
   ```bash
   cd src/pipeline_v3
   python cli_main.py --help
   ```

### First-Time Configuration

```bash
# Initialize with recommended settings
python cli_main.py config set queue.max_workers 4
python cli_main.py config set chunking.chunk_size 1024
python cli_main.py config list
```

---

## Basic Operations

### Adding Documents

#### Single Document
```bash
# Basic addition
python cli_main.py add document.pdf

# With metadata
python cli_main.py add manual.pdf --metadata type=manual category=technical

# Force reprocessing
python cli_main.py add document.pdf --force
```

#### Multiple Documents
```bash
# Add multiple files
python cli_main.py add doc1.pdf doc2.pdf doc3.pdf

# Add with pattern (if supported by shell)
python cli_main.py add *.pdf --metadata batch=import_2024
```

### Searching Documents

#### Basic Search
```bash
# Simple keyword search
python cli_main.py search "laser measurement"

# Specify search type
python cli_main.py search "optical sensor" --type keyword
python cli_main.py search "calibration procedure" --type vector
python cli_main.py search "power measurement" --type hybrid
```

#### Advanced Search
```bash
# Limit results
python cli_main.py search "thermopile" --top-k 3

# JSON output for automation
python cli_main.py search "detector" --json

# Detailed results
python cli_main.py search "sensor" --top-k 10 --detailed
```

### Managing Documents

#### Updating Documents
```bash
# Update existing document
python cli_main.py update document.pdf --metadata version=2.0

# Force update even if no changes detected
python cli_main.py update document.pdf --force
```

#### Removing Documents
```bash
# Remove from all indexes
python cli_main.py remove old_document.pdf

# Remove from specific index type
python cli_main.py remove document.pdf --index-type keyword
```

### System Status

```bash
# Quick status check
python cli_main.py status

# Detailed system information
python cli_main.py status --detailed

# JSON format for monitoring
python cli_main.py status --json
```

---

## Advanced Features

### Queue Management

The pipeline uses an intelligent queue system for processing multiple documents efficiently.

#### Starting the Queue
```bash
# Start with default workers
python cli_main.py queue start

# Start with specific worker count
python cli_main.py queue start --workers 8

# Check if queue is running
python cli_main.py queue status
```

#### Queue Operations
```bash
# Monitor queue in detail
python cli_main.py queue status --detailed

# Stop queue gracefully
python cli_main.py queue stop --wait

# Clear all pending jobs
python cli_main.py queue clear --confirm
```

### System Maintenance

#### Index Management
```bash
# Check index consistency
python cli_main.py maintenance --consistency-check

# Repair any issues
python cli_main.py maintenance --repair

# Clean up temporary files
python cli_main.py maintenance --cleanup
```

#### Performance Optimization
```bash
# Run all maintenance tasks
python cli_main.py maintenance --repair --cleanup --consistency-check
```

### Configuration Management

#### Viewing Configuration
```bash
# List all settings
python cli_main.py config list

# Get specific setting
python cli_main.py config get queue.max_workers
```

#### Updating Configuration
```bash
# Set individual values
python cli_main.py config set queue.max_workers 8
python cli_main.py config set chunking.chunk_size 512

# Reset to defaults
python cli_main.py config reset --confirm
```

---

## CLI Reference

### Command Structure
```
python cli_main.py [GLOBAL_OPTIONS] COMMAND [COMMAND_OPTIONS] [ARGUMENTS]
```

### Global Options
- `--config CONFIG` - Path to configuration file
- `--verbose, -v` - Enable verbose output
- `--json` - Output results in JSON format
- `--help, -h` - Show help information

### Commands Overview

| Command | Purpose | Example |
|---------|---------|---------|
| `add` | Add documents to pipeline | `add doc.pdf --metadata type=manual` |
| `update` | Update existing documents | `update doc.pdf --force` |
| `remove` | Remove documents from indexes | `remove doc.pdf` |
| `search` | Search through documents | `search "keyword" --type hybrid` |
| `queue` | Manage processing queue | `queue start --workers 4` |
| `status` | Show system status | `status --detailed` |
| `maintenance` | Run maintenance tasks | `maintenance --repair` |
| `config` | Manage configuration | `config set key value` |

### Detailed Command Reference

#### `add` Command
```bash
python cli_main.py add [OPTIONS] PATHS...

Options:
  --metadata KEY=VALUE    Add metadata (can be used multiple times)
  --force                 Force processing even if document exists
  --index-type TYPE       Index type: vector, keyword, both (default: both)

Examples:
  python cli_main.py add document.pdf
  python cli_main.py add manual.pdf --metadata type=guide version=1.0
  python cli_main.py add doc.pdf --force --index-type keyword
```

#### `search` Command
```bash
python cli_main.py search [OPTIONS] QUERY

Options:
  --type TYPE            Search type: vector, keyword, hybrid (default: hybrid)
  --top-k NUMBER         Number of results (default: 10)
  --filter FILTER        Filter expression in JSON format

Examples:
  python cli_main.py search "laser measurement"
  python cli_main.py search "calibration" --type keyword --top-k 5
  python cli_main.py search "sensor" --filter '{"type": "manual"}'
```

#### `queue` Subcommands
```bash
# Start queue processing
python cli_main.py queue start [--workers NUMBER]

# Stop queue processing  
python cli_main.py queue stop [--wait]

# Show queue status
python cli_main.py queue status [--detailed]

# Clear all jobs
python cli_main.py queue clear [--confirm]
```

#### `config` Subcommands
```bash
# List all configuration
python cli_main.py config list

# Get configuration value
python cli_main.py config get KEY

# Set configuration value
python cli_main.py config set KEY VALUE

# Reset configuration
python cli_main.py config reset [--confirm]
```

---

## Configuration

### Configuration File Structure

Pipeline v3 uses a YAML configuration file with hierarchical settings:

```yaml
# config.yaml
pipeline:
  max_concurrent: 5
  timeout_seconds: 300
  version: "3.0.0"

queue:
  max_workers: 4
  batch_size: 10
  job_persistence: true
  resume_interrupted: true

storage:
  base_dir: "./storage_data_v3"
  keyword_db_path: "./keyword_index_v3.db"
  document_registry_path: "./document_registry_v3.db"

chunking:
  chunk_size: 1024
  chunk_overlap: 128

openai:
  api_key: null  # Set via environment variable
  embedding_model: "text-embedding-3-small"
  dimensions: 1536
  max_retries: 3

cache:
  enabled: true
  directory: "./cache_v3"
  ttl_days: 7
  compress: true
```

### Key Configuration Sections

#### Performance Settings
```yaml
pipeline:
  max_concurrent: 8      # Concurrent document processing
  timeout_seconds: 600   # Processing timeout

queue:
  max_workers: 6         # Queue worker threads
  batch_size: 20         # Batch processing size
```

#### Storage Configuration
```yaml
storage:
  base_dir: "./data"                    # Base storage directory
  keyword_db_path: "./keyword.db"      # Keyword index database
  document_registry_path: "./docs.db"  # Document registry
```

#### Search & Processing
```yaml
chunking:
  chunk_size: 512       # Text chunk size for processing
  chunk_overlap: 64     # Overlap between chunks

openai:
  embedding_model: "text-embedding-3-small"
  dimensions: 1536
```

### Environment Variables

Set these in your `.env` file:

```bash
# Required for vector search
OPENAI_API_KEY=your_openai_api_key

# Optional for enhanced parsing
LLAMA_CLOUD_API_KEY=your_llama_cloud_key

# Optional for monitoring
LANGFUSE_SECRET_KEY=your_langfuse_key
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
```

---

## Troubleshooting

### Common Issues

#### 1. "No module named 'llama_index'" Error
```bash
# Solution: Install dependencies
uv sync

# Or install specific packages
uv add llama-index llama-index-vector-stores-qdrant
```

#### 2. Search Returns No Results
```bash
# Check if documents are indexed
python cli_main.py status --detailed

# Verify document was processed
python cli_main.py config get storage.keyword_db_path

# Try different search types
python cli_main.py search "keyword" --type keyword
```

#### 3. Queue Not Processing
```bash
# Check queue status
python cli_main.py queue status --detailed

# Restart queue
python cli_main.py queue stop
python cli_main.py queue start --workers 4
```

#### 4. Performance Issues
```bash
# Check system status
python cli_main.py status --detailed

# Run maintenance
python cli_main.py maintenance --repair --cleanup

# Adjust worker count
python cli_main.py config set queue.max_workers 2
```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# Verbose output
python cli_main.py --verbose search "test query"

# JSON output for analysis
python cli_main.py --json status --detailed
```

### Log Files

Check log files for detailed error information:
- `pipeline.log` - Main pipeline logs
- Console output with `--verbose` flag

---

## Best Practices

### Document Management

#### 1. **Organize with Metadata**
```bash
# Use consistent metadata schemes
python cli_main.py add manual.pdf --metadata type=manual category=technical version=1.0
python cli_main.py add guide.pdf --metadata type=guide category=user version=2.1
```

#### 2. **Batch Processing**
```bash
# Process related documents together
python cli_main.py add *.pdf --metadata batch=quarterly_update_2024

# Use appropriate worker counts
python cli_main.py queue start --workers 8  # For many documents
python cli_main.py queue start --workers 2  # For large documents
```

#### 3. **Regular Maintenance**
```bash
# Weekly maintenance routine
python cli_main.py maintenance --consistency-check
python cli_main.py maintenance --cleanup

# Monthly deep maintenance
python cli_main.py maintenance --repair --cleanup --consistency-check
```

### Search Optimization

#### 1. **Choose Appropriate Search Types**
- **Keyword**: Fast, exact matches, technical terms
- **Vector**: Semantic search, concept matching
- **Hybrid**: Best of both, recommended for most use cases

#### 2. **Effective Query Strategies**
```bash
# Specific technical terms
python cli_main.py search "thermopile calibration" --type keyword

# Conceptual searches
python cli_main.py search "measurement accuracy procedures" --type vector

# General purpose
python cli_main.py search "laser power detection" --type hybrid
```

### Performance Optimization

#### 1. **Worker Configuration**
```bash
# For CPU-intensive tasks
python cli_main.py config set queue.max_workers 4

# For I/O-intensive tasks  
python cli_main.py config set queue.max_workers 8
```

#### 2. **Chunking Strategy**
```bash
# Smaller chunks for detailed search
python cli_main.py config set chunking.chunk_size 512

# Larger chunks for context preservation
python cli_main.py config set chunking.chunk_size 1024
```

#### 3. **Cache Management**
```bash
# Enable caching for repeated operations
python cli_main.py config set cache.enabled true
python cli_main.py config set cache.ttl_days 7
```

---

## Examples & Use Cases

### Technical Documentation Management

#### Scenario: Managing Product Manuals
```bash
# 1. Add product manuals with metadata
python cli_main.py add fieldmax_manual.pdf --metadata product=FieldMax type=manual
python cli_main.py add powermax_guide.pdf --metadata product=PowerMax type=guide

# 2. Search for product-specific information
python cli_main.py search "calibration procedure" --type hybrid --top-k 3

# 3. Find troubleshooting information
python cli_main.py search "error codes" --type keyword
```

#### Scenario: Research Document Archive
```bash
# 1. Batch import research papers
python cli_main.py add research/*.pdf --metadata category=research year=2024

# 2. Semantic search for concepts
python cli_main.py search "machine learning applications" --type vector

# 3. Find specific methodologies
python cli_main.py search "experimental setup" --type hybrid --top-k 5
```

### Enterprise Knowledge Base

#### Scenario: Company Policy Documents
```bash
# 1. Structure documents with metadata
python cli_main.py add hr_policy.pdf --metadata department=HR type=policy
python cli_main.py add safety_manual.pdf --metadata department=Safety type=manual

# 2. Department-specific searches
python cli_main.py search "vacation policy" --filter '{"department": "HR"}'

# 3. Cross-department searches
python cli_main.py search "compliance requirements" --type hybrid
```

### Quality Control Documentation

#### Scenario: Test Procedures and Results
```bash
# 1. Add test documentation
python cli_main.py add test_procedure_v2.pdf --metadata type=procedure version=2.0
python cli_main.py add test_results_q1.pdf --metadata type=results quarter=Q1

# 2. Find latest procedures
python cli_main.py search "calibration test" --type keyword

# 3. Historical result analysis
python cli_main.py search "performance metrics" --type vector --top-k 10
```

### Automated Workflows

#### Scenario: Integration with Scripts
```bash
#!/bin/bash
# Automated document processing script

# Add new documents
for file in new_docs/*.pdf; do
    python cli_main.py add "$file" --metadata source=automated date=$(date +%Y%m%d)
done

# Generate daily search report
python cli_main.py search "critical issues" --json > daily_issues.json

# System health check
python cli_main.py status --json > system_status.json
```

#### Scenario: Monitoring Dashboard
```bash
# Status monitoring script
#!/bin/bash

echo "=== Pipeline v3 Status Report ==="
python cli_main.py status --detailed

echo -e "\n=== Queue Status ==="
python cli_main.py queue status --detailed

echo -e "\n=== Recent Activity ==="
python cli_main.py search "recent" --top-k 5
```

### Advanced Configuration Examples

#### High-Performance Setup
```yaml
# config.yaml for high-performance processing
pipeline:
  max_concurrent: 10
  timeout_seconds: 1800

queue:
  max_workers: 8
  batch_size: 50

chunking:
  chunk_size: 2048
  chunk_overlap: 256

cache:
  enabled: true
  compress: true
```

#### Memory-Optimized Setup
```yaml
# config.yaml for memory-constrained environments
pipeline:
  max_concurrent: 2
  timeout_seconds: 300

queue:
  max_workers: 2
  batch_size: 5

chunking:
  chunk_size: 512
  chunk_overlap: 50

cache:
  enabled: false
```

---

## Support & Additional Resources

### Getting Help

```bash
# Command-specific help
python cli_main.py add --help
python cli_main.py search --help

# General help
python cli_main.py --help
```

### Testing Your Setup

```bash
# Run integration tests
python quick_integration_test.py

# Test CLI functionality
python test_cli_simple.py

# Verify search with real documents
python verify_real_search.py
```

### Configuration Validation

```bash
# Check current configuration
python cli_main.py config list

# Validate system status
python cli_main.py status --detailed

# Test connectivity
python cli_main.py maintenance --consistency-check
```

---

**Pipeline v3 User Manual** - Complete guide for enterprise document processing and management. For technical details, see [README.md](./README.md) and [DEVELOPMENT_STATUS.md](./DEVELOPMENT_STATUS.md).