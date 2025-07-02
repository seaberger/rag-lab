#!/usr/bin/env python3
"""
Test script for Issue #27 implementation
"""
import asyncio
import tempfile
from pathlib import Path

from src.pipeline_v3.core.transaction_coordinator import (
    TransactionCoordinator, TransactionOperation, OperationType
)
from src.pipeline_v3.core.storage_adapters import (
    RegistryAdapter, KeywordIndexAdapter, StorageArtifactsAdapter
)
from src.pipeline_v3.core.consistency_checker import ConsistencyChecker
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.core.fingerprint import FingerprintManager
from src.pipeline_v3.storage.keyword_index import BM25Index
from src.pipeline_v3.utils.config import PipelineConfig

# Mock IndexManager for testing
class MockIndexManager:
    def __init__(self):
        self.vector_docs = {}
        self.keyword_docs = {}
        
    async def verify_vector_index_state(self, doc_id: str) -> dict:
        return {"exists": doc_id in self.vector_docs}
    
    async def verify_keyword_index_state(self, doc_id: str) -> dict:
        return {"exists": doc_id in self.keyword_docs}

def test_imports():
    """Test that all imports work"""
    print("✅ All imports successful")

async def test_transaction_basic():
    """Test basic transaction functionality"""
    print("\n🔧 Testing TransactionCoordinator...")
    
    # Create test config
    config = PipelineConfig()
    
    # Create temporary storage
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up storage systems
        config.storage.registry_path = str(Path(temp_dir) / "registry.db")
        registry = DocumentRegistry(config)
        registry_adapter = RegistryAdapter(registry)
        
        keyword_db_path = str(Path(temp_dir) / "keyword.db")
        keyword_index = BM25Index(keyword_db_path)
        keyword_adapter = KeywordIndexAdapter(keyword_index)
        
        storage_dir = Path(temp_dir) / "storage"
        storage_dir.mkdir()
        storage_adapter = StorageArtifactsAdapter(storage_dir)
        
        # Create coordinator
        systems = [registry_adapter, keyword_adapter, storage_adapter]
        coordinator = TransactionCoordinator(systems)
        
        # Test operation
        operation = TransactionOperation(
            operation_type=OperationType.ADD_DOCUMENT,
            doc_id="test_doc_001",
            data={
                "file_path": "/test/doc.pdf",
                "content": "Test content",
                "fingerprint": "test_hash",
                "artifact_data": {"text": "Test document content"},
                "nodes": []  # Empty nodes for test
            },
            metadata={"title": "Test Document"}
        )
        
        # Execute transaction
        success, errors, details = await coordinator.execute_transaction(operation)
        
        if success:
            print(f"✅ Transaction successful!")
            print(f"   - Document ID: {details['doc_id']}")
            print(f"   - State: {details['state']}")
            print(f"   - Systems prepared: {details['systems_prepared']}")
        else:
            print(f"❌ Transaction failed: {errors}")

async def test_consistency_checker():
    """Test consistency checker functionality"""
    print("\n🔍 Testing ConsistencyChecker...")
    
    config = PipelineConfig()
    
    with tempfile.TemporaryDirectory() as temp_dir:
        # Set up components
        config.storage.registry_path = str(Path(temp_dir) / "registry.db")
        config.storage.fingerprint_path = str(Path(temp_dir) / "fingerprint.db")
        
        registry = DocumentRegistry(config)
        fingerprint_manager = FingerprintManager(config)
        index_manager = MockIndexManager()
        storage_dir = Path(temp_dir) / "storage"
        storage_dir.mkdir()
        
        # Create checker
        checker = ConsistencyChecker(
            registry=registry,
            index_manager=index_manager,
            fingerprint_manager=fingerprint_manager,
            storage_dir=str(storage_dir)
        )
        
        # Add a consistent document
        doc_id = "consistent_doc"
        registry.register_document(
            source="/test/doc.pdf",
            content_hash="test_hash",
            size=1000,
            modified_time=1234567890.0,
            doc_id=doc_id,
            metadata={}
        )
        index_manager.vector_docs[doc_id] = True
        index_manager.keyword_docs[doc_id] = True
        (storage_dir / f"{doc_id}.jsonl").write_text("{}")
        
        # Check consistency
        report = await checker.check_all_documents()
        
        print(f"✅ Consistency check complete:")
        print(f"   - Total documents: {report.total_documents}")
        print(f"   - Consistent: {report.consistent_documents}")
        print(f"   - Consistency rate: {report.consistency_rate:.1f}%")

async def main():
    """Run all tests"""
    print("🚀 Testing Issue #27 Implementation: Cross-System Consistency\n")
    
    test_imports()
    await test_transaction_basic()
    await test_consistency_checker()
    
    print("\n✨ All tests complete!")

if __name__ == "__main__":
    asyncio.run(main())