#!/usr/bin/env python3
"""
Demo script for Issue #27: Cross-System Consistency
Shows transaction coordinator preventing partial updates
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline_v3.core.fingerprint import FingerprintManager
from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.core.storage_adapters import (
    FingerprintAdapter,
    KeywordIndexAdapter,
    QdrantAdapter,
    RegistryAdapter,
    StorageArtifactsAdapter,
)
from src.pipeline_v3.core.transaction_coordinator import (
    OperationType,
    TransactionCoordinator,
    TransactionOperation,
)
from src.pipeline_v3.utils.config import PipelineConfig


async def simulate_failure_scenario():
    """Simulate a failure during multi-system update"""
    print("=== Issue #27: Transaction Coordinator Demo ===\n")

    # Initialize components
    config = PipelineConfig()
    registry = DocumentRegistry(config)
    index_manager = IndexManager(config, registry=registry)
    fingerprint_manager = FingerprintManager(config)

    # Create storage adapters
    registry_adapter = RegistryAdapter(registry)
    QdrantAdapter(config)
    keyword_adapter = KeywordIndexAdapter(Path("keyword_index_v3.db"))
    storage_adapter = StorageArtifactsAdapter(Path("storage_data_v3"))
    fingerprint_adapter = FingerprintAdapter(fingerprint_manager)

    # Create a failing adapter to simulate failure
    class FailingVectorAdapter(QdrantAdapter):
        """Adapter that fails during commit"""

        async def commit(self, checkpoint):
            raise Exception("Simulated vector index failure!")

    # Replace vector adapter with failing one
    failing_vector = FailingVectorAdapter(config)

    # Create transaction coordinator
    systems = [
        registry_adapter,
        failing_vector,  # This will fail
        keyword_adapter,
        storage_adapter,
        fingerprint_adapter,
    ]

    coordinator = TransactionCoordinator(systems, timeout=30.0)

    # Create test operation
    test_doc_id = "test-doc-failure-scenario"
    operation = TransactionOperation(
        operation_type=OperationType.ADD_DOCUMENT,
        doc_id=test_doc_id,
        data={
            "nodes": ["test node 1", "test node 2"],
            "content": "Test document content for failure scenario",
            "file_path": "/test/failure/doc.pdf",
            "metadata": {"test": True},
        },
    )

    print("1. Attempting to add document across all systems...")
    print("   (Vector index will fail during commit phase)")

    # Execute transaction - should fail and rollback
    success, errors, details = await coordinator.execute_transaction(operation)

    print("\n2. Transaction result:")
    print(f"   Success: {success}")
    print(f"   Errors: {errors}")
    print(f"   State: {details.get('state', 'unknown')}")

    # Verify rollback worked - document should not exist in any system
    print(f"\n3. Verifying rollback - checking all systems for doc_id: {test_doc_id}")

    # Check registry
    reg_doc = registry.get_document(test_doc_id)
    print(
        f"   Registry: {'❌ Document found (rollback failed!)' if reg_doc else '✅ Document not found (rollback success)'}"
    )

    # Check vector index
    vector_state = await index_manager.verify_vector_index_state(test_doc_id)
    print(
        f"   Vector index: {'❌ Document found' if vector_state.get('exists') else '✅ Document not found'}"
    )

    # Check keyword index
    keyword_state = await index_manager.verify_keyword_index_state(test_doc_id)
    print(
        f"   Keyword index: {'❌ Document found' if keyword_state.get('exists') else '✅ Document not found'}"
    )

    # Check storage
    storage_path = Path("storage_data_v3") / f"{test_doc_id}.jsonl"
    print(
        f"   Storage artifact: {'❌ File exists' if storage_path.exists() else '✅ File not found'}"
    )

    # Check transaction log
    print("\n4. Transaction log:")
    log = coordinator.get_transaction_log()
    if log:
        latest = log[-1]
        print(f"   Transaction ID: {latest['transaction_id']}")
        print(f"   State: {latest['state']}")
        print(f"   Duration: {latest['duration_ms']:.1f}ms")
        print(f"   Errors: {latest.get('errors', [])}")


async def demonstrate_successful_transaction():
    """Show a successful multi-system update"""
    print("\n\n=== Successful Transaction Demo ===\n")

    # Initialize components
    config = PipelineConfig()
    registry = DocumentRegistry(config)
    IndexManager(config, registry=registry)
    fingerprint_manager = FingerprintManager(config)

    # Create storage adapters (all working properly)
    systems = [
        RegistryAdapter(registry),
        QdrantAdapter(config),
        KeywordIndexAdapter(Path("keyword_index_v3.db")),
        StorageArtifactsAdapter(Path("storage_data_v3")),
        FingerprintAdapter(fingerprint_manager),
    ]

    coordinator = TransactionCoordinator(systems, timeout=30.0)

    # Create test operation
    test_doc_id = "test-doc-success-scenario"
    operation = TransactionOperation(
        operation_type=OperationType.ADD_DOCUMENT,
        doc_id=test_doc_id,
        data={
            "nodes": ["success node 1", "success node 2"],
            "content": "Test document content for success scenario",
            "file_path": "/test/success/doc.pdf",
            "metadata": {"success": True},
            "registry_data": {
                "source": "/test/success/doc.pdf",
                "content_hash": "test-hash-123",
                "size": 1024,
                "modified_time": 1234567890.0,
            },
        },
    )

    print("1. Adding document across all systems (should succeed)...")

    # Execute transaction
    success, errors, details = await coordinator.execute_transaction(operation)

    print("\n2. Transaction result:")
    print(f"   Success: {success}")
    print(f"   State: {details.get('state', 'unknown')}")
    print(f"   Systems prepared: {len(details.get('checkpoints', []))}")

    if success:
        print("\n3. Verifying document exists in all systems:")

        # Check registry
        reg_doc = registry.get_document(test_doc_id)
        print(f"   Registry: {'✅ Document found' if reg_doc else '❌ Document not found'}")

        # Check indexes (Note: actual indexing would require real nodes/embeddings)
        print("   Vector index: ⚠️  (Would be indexed with real embeddings)")
        print("   Keyword index: ⚠️  (Would be indexed with real content)")

        # Check storage
        storage_path = Path("storage_data_v3") / f"{test_doc_id}.jsonl"
        print(
            f"   Storage artifact: {'✅ File created' if storage_path.exists() else '❌ File not found'}"
        )

        # Cleanup test file
        if storage_path.exists():
            storage_path.unlink()
            print("\n   (Cleaned up test storage file)")


async def main():
    """Run all demos"""
    # Demo 1: Failure scenario with rollback
    await simulate_failure_scenario()

    # Demo 2: Successful transaction
    await demonstrate_successful_transaction()

    print("\n✨ Issue #27 demo complete!")
    print("\nKey takeaways:")
    print("- Transaction coordinator ensures atomic updates across all systems")
    print("- Failures trigger automatic rollback to prevent inconsistencies")
    print("- All systems must succeed or none are updated")
    print("- This prevents the partial update issues that can corrupt data")


if __name__ == "__main__":
    asyncio.run(main())
