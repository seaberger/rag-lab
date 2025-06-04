# Production Pipeline v3 - Development Plan

## Executive Summary

This document outlines the complete development roadmap for transforming the stable v2.1 document pipeline into a production-ready enterprise system capable of handling large-scale document processing, lifecycle management, and advanced index operations.

## Problem Statement

The current v2.1 pipeline, while functional, has limitations for production use:

- **No queue management**: Synchronous processing unsuitable for large batches
- **Limited update capability**: Can't update/remove documents from indexes
- **No change detection**: Reprocesses all documents regardless of changes
- **No job persistence**: Can't resume interrupted processing
- **No index management**: No tools for consistency checking or maintenance

## Solution Overview

Transform the pipeline into a production system with:

1. **Queue-based processing** with configurable concurrency
2. **Document lifecycle management** (CRUD operations on indexes)
3. **Content fingerprinting** for intelligent change detection
4. **Enterprise management tools** for operations and monitoring
5. **Index consistency management** across multiple storage backends

## Detailed Development Plan

### Phase 1: Foundation Infrastructure (Week 1)
**Estimated Effort**: ~70,000 tokens

#### 1.1 Document Queue System
**File**: `queue/manager.py` (~400 lines)
```python
class DocumentQueue:
    """Queue-based document processing with job management."""
    
    def __init__(self, config: PipelineConfig):
        self.pending = PriorityQueue()
        self.processing = {}
        self.completed = {}
        self.failed = {}
        self.max_workers = config.queue.max_concurrent
    
    async def add_batch(self, sources: List[Union[str, Path]], priority: int = 0):
        """Add documents to processing queue with priority."""
        
    async def process_queue(self, max_concurrent: int = 5):
        """Process queue with configurable concurrency using asyncio."""
        
    def get_status(self) -> Dict:
        """Get queue status: pending, processing, completed, failed counts."""
        
    def pause_processing(self):
        """Pause queue processing (allow current jobs to finish)."""
        
    def resume_processing(self):
        """Resume paused queue processing."""
        
    def cancel_job(self, job_id: str):
        """Cancel specific job if not yet started."""
```

#### 1.2 Content Fingerprinting
**File**: `core/fingerprint.py` (~300 lines)
```python
class DocumentFingerprint:
    """Track document versions and detect changes."""
    
    def __init__(self, storage_path: str = "./fingerprints.db"):
        self.storage_path = storage_path
        self.conn = sqlite3.connect(storage_path)
        self._init_db()
    
    @staticmethod
    def compute_fingerprint(content: bytes, metadata: Dict) -> str:
        """SHA-256 hash of content + key metadata (filename, size, mtime)."""
        
    def has_changed(self, source: Union[str, Path], current_fingerprint: str) -> bool:
        """Check if document content has changed since last processing."""
        
    def update_fingerprint(self, source: Union[str, Path], fingerprint: str, doc_id: str):
        """Update stored fingerprint for document."""
        
    def get_document_history(self, source: Union[str, Path]) -> List[Dict]:
        """Get processing history for document."""
        
    def cleanup_old_fingerprints(self, older_than_days: int = 90):
        """Clean up fingerprints for documents not seen recently."""
```

#### 1.3 Job Persistence & Management
**File**: `queue/job.py` (~500 lines)
```python
class JobManager:
    """Persistent job tracking with resume capability."""
    
    def __init__(self, storage_path: str = "./jobs.db"):
        self.storage_path = storage_path
        self.conn = sqlite3.connect(storage_path)
        self._init_db()
    
    def create_job(self, source: str, job_type: str, priority: int = 0) -> str:
        """Create new job with unique ID."""
        
    def update_job_status(self, job_id: str, status: str, progress: float = 0.0, error: str = None):
        """Update job status: pending, processing, completed, failed."""
        
    def save_job_state(self, job_id: str, state: Dict):
        """Save intermediate job state for resume capability."""
        
    def resume_interrupted_jobs(self) -> List[Dict]:
        """Find and return jobs that were interrupted (status=processing)."""
        
    def get_job_status(self, job_id: str) -> Dict:
        """Get detailed job status and progress."""
        
    def list_jobs(self, status: str = None, limit: int = 100) -> List[Dict]:
        """List jobs with optional status filter."""
        
    def cleanup_completed_jobs(self, older_than_days: int = 7):
        """Remove old completed/failed job records."""
```

