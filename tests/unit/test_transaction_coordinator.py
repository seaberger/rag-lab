"""
Unit tests for TransactionCoordinator

Tests the core transaction functionality including:
- Successful transactions
- Prepare phase failures
- Commit phase failures
- Rollback operations
- Timeout handling
"""

import asyncio
import pytest
from datetime import datetime
from uuid import UUID, uuid4

from src.pipeline_v3.core.transaction_coordinator import (
    Checkpoint, OperationType, StorageSystem, TransactionCoordinator,
    TransactionError, TransactionOperation, TransactionState
)


class MockStorageSystem(StorageSystem):
    """Mock storage system for testing"""
    
    def __init__(self, name: str, should_fail: str = None, delay: float = 0):
        super().__init__(name)
        self.should_fail = should_fail  # 'prepare', 'commit', 'rollback', or None
        self.delay = delay
        self.prepare_called = False
        self.commit_called = False
        self.rollback_called = False
        self.prepared_data = {}
        
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """Mock prepare"""
        self.prepare_called = True
        
        if self.delay:
            await asyncio.sleep(self.delay)
            
        if self.should_fail == 'prepare':
            raise Exception(f"{self.name} prepare failed")
            
        checkpoint = Checkpoint(
            system_name=self.name,
            operation_id=operation_id,
            doc_id=operation.doc_id,
            operation_type=operation.operation_type,
            state_before={"exists": False}
        )
        
        self.prepared_data[operation_id] = operation
        return checkpoint
    
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """Mock commit"""
        self.commit_called = True
        
        if self.delay:
            await asyncio.sleep(self.delay)
            
        if self.should_fail == 'commit':
            raise Exception(f"{self.name} commit failed")
            
        return True
    
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """Mock rollback"""
        self.rollback_called = True
        
        if self.delay:
            await asyncio.sleep(self.delay)
            
        if self.should_fail == 'rollback':
            raise Exception(f"{self.name} rollback failed")
            
        return True
    
    async def verify_state(self, doc_id: str) -> dict:
        """Mock verify state"""
        return {"exists": self.commit_called}
    
    async def health_check(self) -> bool:
        """Mock health check"""
        return self.should_fail != 'unhealthy'


