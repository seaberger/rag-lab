"""
Transaction Coordinator for Cross-System Consistency

Implements distributed transaction-like behavior with two-phase commit
and rollback capabilities across Pipeline v3's storage systems.

This module addresses Issue #27: No Cross-System Consistency Guarantees
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """Types of operations that can be performed atomically"""

    ADD_DOCUMENT = "add_document"
    UPDATE_DOCUMENT = "update_document"
    DELETE_DOCUMENT = "delete_document"
    REINDEX_DOCUMENT = "reindex_document"
    UPDATE_METADATA = "update_metadata"


class TransactionState(Enum):
    """States of a distributed transaction"""

    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


@dataclass
class TransactionOperation:
    """Represents an atomic operation across systems"""

    operation_type: OperationType
    doc_id: str
    data: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """Validate operation data"""
        if not self.doc_id:
            raise ValueError("doc_id is required for all operations")

        # Validate required data based on operation type
        if self.operation_type == OperationType.ADD_DOCUMENT:
            required = {"nodes", "content", "file_path"}
            if not all(k in self.data for k in required):
                raise ValueError(f"ADD_DOCUMENT requires: {required}")


@dataclass
class Checkpoint:
    """Checkpoint data for rollback"""

    system_name: str
    operation_id: UUID
    doc_id: str
    operation_type: OperationType
    state_before: dict[str, Any] | None = None
    state_after: dict[str, Any] | None = None
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert checkpoint to dictionary for logging"""
        return {
            "system_name": self.system_name,
            "operation_id": str(self.operation_id),
            "doc_id": self.doc_id,
            "operation_type": self.operation_type.value,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "error": self.error,
        }


class StorageSystem(ABC):
    """Base class for storage systems with transactional support"""

    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def prepare(self, operation: TransactionOperation, operation_id: UUID) -> Checkpoint:
        """
        Prepare the operation and return checkpoint data.

        This method should:
        1. Validate the operation can be performed
        2. Capture current state for rollback
        3. Prepare any resources needed for commit
        4. Return checkpoint with state information
        """

    @abstractmethod
    async def commit(self, checkpoint: Checkpoint) -> bool:
        """
        Commit the prepared operation.

        This method should:
        1. Apply the prepared changes
        2. Make changes permanent
        3. Clean up any temporary resources
        4. Return success status
        """

    @abstractmethod
    async def rollback(self, checkpoint: Checkpoint) -> bool:
        """
        Rollback using checkpoint data.

        This method should:
        1. Restore previous state if possible
        2. Clean up any partial changes
        3. Release any held resources
        4. Return success status
        """

    @abstractmethod
    async def verify_state(self, doc_id: str) -> dict[str, Any]:
        """
        Verify current state of a document.

        Returns current state information for consistency checking.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if the storage system is healthy and accessible"""


