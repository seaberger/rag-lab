# Multi-Tenant Architecture Design

**Document Version:** 1.0
**Last Updated:** July 4, 2025
**Author:** Pipeline v3 Development Team
**Status:** Proposed Architecture

## Executive Summary

This document outlines the architecture for implementing multi-tenant support in Pipeline v3, enabling complete isolation between business groups, departments, or projects. The design leverages Qdrant's native collection support for vector storage while maintaining filesystem isolation for other components.

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Architecture Overview](#architecture-overview)
3. [Component Design](#component-design)
4. [Implementation Strategy](#implementation-strategy)
5. [Security & Isolation](#security--isolation)
6. [Performance Considerations](#performance-considerations)
7. [Migration Plan](#migration-plan)
8. [Future Enhancements](#future-enhancements)

## Current State Analysis

### What Exists Today

1. **Basic Configuration Support**
   ```yaml
   # config.yaml
   qdrant:
     collection_name: datasheets_v3
     collections:  # Placeholder for future multi-collection support
       default: datasheets_v3
   ```

2. **Single Collection Implementation**
   - All operations use a single hardcoded collection
   - No collection switching logic
   - No isolation between different document sets

3. **Infrastructure Ready**
   - Qdrant server mode is now default (Issue #71 completed)
   - Server infrastructure supports multiple collections
   - No filesystem-level isolation implemented

### Limitations of Current Architecture

- **No Data Isolation**: All documents mixed in one collection
- **No Access Control**: Cannot restrict access by group
- **No Configuration Flexibility**: All users share same settings
- **Scalability Issues**: Cannot scale per tenant
- **Testing Challenges**: Test data mixed with production

## Architecture Overview

### Design Principles

1. **Complete Isolation**: No data leakage between tenants
2. **Technology Strengths**: Use each component's native capabilities
3. **Simple Operations**: Easy backup, restore, and migration
4. **Minimal Changes**: Extend rather than rewrite existing code
5. **Future-Proof**: Support for RBAC and advanced features

### Hybrid Approach

We recommend a hybrid architecture that combines:
- **Qdrant Native Collections**: For vector storage isolation
- **Filesystem Isolation**: For SQLite databases and artifacts
- **Unified Management**: Single CollectionManager to coordinate

### Directory Structure

```
rag_lab/
├── collections_v3/                    # Multi-tenant base directory
│   ├── _global/                      # Shared configuration
│   │   ├── collections.json          # Collection registry
│   │   ├── access_control.json       # Future: RBAC rules
│   │   └── audit_log.jsonl           # Collection operations log
│   │
│   ├── default/                      # Default collection
│   │   ├── config_override.yaml      # Collection-specific config
│   │   ├── keyword_index.db          # SQLite FTS5 search
│   │   ├── document_registry.db      # Document tracking
│   │   ├── fingerprints.db           # Change detection
│   │   ├── jobs.db                   # Job queue
│   │   ├── storage_data/             # JSONL artifacts
│   │   │   └── *.jsonl
│   │   └── cache/                    # LZ4 compressed cache
│   │       └── *.lz4
│   │
│   └── [collection_name]/            # Additional collections
│       └── [same structure as default]
│
├── qdrant_server_data/               # Managed by Qdrant
│   └── [Qdrant's internal storage]
│
└── logs/
    └── collections/                  # Collection-specific logs
        ├── default/
        └── [collection_name]/
```

### Qdrant Collection Naming

Qdrant collections will use a namespaced approach:
- Pattern: `{prefix}_{collection_name}`
- Example: `datasheets_v3_default`, `datasheets_v3_engineering`
- Benefits: Clear organization, easy filtering, migration support

## Component Design

### CollectionManager

Central coordinator for all collection operations:

```python
from dataclasses import dataclass
from typing import Optional, List, Dict
from pathlib import Path
import json

@dataclass
class CollectionInfo:
    name: str
    created_at: str
    document_count: int
    storage_size_mb: float
    last_accessed: str
    config_overrides: Dict
    is_active: bool
    metadata: Dict

class CollectionManager:
    """Manages multi-tenant collections for document processing."""

    def __init__(self, base_dir: str = "./collections_v3"):
        self.base_dir = Path(base_dir)
        self.registry_path = self.base_dir / "_global" / "collections.json"
        self._ensure_base_structure()

    def create_collection(
        self,
        name: str,
        config_overrides: Optional[Dict] = None,
        metadata: Optional[Dict] = None
    ) -> CollectionInfo:
        """Create a new isolated collection."""
        # 1. Validate collection name
        # 2. Create Qdrant collection
        # 3. Create filesystem structure
        # 4. Initialize SQLite databases
        # 5. Register in collections.json
        # 6. Apply config overrides
        # 7. Log operation

    def delete_collection(self, name: str, confirm: bool = False) -> None:
        """Delete a collection and all its data."""
        # 1. Verify collection exists
        # 2. Require confirmation
        # 3. Delete Qdrant collection
        # 4. Remove filesystem data
        # 5. Update registry
        # 6. Log operation

    def list_collections(self) -> List[CollectionInfo]:
        """List all registered collections with metadata."""

    def get_collection_info(self, name: str) -> CollectionInfo:
        """Get detailed information about a collection."""

    def switch_collection(self, name: str) -> None:
        """Switch active collection for operations."""

    def export_collection(self, name: str, output_path: str) -> None:
        """Export collection for backup or migration."""

    def import_collection(self, archive_path: str, new_name: Optional[str] = None) -> None:
        """Import a collection from archive."""
```

### Configuration Updates

```python
@dataclass
class CollectionSettings:
    """Settings for multi-tenant collection support."""

    # Active collection for operations
    active_collection: str = "default"

    # Base directory for all collections
    base_directory: str = "./collections_v3"

    # Qdrant collection prefix
    qdrant_prefix: str = "datasheets_v3"

    # Enable collection isolation
    isolation_enabled: bool = True

    # Per-collection configuration overrides
    collection_overrides: Dict[str, Dict] = field(default_factory=lambda: {
        "engineering": {
            "openai": {
                "vision_model": "gpt-4-turbo",
                "timeout_per_page": 45
            },
            "chunking": {
                "chunk_size": 2048,
                "chunk_overlap": 256
            }
        },
        "sales": {
            "openai": {
                "vision_model": "gpt-4.1",
                "timeout_per_page": 30
            },
            "chunking": {
                "chunk_size": 1024,
                "chunk_overlap": 128
            }
        }
    })
```

### Component Integration

#### PipelineConfig Updates

```python
class PipelineConfig:
    def __init__(self, config_path: Optional[str] = None, collection: Optional[str] = None):
        # Load base configuration
        self._load_base_config(config_path)

        # Set active collection
        self.collection_name = collection or self.collections.active_collection

        # Apply collection overrides
        self._apply_collection_overrides()

        # Update all paths to be collection-aware
        self._update_paths_for_collection()

    @property
    def collection_context(self) -> str:
        """Current collection context for operations."""
        return self.collection_name

    def get_collection_path(self, component: str) -> Path:
        """Get collection-specific path for a component."""
        base = Path(self.collections.base_directory)
        return base / self.collection_name / component
```

#### Storage Path Updates

All components need collection-aware paths:

```python
# Before (single collection)
keyword_db_path = "./keyword_index_v3.db"

# After (multi-tenant)
keyword_db_path = config.get_collection_path("keyword_index.db")
```

### CLI Integration

New collection management commands:

```bash
# Collection management
uv run python -m src.pipeline_v3.cli_main collections create [name] [options]
uv run python -m src.pipeline_v3.cli_main collections list
uv run python -m src.pipeline_v3.cli_main collections info [name]
uv run python -m src.pipeline_v3.cli_main collections delete [name] --confirm
uv run python -m src.pipeline_v3.cli_main collections set-default [name]

# Collection-aware operations
uv run python -m src.pipeline_v3.cli_main add document.pdf --collection engineering
uv run python -m src.pipeline_v3.cli_main search "query" --collection engineering

# Import/Export
uv run python -m src.pipeline_v3.cli_main collections export engineering --output backup.tar.gz
uv run python -m src.pipeline_v3.cli_main collections import backup.tar.gz --name engineering_restored
```

## Implementation Strategy

### Phase 1: Core Infrastructure (2 days)

1. **CollectionManager Implementation**
   - Basic CRUD operations
   - Registry management
   - Filesystem operations

2. **Configuration Updates**
   - Add CollectionSettings
   - Update PipelineConfig
   - Path generation logic

3. **Qdrant Integration**
   - Collection creation/deletion
   - Namespaced collection names
   - Connection management

### Phase 2: Component Updates (2 days)

1. **Update Core Components**
   - DocumentRegistry → collection-aware paths
   - IndexManager → use collection-specific Qdrant collections
   - KeywordIndex → collection-specific SQLite files
   - FingerprintStore → collection-specific database
   - JobStorage → per-collection job queues

2. **Storage Updates**
   - JSONL artifacts in collection directories
   - Cache isolation per collection
   - Proper path resolution

### Phase 3: CLI & Testing (1 day)

1. **CLI Commands**
   - Add `--collection` parameter
   - Implement collections command group
   - Update help documentation

2. **Testing**
   - Collection isolation tests
   - Cross-collection security tests
   - Performance benchmarks

3. **Migration Tools**
   - Single to multi-tenant migration
   - Collection import/export
   - Backup utilities

## Security & Isolation

### Data Isolation Guarantees

1. **Vector Storage**: Qdrant enforces collection-level isolation
2. **Keyword Search**: Separate SQLite files prevent cross-queries
3. **Document Registry**: Independent tracking per collection
4. **Cache**: No shared cache entries between collections
5. **Jobs**: Separate queues prevent job interference

### Security Measures

```python
class CollectionSecurityManager:
    """Handles collection access control and security."""

    def validate_collection_name(self, name: str) -> bool:
        """Ensure collection name is safe."""
        # No path traversal characters
        # No special characters
        # Length limits
        # Reserved name checks

    def check_access(self, user: str, collection: str, operation: str) -> bool:
        """Check if user can perform operation on collection."""
        # Future: Integrate with RBAC
        # For now: Basic validation only

    def audit_operation(self, user: str, collection: str, operation: str) -> None:
        """Log security-relevant operations."""
```

### Future RBAC Integration

```json
// access_control.json
{
  "roles": {
    "engineering_admin": {
      "collections": ["engineering", "engineering_test"],
      "permissions": ["read", "write", "delete", "admin"]
    },
    "engineering_user": {
      "collections": ["engineering"],
      "permissions": ["read", "write"]
    }
  },
  "users": {
    "alice@company.com": ["engineering_admin"],
    "bob@company.com": ["engineering_user"]
  }
}
```

## Performance Considerations

### Resource Usage

1. **Memory**: Only active collection loaded
2. **Disk**: Linear growth with collections
3. **CPU**: No additional overhead
4. **Network**: Qdrant handles efficiently

### Optimization Strategies

1. **Lazy Loading**: Load collection resources on demand
2. **Connection Pooling**: Reuse database connections
3. **Cache Warmup**: Optional per-collection cache preload
4. **Index Optimization**: Per-collection tuning possible

### Benchmarks

Expected performance characteristics:
- Collection switching: < 100ms
- Collection creation: < 2 seconds
- No degradation in query performance
- Linear storage growth

## Migration Plan

### From Single to Multi-Tenant

```python
def migrate_to_multi_tenant():
    """One-time migration from single collection to multi-tenant."""

    # 1. Create collections_v3 directory structure
    # 2. Create "default" collection
    # 3. Copy existing data to default collection:
    #    - Rename Qdrant collection: datasheets_v3 → datasheets_v3_default
    #    - Move SQLite files to collections_v3/default/
    #    - Move storage_data_v3 to collections_v3/default/storage_data/
    #    - Move cache_v3 to collections_v3/default/cache/
    # 4. Update configuration to enable multi-tenant mode
    # 5. Verify migration success
    # 6. Create backup of old structure
```

### Rollback Strategy

1. Keep original data for 30 days
2. Single command rollback capability
3. Verification before cleanup

## Future Enhancements

### Near Term (v3.1)

1. **Web UI**: Collection selection dropdown
2. **API**: Collection-aware REST endpoints
3. **Metrics**: Per-collection usage tracking
4. **Quotas**: Storage and document limits

### Long Term (v4.0)

1. **Full RBAC**: User and role management
2. **Cross-Collection Search**: With permissions
3. **Collection Templates**: Predefined configurations
4. **Federated Search**: Search across allowed collections

## Testing Strategy

### Unit Tests

```python
def test_collection_isolation():
    """Ensure no data leakage between collections."""

def test_collection_crud():
    """Test create, read, update, delete operations."""

def test_concurrent_collections():
    """Test multiple collections operating simultaneously."""
```

### Integration Tests

1. End-to-end document processing per collection
2. Search isolation verification
3. Migration testing
4. Performance benchmarks

### Security Tests

1. Path traversal attempts
2. SQL injection in collection names
3. Resource exhaustion protection
4. Access control verification

## Appendix

### A. Collection Naming Conventions

- Lowercase with underscores: `engineering_team`
- No special characters except underscore
- Maximum 50 characters
- Reserved names: `default`, `_global`, `test`

### B. Error Codes

| Code | Description |
|------|-------------|
| COL001 | Collection already exists |
| COL002 | Collection not found |
| COL003 | Invalid collection name |
| COL004 | Collection operation failed |
| COL005 | Access denied |

### C. Configuration Examples

```yaml
# Per-collection override example
collections:
  engineering:
    openai:
      vision_model: gpt-4-turbo
      max_retries: 5
    chunking:
      chunk_size: 2048
    processing:
      timeout_multiplier: 1.5
```

### D. CLI Usage Examples

```bash
# Create collection for new team
uv run python -m src.pipeline_v3.cli_main collections create marketing \
  --description "Marketing team documents" \
  --config-override openai.vision_model=gpt-4.1

# Migrate existing data to collection
uv run python -m src.pipeline_v3.cli_main collections import legacy_data.tar.gz \
  --name legacy_docs \
  --no-overwrite

# Daily backup of critical collection
uv run python -m src.pipeline_v3.cli_main collections export finance \
  --output /backups/finance_$(date +%Y%m%d).tar.gz \
  --compress
```

---

This architecture provides a robust foundation for multi-tenant document processing while maintaining the simplicity and reliability that makes Pipeline v3 successful.