#### 1.4 Enhanced Core Pipeline
**File**: `core/pipeline.py` (~400 lines)
```python
async def smart_ingest_sources(
    sources: List[Union[str, Path]],
    *,
    force_reprocess: bool = False,
    update_mode: str = "auto",  # "auto", "add_only", "update_only", "skip_existing"
    max_concurrent: int = 5,
    priority: int = 0,
    config_file: str = "config.yaml"
) -> Dict:
    """Enhanced pipeline with queue management and lifecycle support."""
    
    config = PipelineConfig.from_yaml(config_file)
    
    # Initialize components
    queue = DocumentQueue(config)
    job_manager = JobManager(config.queue.job_storage_path)
    fingerprint_db = DocumentFingerprint(config.fingerprint.storage_path)
    index_manager = IndexManager(config)
    
    # Phase 1: Analyze sources and create jobs
    for src in sources:
        # Compute current fingerprint
        content = Path(src).read_bytes()
        current_fingerprint = DocumentFingerprint.compute_fingerprint(content, {})
        
        # Check if processing needed
        if not force_reprocess and not fingerprint_db.has_changed(src, current_fingerprint):
            logger.info(f"Document {src} unchanged, skipping")
            continue
            
        # Determine action needed
        action = determine_action(src, update_mode, index_manager)
        
        # Create job
        job_id = job_manager.create_job(str(src), action, priority)
        await queue.add_job(job_id, src, action, current_fingerprint)
    
    # Phase 2: Process queue
    results = await queue.process_queue(max_concurrent=max_concurrent)
    
    return {
        "total_jobs": len(sources),
        "processed": results.completed,
        "failed": results.failed,
        "skipped": results.skipped,
        "processing_time": results.total_time
    }
```

#### 1.5 Enhanced Configuration
**File**: `config.yaml` (~100 lines)
```yaml
# Extended configuration for production features
queue:
  max_concurrent: 10
  job_persistence: true
  job_storage_path: ./jobs.db
  job_retention_days: 30
  chunk_size: 100
  default_priority: 0
  
fingerprint:
  enabled: true
  storage_path: ./fingerprints.db
  retention_days: 90
  include_metadata: true  # Include file size, mtime in fingerprint
  
index_management:
  consistency_checks: true
  auto_backup: true
  backup_path: ./backups
  backup_retention_days: 90
  rebuild_on_corruption: true
  
monitoring:
  detailed_progress: true
  performance_metrics: true
  resource_monitoring: true
  alert_on_failures: true
```

### Phase 2: Index Lifecycle Management (Week 2)
**Estimated Effort**: ~80,000 tokens

#### 2.1 Index Manager
**File**: `index/manager.py` (~600 lines)
```python
class IndexManager:
    """Comprehensive index lifecycle management."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.vector_store = self._init_vector_store()
        self.keyword_index = self._init_keyword_index()
        self.document_registry = DocumentRegistry(config.registry.storage_path)
    
    async def add_document(self, doc_id: str, nodes: List[TextNode], 
                          pairs: List[Tuple], source: str) -> bool:
        """Add new document to both indexes."""
        
    async def update_document(self, doc_id: str, nodes: List[TextNode], 
                             pairs: List[Tuple], source: str) -> bool:
        """Replace existing document in both indexes."""
        
    async def remove_document(self, doc_id: str) -> bool:
        """Remove document from both indexes and registry."""
        
    def document_exists(self, doc_id: str) -> bool:
        """Check if document exists in indexes."""
        
    def list_documents(self, source_filter: str = None) -> List[Dict]:
        """List all indexed documents with metadata."""
        
    async def batch_operations(self, operations: List[Dict]) -> Dict:
        """Execute multiple add/update/remove operations efficiently."""
        
    def get_index_stats(self) -> Dict:
        """Get comprehensive index statistics."""
```

#### 2.2 Enhanced Storage Operations
**Files**: `storage/vector.py`, `storage/keyword.py` (~400 lines total)

Enhanced vector and keyword storage with:
- Individual document update/remove operations
- Batch operation optimization
- Transaction support for consistency
- Performance monitoring

#### 2.3 Index Consistency Management
**File**: `index/consistency.py` (~300 lines)
```python
class IndexConsistencyManager:
    """Ensure consistency between vector and keyword indexes."""
    
    def verify_consistency(self) -> Dict:
        """Check if both indexes have same documents."""
        
    def find_orphaned_documents(self) -> Dict:
        """Find documents in one index but not the other."""
        
    def repair_consistency(self, auto_fix: bool = False) -> Dict:
        """Repair consistency issues between indexes."""
        
    def backup_indexes(self, backup_path: Path, compress: bool = True) -> bool:
        """Create comprehensive backup of all indexes."""
        
    def restore_indexes(self, backup_path: Path) -> bool:
        """Restore indexes from backup."""
        
    def rebuild_index(self, index_type: str = "both") -> Dict:
        """Rebuild indexes from stored artifacts."""
```