class TransactionCoordinator:
    """
    Coordinates atomic operations across multiple storage systems.

    Implements a two-phase commit protocol:
    1. Prepare Phase: All systems prepare the operation
    2. Commit Phase: If all prepare successfully, commit changes
    3. Rollback: If any failure occurs, rollback all systems
    """

    def __init__(self, systems: list[StorageSystem], timeout: float = 30.0):
        self.systems = systems
        self.timeout = timeout
        self.logger = logging.getLogger(__name__)
        self._transaction_log: list[dict[str, Any]] = []

    async def execute_transaction(
        self, operation: TransactionOperation
    ) -> tuple[bool, list[str], dict[str, Any]]:
        """
        Execute operation atomically across all systems.

        Returns:
            - success: bool
            - errors: List of error messages
            - details: Dict with transaction details
        """
        transaction_id = uuid4()
        checkpoints: list[Checkpoint] = []
        errors: list[str] = []
        state = TransactionState.PREPARING

        start_time = datetime.now()
        transaction_details = {
            "transaction_id": str(transaction_id),
            "operation_type": operation.operation_type.value,
            "doc_id": operation.doc_id,
            "start_time": start_time.isoformat(),
            "systems_involved": [s.name for s in self.systems],
        }

        try:
            # Verify all systems are healthy
            health_checks = await self._check_all_systems_health()
            if not all(health_checks.values()):
                unhealthy = [k for k, v in health_checks.items() if not v]
                errors.append(f"Systems unhealthy: {unhealthy}")
                return False, errors, transaction_details

            # Phase 1: Prepare all systems
            self.logger.info(
                f"Transaction {transaction_id}: Preparing {operation.operation_type.value} for {operation.doc_id}"
            )

            prepare_results = await self._prepare_all_systems(operation, transaction_id)
            checkpoints = prepare_results["checkpoints"]
            errors.extend(prepare_results["errors"])

            if errors:
                state = TransactionState.FAILED
                self.logger.error(f"Transaction {transaction_id}: Prepare phase failed")
                await self._rollback_all(checkpoints)
                return False, errors, transaction_details

            state = TransactionState.PREPARED

            # Phase 2: Commit all systems
            self.logger.info(f"Transaction {transaction_id}: Committing all systems")
            state = TransactionState.COMMITTING

            commit_results = await self._commit_all_systems(checkpoints)
            errors.extend(commit_results["errors"])

            if errors:
                state = TransactionState.FAILED
                self.logger.error(f"Transaction {transaction_id}: Commit phase failed")
                await self._rollback_all(checkpoints)
                return False, errors, transaction_details

            state = TransactionState.COMMITTED
            self.logger.info(f"Transaction {transaction_id}: Successfully committed")

            # Record successful transaction
            transaction_details.update(
                {
                    "end_time": datetime.now().isoformat(),
                    "duration_ms": (datetime.now() - start_time).total_seconds() * 1000,
                    "state": state.value,
                    "checkpoints": [cp.to_dict() for cp in checkpoints],
                }
            )

            self._log_transaction(transaction_details)
            return True, [], transaction_details

        except TimeoutError:
            errors.append(f"Transaction timeout after {self.timeout}s")
            state = TransactionState.FAILED
            await self._rollback_all(checkpoints)
            return False, errors, transaction_details

        except Exception as e:
            errors.append(f"Unexpected error: {e!s}")
            state = TransactionState.FAILED
            self.logger.exception(f"Transaction {transaction_id}: Unexpected error")
            await self._rollback_all(checkpoints)
            return False, errors, transaction_details

        finally:
            if state == TransactionState.FAILED:
                transaction_details.update(
                    {
                        "end_time": datetime.now().isoformat(),
                        "duration_ms": (datetime.now() - start_time).total_seconds() * 1000,
                        "state": state.value,
                        "errors": errors,
                    }
                )
                self._log_transaction(transaction_details)

    async def _check_all_systems_health(self) -> dict[str, bool]:
        """Check health of all systems"""
        tasks = {system.name: system.health_check() for system in self.systems}

        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await asyncio.wait_for(task, timeout=5.0)
            except Exception as e:
                self.logger.exception(f"Health check failed for {name}: {e}")
                results[name] = False

        return results

    async def _prepare_all_systems(
        self, operation: TransactionOperation, transaction_id: UUID
    ) -> dict[str, Any]:
        """Prepare operation on all systems"""
        checkpoints = []
        errors = []

        # Create tasks for parallel preparation
        prepare_tasks = []
        for system in self.systems:
            task = self._prepare_system(system, operation, transaction_id)
            prepare_tasks.append((system.name, task))

        # Execute with timeout
        for system_name, task in prepare_tasks:
            try:
                checkpoint = await asyncio.wait_for(task, timeout=self.timeout / 2)
                checkpoints.append(checkpoint)
                self.logger.debug(f"System {system_name} prepared successfully")
            except TimeoutError:
                errors.append(f"{system_name}: Prepare timeout")
            except Exception as e:
                errors.append(f"{system_name}: {e!s}")
                self.logger.exception(f"Prepare failed for {system_name}: {e}")

        return {"checkpoints": checkpoints, "errors": errors}

    async def _prepare_system(
        self, system: StorageSystem, operation: TransactionOperation, transaction_id: UUID
    ) -> Checkpoint:
        """Prepare a single system"""
        return await system.prepare(operation, transaction_id)

    async def _commit_all_systems(self, checkpoints: list[Checkpoint]) -> dict[str, Any]:
        """Commit all prepared systems"""
        errors = []
        successful_commits = []

        for checkpoint in checkpoints:
            try:
                system = self._get_system_by_name(checkpoint.system_name)
                success = await asyncio.wait_for(
                    system.commit(checkpoint), timeout=self.timeout / 2
                )

                if success:
                    successful_commits.append(checkpoint.system_name)
                    checkpoint.success = True
                else:
                    errors.append(f"{checkpoint.system_name}: Commit returned false")

            except TimeoutError:
                errors.append(f"{checkpoint.system_name}: Commit timeout")
            except Exception as e:
                errors.append(f"{checkpoint.system_name}: {e!s}")
                self.logger.exception(f"Commit failed for {checkpoint.system_name}: {e}")

        return {"successful": successful_commits, "errors": errors}

    async def _rollback_all(self, checkpoints: list[Checkpoint]) -> None:
        """Rollback all checkpoints in reverse order"""
        self.logger.info(f"Rolling back {len(checkpoints)} checkpoints")

        # Rollback in reverse order
        for checkpoint in reversed(checkpoints):
            try:
                system = self._get_system_by_name(checkpoint.system_name)
                success = await asyncio.wait_for(
                    system.rollback(checkpoint),
                    timeout=10.0,  # Shorter timeout for rollback
                )

                if success:
                    self.logger.info(f"Successfully rolled back {checkpoint.system_name}")
                else:
                    self.logger.error(f"Rollback returned false for {checkpoint.system_name}")

            except Exception as e:
                # Log but continue rolling back other systems
                self.logger.exception(f"Rollback failed for {checkpoint.system_name}: {e}")

    def _get_system_by_name(self, name: str) -> StorageSystem:
        """Get storage system by name"""
        for system in self.systems:
            if system.name == name:
                return system
        raise ValueError(f"Unknown storage system: {name}")

    def _log_transaction(self, details: dict[str, Any]) -> None:
        """Log transaction details for auditing"""
        self._transaction_log.append(details)
        # In production, this would write to persistent storage
        self.logger.info(f"Transaction logged: {details['transaction_id']}")

    def get_transaction_log(self) -> list[dict[str, Any]]:
        """Get transaction log for monitoring/debugging"""
        return self._transaction_log.copy()


class TransactionError(Exception):
    """Exception raised when a transaction fails"""

    def __init__(self, message: str, errors: list[str], transaction_id: UUID):
        super().__init__(message)
        self.errors = errors
        self.transaction_id = transaction_id
