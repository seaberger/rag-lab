# Pipeline v3 - Technical Architecture

## System Overview

Pipeline v3 is designed as a distributed, queue-based document processing system with enterprise-grade reliability, scalability, and management capabilities.

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Pipeline v3 Architecture                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐         │
│  │    CLI      │    │  Monitoring │    │   Config    │         │
│  │   Tools     │    │ & Alerting  │    │ Management  │         │
│  └─────────────┘    └─────────────┘    └─────────────┘         │
│         │                   │                   │               │
├─────────┼───────────────────┼───────────────────┼───────────────┤
│         │                   │                   │               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Queue Management Layer                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │ Document    │  │ Job Manager │  │ Scheduler   │     │   │
│  │  │ Queue       │  │ & Persist   │  │ & Priority  │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                                                       │
├─────────┼───────────────────────────────────────────────────────┤
│         │                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             Core Processing Engine                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │ Document    │  │ Fingerprint │  │ Pipeline    │     │   │
│  │  │ Classifier  │  │ & Change    │  │ Orchestrator│     │   │
│  │  │             │  │ Detection   │  │             │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                                                       │
├─────────┼───────────────────────────────────────────────────────┤
│         │                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │             Index Management Layer                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │ Index       │  │ Consistency │  │ Backup &    │     │   │
│  │  │ Manager     │  │ Checker     │  │ Recovery    │     │   │
│  │  │ (CRUD)      │  │             │  │             │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                                                       │
├─────────┼───────────────────────────────────────────────────────┤
│         │                                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Storage Layer                              │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │   │
│  │  │ Vector      │  │ Keyword     │  │ Artifacts   │     │   │
│  │  │ Store       │  │ Index       │  │ & Metadata  │     │   │
│  │  │ (Qdrant)    │  │ (SQLite)    │  │ (JSONL)     │     │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Queue Management Layer

**DocumentQueue** (`queue/manager.py`)
- Priority-based job scheduling
- Configurable concurrency (1-50 workers)
- Automatic retry with exponential backoff
- Real-time progress tracking
- Pause/resume capability

**JobManager** (`queue/job.py`)
- Persistent job state in SQLite
- Resume interrupted processing
- Job history and audit trail
- Cleanup of old job records
- Job status API for monitoring

**Scheduler** (`queue/scheduler.py`)
- Worker pool management
- Load balancing across workers
- Resource usage monitoring
- Adaptive concurrency scaling

### 2. Core Processing Engine

**DocumentClassifier** (Enhanced from v2.1)
- Extended classification logic
- Confidence scoring improvements
- Custom classification rules
- Integration with fingerprinting

**FingerprintManager** (`core/fingerprint.py`)
- SHA-256 content + metadata hashing
- Change detection logic
- Version history tracking
- Cleanup of stale fingerprints

**PipelineOrchestrator** (`core/pipeline.py`)
- Main processing workflow
- Integration with all subsystems
- Error handling and recovery
- Performance metrics collection

### 3. Index Management Layer

**IndexManager** (`index/manager.py`)
- CRUD operations on indexes
- Transaction support
- Batch operation optimization
- Cross-index consistency

**ConsistencyChecker** (`index/consistency.py`)
- Vector/keyword index synchronization
- Orphaned document detection
- Automatic repair capabilities
- Health monitoring

**BackupManager** (`index/backup.py`)
- Incremental and full backups
- Compression and encryption
- Automated backup scheduling
- Point-in-time recovery

### 4. Storage Layer

**Enhanced Vector Store** (`storage/vector.py`)
- Individual document operations
- Batch update optimization
- Metadata filtering
- Performance monitoring

**Enhanced Keyword Index** (`storage/keyword.py`)
- Document update/remove operations
- Index optimization
- Full-text search improvements
- Statistics and analytics

**Artifact Manager** (`storage/artifacts.py`)
- JSONL artifact management
- Compression and archiving
- Retention policy enforcement
- Quick retrieval by doc_id

## Data Flow

### 1. Document Ingestion Flow
```
Source Documents → Queue → Fingerprinting → Classification → Processing → Dual Indexing
```

### 2. Update Flow
```
Changed Document → Fingerprint Check → Remove Old → Process New → Update Indexes
```

### 3. Search Flow
```
Query → Index Manager → Hybrid Search → Result Fusion → Response
```

## Scalability Design

### Horizontal Scaling
- **Worker Pool**: Configurable number of processing workers
- **Queue Sharding**: Partition large queues by document type
- **Index Sharding**: Support for distributed Qdrant clusters
- **Load Balancing**: Distribute processing across available resources

### Vertical Scaling
- **Memory Management**: Configurable chunk sizes and batch limits
- **CPU Optimization**: Parallel processing within workers
- **I/O Optimization**: Async operations and connection pooling
- **Cache Utilization**: Intelligent caching at multiple levels

## Reliability & Fault Tolerance

### Error Handling
- **Graceful Degradation**: Continue processing on partial failures
- **Retry Logic**: Exponential backoff with jitter
- **Circuit Breakers**: Prevent cascade failures
- **Dead Letter Queue**: Isolate persistently failing jobs

### Data Integrity
- **Checksums**: Verify data integrity at each stage
- **Transactions**: ACID compliance for critical operations
- **Backups**: Automated backup with versioning
- **Validation**: Schema validation for all data

### Monitoring & Alerting
- **Health Checks**: Component status monitoring
- **Performance Metrics**: Throughput, latency, error rates
- **Resource Monitoring**: CPU, memory, disk usage
- **Alert Integration**: Configurable alerting thresholds

## Security Considerations

### Access Control
- **API Authentication**: Secure API endpoints
- **Role-Based Access**: Different permissions for operations
- **Audit Logging**: Complete audit trail of operations
- **Data Encryption**: Encryption at rest and in transit

### Data Privacy
- **PII Detection**: Identify and handle sensitive data
- **Data Masking**: Mask sensitive information in logs
- **Retention Policies**: Automatic cleanup of old data
- **Compliance**: GDPR/CCPA compliance features

## Performance Characteristics

### Throughput Targets
- **Small Documents** (< 1MB): 100+ docs/minute
- **Large Documents** (> 10MB): 10+ docs/minute
- **Batch Processing**: 1000+ docs/hour sustained
- **Index Operations**: < 1s for individual operations

### Latency Targets
- **Search Queries**: < 100ms hybrid search
- **Status Updates**: < 10ms queue status
- **Health Checks**: < 5ms component status
- **Job Submission**: < 50ms queue insertion

### Resource Usage
- **Memory**: < 4GB for 1000 concurrent documents
- **CPU**: Configurable based on available cores
- **Disk**: Efficient storage with compression
- **Network**: Minimal external API calls with caching

## Integration Points

### External APIs
- **OpenAI API**: Vision, embeddings, keyword generation
- **File Systems**: Local and network file access
- **Databases**: SQLite, Qdrant, external databases
- **Monitoring**: Prometheus, Grafana, custom dashboards

### Internal APIs
- **Queue API**: Job submission and status
- **Index API**: CRUD operations on documents
- **Search API**: Query processing and results
- **Management API**: System administration

This architecture provides a robust foundation for enterprise-scale document processing while maintaining simplicity and operational efficiency.