### Phase 3: CLI Tools & Management (Week 3)
**Estimated Effort**: ~50,000 tokens

#### 3.1 Batch Processing CLI
**File**: `cli/batch.py` (~400 lines)
```bash
# Usage examples:
python cli/batch.py --src "docs/**/*.pdf" --max-concurrent 10 --mode auto
python cli/batch.py --src folder/ --force-reprocess --with-keywords
python cli/batch.py --resume-jobs  # Resume interrupted processing
python cli/batch.py --status       # Show current processing status
```

#### 3.2 Index Management CLI  
**File**: `cli/manage.py` (~500 lines)
```bash
# Document lifecycle operations
python cli/manage.py --add new_document.pdf --with-keywords
python cli/manage.py --update doc_id --src new_version.pdf  
python cli/manage.py --remove doc_id
python cli/manage.py --list --filter "*.pdf"

# Index management operations
python cli/manage.py --verify-consistency
python cli/manage.py --repair-consistency --auto-fix
python cli/manage.py --backup ./backups/2025-06-04/
python cli/manage.py --restore ./backups/2025-06-04/
python cli/manage.py --rebuild-index vector
python cli/manage.py --stats
```

#### 3.3 Monitoring & Status CLI
**File**: `cli/monitor.py` (~300 lines)
```bash
# Real-time monitoring
python cli/monitor.py --live           # Live processing status
python cli/monitor.py --jobs           # Job queue status
python cli/monitor.py --performance    # Performance metrics
python cli/monitor.py --resources      # Resource usage
python cli/monitor.py --health-check   # System health
```

## Implementation Timeline

### Week 1: Foundation (Phase 1)
- **Days 1-2**: Document queue system and job management
- **Days 3-4**: Content fingerprinting and change detection  
- **Days 5-7**: Enhanced core pipeline integration and testing

### Week 2: Index Management (Phase 2)  
- **Days 1-3**: Index manager and lifecycle operations
- **Days 4-5**: Enhanced storage operations with update/remove
- **Days 6-7**: Consistency management and backup/restore

### Week 3: CLI & Polish (Phase 3)
- **Days 1-2**: Batch processing CLI
- **Days 3-4**: Management CLI tools
- **Days 5-7**: Monitoring, documentation, and final testing

## Testing Strategy

### Unit Tests
- Individual component testing for all new classes
- Mock external dependencies (OpenAI API, Qdrant, SQLite)
- Test edge cases and error conditions

### Integration Tests  
- End-to-end pipeline testing with real documents
- Queue processing with various concurrency levels
- Index consistency across multiple operations
- Resume interrupted processing scenarios

### Performance Tests
- Large batch processing (1000+ documents)
- Concurrent operation stress testing
- Memory usage and resource monitoring
- Index operation performance benchmarks

## Migration Strategy

### Backward Compatibility
- v3 can read existing v2.1 artifacts and indexes
- Configuration migration utility
- Side-by-side operation during transition

### Migration Path
1. **Phase A**: Deploy v3 alongside v2.1 (no disruption)
2. **Phase B**: Migrate existing indexes to v3 format  
3. **Phase C**: Switch processing to v3 pipeline
4. **Phase D**: Deprecate v2.1 after validation period

## Risk Mitigation

### Technical Risks
- **Index corruption**: Comprehensive backup/restore system
- **Performance degradation**: Benchmarking and optimization
- **Memory issues**: Resource monitoring and limits

### Operational Risks  
- **Migration failures**: Rollback procedures and testing
- **Data loss**: Multiple backup strategies
- **Downtime**: Blue-green deployment approach

## Success Metrics

### Performance Targets
- **Throughput**: 10x improvement in large batch processing
- **Reliability**: 99.9% job completion rate
- **Recovery**: < 1 minute to resume interrupted processing
- **Consistency**: 100% index consistency verification

### Feature Completeness
- ✅ Queue-based processing with configurable concurrency
- ✅ Document lifecycle management (CRUD operations)
- ✅ Content fingerprinting and change detection
- ✅ Index consistency management and repair
- ✅ Comprehensive CLI tools for operations
- ✅ Enterprise monitoring and alerting

This development plan provides a clear roadmap for building a production-ready document processing pipeline while maintaining stability and providing clear migration paths.