class TestTransactionCoordinator:
    """Test cases for TransactionCoordinator"""
    
    @pytest.mark.asyncio
    async def test_successful_transaction(self):
        """Test successful atomic operation across all systems"""
        # Setup
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2"),
            MockStorageSystem("System3")
        ]
        
        coordinator = TransactionCoordinator(systems, timeout=5.0)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_123",
            data={
                "nodes": ["node1", "node2"],
                "content": "test content",
                "file_path": "/test/path"
            },
            metadata={"key": "value"}
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is True
        assert errors == []
        assert details["doc_id"] == "test_doc_123"
        assert details["state"] == TransactionState.COMMITTED.value
        
        # All systems should have been called
        for system in systems:
            assert system.prepare_called
            assert system.commit_called
            assert not system.rollback_called
    
    @pytest.mark.asyncio
    async def test_prepare_phase_failure(self):
        """Test rollback when prepare fails on one system"""
        # Setup - System2 will fail during prepare
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2", should_fail='prepare'),
            MockStorageSystem("System3")
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_456",
            data={
                "nodes": ["node1"],
                "content": "test",
                "file_path": "/test"
            }
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        assert len(errors) > 0
        assert "System2" in errors[0]
        assert "prepare failed" in errors[0]
        
        # System1 should have been rolled back
        assert systems[0].prepare_called
        assert not systems[0].commit_called
        assert systems[0].rollback_called
        
        # System2 failed prepare, no rollback needed
        assert systems[1].prepare_called
        assert not systems[1].commit_called
        assert not systems[1].rollback_called
        
        # System3 might have been prepared (parallel execution)
        # but should be rolled back if it was
        if systems[2].prepare_called:
            assert systems[2].rollback_called
    
    @pytest.mark.asyncio
    async def test_commit_phase_failure(self):
        """Test rollback when commit fails on one system"""
        # Setup - System2 will fail during commit
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2", should_fail='commit'),
            MockStorageSystem("System3")
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.UPDATE_DOCUMENT,
            doc_id="test_doc_789",
            data={
                "nodes": ["node1"],
                "content": "updated",
                "file_path": "/test"
            }
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        assert len(errors) > 0
        assert "System2" in errors[0]
        assert "commit failed" in errors[0]
        
        # All systems should have prepared and rolled back
        for system in systems:
            assert system.prepare_called
            assert system.rollback_called
    
    @pytest.mark.asyncio
    async def test_partial_commit_failure(self):
        """Test handling when some systems commit successfully before failure"""
        # Setup - System3 will fail during commit
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2"),
            MockStorageSystem("System3", should_fail='commit')
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.DELETE_DOCUMENT,
            doc_id="test_doc_999",
            data={}
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        assert len(errors) > 0
        
        # All systems should have rolled back
        for system in systems:
            assert system.prepare_called
            assert system.rollback_called
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """Test transaction timeout during prepare phase"""
        # Setup - System2 will take too long
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2", delay=2.0),  # Longer than timeout
            MockStorageSystem("System3")
        ]
        
        coordinator = TransactionCoordinator(systems, timeout=1.0)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_timeout",
            data={
                "nodes": ["node1"],
                "content": "test",
                "file_path": "/test"
            }
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        assert any("timeout" in error.lower() for error in errors)
        
        # System1 should have been rolled back
        assert systems[0].rollback_called
    
    @pytest.mark.asyncio
    async def test_rollback_failure_handling(self):
        """Test that rollback failures are logged but don't stop other rollbacks"""
        # Setup - System1 will fail during rollback
        systems = [
            MockStorageSystem("System1", should_fail='rollback'),
            MockStorageSystem("System2"),
            MockStorageSystem("System3", should_fail='commit')  # Trigger rollback
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_rb_fail",
            data={
                "nodes": ["node1"],
                "content": "test",
                "file_path": "/test"
            }
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        
        # All systems should have attempted rollback despite System1 failure
        assert systems[0].rollback_called
        assert systems[1].rollback_called
        assert systems[2].rollback_called
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test transaction abort when systems are unhealthy"""
        # Setup - System2 is unhealthy
        systems = [
            MockStorageSystem("System1"),
            MockStorageSystem("System2", should_fail='unhealthy'),
            MockStorageSystem("System3")
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_health",
            data={
                "nodes": ["node1"],
                "content": "test",
                "file_path": "/test"
            }
        )
        
        # Execute
        success, errors, details = await coordinator.execute_transaction(operation)
        
        # Verify
        assert success is False
        assert any("unhealthy" in error.lower() for error in errors)
        
        # No system should have been called
        for system in systems:
            assert not system.prepare_called
            assert not system.commit_called
    
    @pytest.mark.asyncio
    async def test_transaction_logging(self):
        """Test that transactions are properly logged"""
        systems = [MockStorageSystem("System1")]
        coordinator = TransactionCoordinator(systems)
        
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_log",
            data={
                "nodes": ["node1"],
                "content": "test",
                "file_path": "/test"
            }
        )
        
        # Execute
        await coordinator.execute_transaction(operation)
        
        # Verify
        log = coordinator.get_transaction_log()
        assert len(log) == 1
        assert log[0]["doc_id"] == "test_doc_log"
        assert log[0]["state"] == TransactionState.COMMITTED.value
        assert "transaction_id" in log[0]
        assert "duration_ms" in log[0]
    
    @pytest.mark.asyncio
    async def test_invalid_operation_validation(self):
        """Test that invalid operations are rejected"""
        systems = [MockStorageSystem("System1")]
        coordinator = TransactionCoordinator(systems)
        
        # Missing required doc_id
        with pytest.raises(ValueError):
            operation = TransactionOperation(
                operation_type=OperationType.ADD_DOCUMENT,
                doc_id="",  # Invalid
                data={}
            )
        
        # Missing required data for ADD_DOCUMENT
        with pytest.raises(ValueError):
            operation = TransactionOperation(
                operation_type=OperationType.ADD_DOCUMENT,
                doc_id="test",
                data={"content": "test"}  # Missing nodes and file_path
            )
    
    @pytest.mark.asyncio
    async def test_concurrent_transactions(self):
        """Test that multiple transactions can run concurrently"""
        systems = [
            MockStorageSystem("System1", delay=0.1),
            MockStorageSystem("System2", delay=0.1)
        ]
        
        coordinator = TransactionCoordinator(systems)
        
        operations = [
            TransactionOperation(
                operation_type=OperationType.ADD_DOCUMENT,
                doc_id=f"test_doc_{i}",
                data={
                    "nodes": [f"node_{i}"],
                    "content": f"content_{i}",
                    "file_path": f"/test_{i}"
                }
            )
            for i in range(3)
        ]
        
        # Execute concurrently
        start_time = datetime.now()
        tasks = [
            coordinator.execute_transaction(op) 
            for op in operations
        ]
        results = await asyncio.gather(*tasks)
        duration = (datetime.now() - start_time).total_seconds()
        
        # Verify
        assert all(r[0] for r in results)  # All successful
        assert duration < 0.5  # Should run in parallel, not 0.6s sequential
        
        # Check transaction log
        log = coordinator.get_transaction_log()
        assert len(log) == 3
        assert {entry["doc_id"] for entry in log} == {
            "test_doc_0", "test_doc_1", "test_doc_2"
        }