# Issue #27: Cross-System Consistency Guarantees - Implementation Plan

## Overview
Implement distributed transaction-like behavior with rollback capabilities to ensure data consistency across Pipeline v3's multiple storage systems (SQLite, Qdrant, JSONL).

## Problem Statement
Pipeline v3 uses 5 separate storage systems that can become inconsistent during failures:
1. **DocumentRegistry** (`document_registry_v3.db`) - Document metadata
2. **Qdrant Vector Store** (`qdrant_data_v3/`) - Vector embeddings  
3. **Keyword Index** (`keyword_index_v3.db`) - Full-text search
4. **JSONL Artifacts** (`storage_data_v3/`) - Raw storage
5. **Fingerprint Store** (`fingerprints_v3.db`) - Change detection

When operations partially fail, the system enters an inconsistent state that's difficult to detect and recover from.

## Implementation Approach

### Phase 1: Core Infrastructure (Days 1-2)

#### 1.1 Transaction Coordinator Framework
**File**: `src/pipeline_v3/core/transaction_coordinator.py`

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4
import logging
from enum import Enum

class OperationType(Enum):
    ADD_DOCUMENT = "add_document"
    UPDATE_DOCUMENT = "update_document"
    DELETE_DOCUMENT = "delete_document"
    REINDEX_DOCUMENT = "reindex_document"

@dataclass
class TransactionOperation:
    """Represents an atomic operation across systems"""
    operation_type: OperationType
    doc_id: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]

@dataclass
class Checkpoint:
    """Checkpoint data for rollback"""
    system_name: str
    operation_id: UUID
    state_before: Dict[str, Any]
    state_after: Optional[Dict[str, Any]] = None
    
class StorageSystem(ABC):
    """Base class for storage systems with transactional support"""
    
    @abstractmethod
    async def prepare(self, operation: TransactionOperation) -> Checkpoint:
        """Prepare the operation and return checkpoint data"""
        pass
    
    @abstractmethod
    async def commit(self, operation_id: UUID) -> bool:
        """Commit the prepared operation"""
        pass
    
    @abstractmethod
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Rollback using checkpoint data"""
        pass
    
    @abstractmethod
    async def verify_state(self, doc_id: str) -> Dict[str, Any]:
        """Verify current state of a document"""
        pass

class TransactionCoordinator:
    """Coordinates atomic operations across multiple storage systems"""
    
    def __init__(self, systems: List[StorageSystem]):
        self.systems = systems
        self.logger = logging.getLogger(__name__)
        
    async def execute_transaction(self, operation: TransactionOperation) -> Tuple[bool, List[str]]:
        """Execute operation atomically across all systems"""
        operation_id = uuid4()
        checkpoints = []
        errors = []
        
        # Phase 1: Prepare all systems
        for system in self.systems:
            try:
                checkpoint = await system.prepare(operation)
                checkpoints.append(checkpoint)
            except Exception as e:
                errors.append(f"{system.__class__.__name__}: {str(e)}")
                # Rollback any prepared systems
                await self._rollback_all(checkpoints)
                return False, errors
        
        # Phase 2: Commit all systems
        commit_failures = []
        for i, system in enumerate(self.systems):
            try:
                success = await system.commit(operation_id)
                if not success:
                    commit_failures.append(i)
            except Exception as e:
                commit_failures.append(i)
                errors.append(f"Commit failed for {system.__class__.__name__}: {str(e)}")
        
        # Phase 3: Handle commit failures
        if commit_failures:
            # Attempt to rollback all systems
            await self._rollback_all(checkpoints)
            return False, errors
            
        return True, []
    
    async def _rollback_all(self, checkpoints: List[Checkpoint]) -> None:
        """Rollback all checkpoints"""
        for checkpoint in reversed(checkpoints):
            try:
                system = self._get_system_by_name(checkpoint.system_name)
                await system.rollback(checkpoint)
            except Exception as e:
                self.logger.error(f"Rollback failed for {checkpoint.system_name}: {e}")
```

#### 1.2 Storage System Adapters
**File**: `src/pipeline_v3/core/storage_adapters.py`

```python
class RegistryAdapter(StorageSystem):
    """Adapter for DocumentRegistry with transactional support"""
    
    def __init__(self, registry: DocumentRegistry):
        self.registry = registry
        self.pending_operations = {}
        
    async def prepare(self, operation: TransactionOperation) -> Checkpoint:
        # Capture current state
        current_state = self.registry.get_document(operation.doc_id)
        checkpoint = Checkpoint(
            system_name="DocumentRegistry",
            operation_id=uuid4(),
            state_before=current_state.dict() if current_state else None
        )
        
        # Store pending operation
        self.pending_operations[checkpoint.operation_id] = operation
        
        return checkpoint
    
    async def commit(self, operation_id: UUID) -> bool:
        operation = self.pending_operations.get(operation_id)
        if not operation:
            return False
            
        if operation.operation_type == OperationType.ADD_DOCUMENT:
            return self.registry.add_document(
                operation.doc_id,
                operation.data['file_path'],
                operation.metadata
            )
        # Handle other operations...
        
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        if checkpoint.state_before:
            # Restore previous state
            return self.registry.update_document_state(
                checkpoint.state_before['doc_id'],
                checkpoint.state_before['state']
            )
        else:
            # Document didn't exist before, remove it
            return self.registry.remove_document(
                self.pending_operations[checkpoint.operation_id].doc_id
            )

class QdrantAdapter(StorageSystem):
    """Adapter for Qdrant with transactional support"""
    
    def __init__(self, qdrant_client, collection_name):
        self.client = qdrant_client
        self.collection = collection_name
        self.prepared_points = {}
        
    async def prepare(self, operation: TransactionOperation) -> Checkpoint:
        # Similar implementation for Qdrant
        pass

# Similar adapters for KeywordIndex, StorageArtifacts, FingerprintStore
```

### Phase 2: Consistency Checker (Day 3)

#### 2.1 Consistency Verification
**File**: `src/pipeline_v3/core/consistency_checker.py`

```python
@dataclass
class ConsistencyReport:
    """Report of consistency check results"""
    timestamp: datetime
    total_documents: int
    consistent_documents: int
    inconsistencies: List[DocumentInconsistency]
    
@dataclass
class DocumentInconsistency:
    """Details of document inconsistency"""
    doc_id: str
    missing_from: List[str]
    state_mismatches: Dict[str, Dict[str, Any]]
    
class ConsistencyChecker:
    """Verifies and repairs consistency across storage systems"""
    
    def __init__(self, registry, index_manager, storage_manager, fingerprint_manager):
        self.registry = registry
        self.index_manager = index_manager
        self.storage_manager = storage_manager
        self.fingerprint_manager = fingerprint_manager
        
    async def check_all_documents(self) -> ConsistencyReport:
        """Check consistency of all documents"""
        all_doc_ids = self._get_all_document_ids()
        inconsistencies = []
        
        for doc_id in all_doc_ids:
            inconsistency = await self._check_document(doc_id)
            if inconsistency:
                inconsistencies.append(inconsistency)
                
        return ConsistencyReport(
            timestamp=datetime.now(),
            total_documents=len(all_doc_ids),
            consistent_documents=len(all_doc_ids) - len(inconsistencies),
            inconsistencies=inconsistencies
        )
    
    async def repair_inconsistencies(self, report: ConsistencyReport, strategy: RepairStrategy):
        """Attempt to repair detected inconsistencies"""
        repaired = []
        failed = []
        
        for inconsistency in report.inconsistencies:
            try:
                await self._repair_document(inconsistency, strategy)
                repaired.append(inconsistency.doc_id)
            except Exception as e:
                failed.append((inconsistency.doc_id, str(e)))
                
        return {"repaired": repaired, "failed": failed}
```

### Phase 3: Integration (Days 4-5)

#### 3.1 Enhanced Index Manager
**File**: Update `src/pipeline_v3/core/index_manager.py`

```python
class IndexManager:
    def __init__(self, config, enable_transactions=True):
        # Existing initialization...
        self.enable_transactions = enable_transactions
        if enable_transactions:
            self._init_transaction_support()
    
    def _init_transaction_support(self):
        """Initialize transaction coordinator"""
        self.transaction_coordinator = TransactionCoordinator([
            RegistryAdapter(self.registry),
            QdrantAdapter(self.qdrant_client, self.collection_name),
            KeywordAdapter(self.keyword_conn),
            StorageAdapter(self.storage_manager),
            FingerprintAdapter(self.fingerprint_store)
        ])
    
    async def add_document_atomic(self, doc_id: str, nodes: List[Node], metadata: Dict):
        """Add document with atomic guarantees"""
        if not self.enable_transactions:
            # Fall back to non-atomic for backwards compatibility
            return await self.add_document(doc_id, nodes, metadata)
            
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id=doc_id,
            data={"nodes": nodes},
            metadata=metadata
        )
        
        success, errors = await self.transaction_coordinator.execute_transaction(operation)
        if not success:
            raise TransactionError(f"Failed to add document atomically: {errors}")
            
        return True
```

### Phase 4: Testing Strategy (Days 6-7)

#### 4.1 Unit Tests
**File**: `tests/unit/test_transaction_coordinator.py`

```python
class TestTransactionCoordinator:
    async def test_successful_transaction(self):
        """Test successful atomic operation"""
        
    async def test_prepare_phase_failure(self):
        """Test rollback when prepare fails"""
        
    async def test_commit_phase_failure(self):
        """Test rollback when commit fails"""
        
    async def test_partial_commit_failure(self):
        """Test handling of partial commit failures"""
```

#### 4.2 Integration Tests
**File**: `tests/integration/test_consistency.py`

```python
class TestConsistency:
    async def test_add_document_atomic(self):
        """Test atomic document addition"""
        
    async def test_consistency_checker(self):
        """Test consistency verification"""
        
    async def test_automatic_repair(self):
        """Test automatic inconsistency repair"""
```

#### 4.3 Failure Injection Tests
**File**: `tests/integration/test_failure_scenarios.py`

```python
class TestFailureScenarios:
    async def test_network_failure_during_commit(self):
        """Simulate network failure during commit phase"""
        
    async def test_disk_full_during_operation(self):
        """Simulate disk full errors"""
        
    async def test_concurrent_operations(self):
        """Test consistency with concurrent operations"""
```

## Implementation Timeline

### Week 1
- **Days 1-2**: Core infrastructure (TransactionCoordinator, StorageSystem adapters)
- **Day 3**: Consistency checker implementation
- **Days 4-5**: Integration with existing components

### Week 2
- **Days 6-7**: Comprehensive testing
- **Day 8**: Performance optimization
- **Days 9-10**: Documentation and monitoring

## Rollout Strategy

1. **Feature Flag**: Add `enable_atomic_operations` config flag (default: false)
2. **Gradual Rollout**: 
   - Enable for new documents first
   - Monitor performance and reliability
   - Enable for updates/deletes
   - Make default after validation
3. **Backwards Compatibility**: Keep non-atomic operations available

## Success Metrics

1. **Zero inconsistencies** in normal operation
2. **100% rollback success** for simulated failures
3. **< 10% performance overhead** for atomic operations
4. **Automatic repair success rate > 95%**

## Risks and Mitigations

1. **Performance Impact**
   - Risk: Atomic operations slower
   - Mitigation: Optimize critical path, async where possible

2. **Complexity**
   - Risk: Harder to debug issues
   - Mitigation: Comprehensive logging, monitoring dashboard

3. **Backwards Compatibility**
   - Risk: Breaking existing workflows
   - Mitigation: Feature flag, gradual rollout

## Definition of Done

- [ ] TransactionCoordinator implemented and tested
- [ ] All 5 storage systems support atomic operations
- [ ] Consistency checker detects and repairs issues
- [ ] Integration tests pass with failure injection
- [ ] Performance benchmarks meet targets
- [ ] Monitoring and alerting configured
- [ ] Documentation complete
- [ ] Code review approved
- [ ] Deployed behind feature flag