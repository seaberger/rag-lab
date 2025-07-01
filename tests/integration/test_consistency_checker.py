"""
Integration tests for ConsistencyChecker

Tests the consistency verification and repair functionality across
multiple storage systems.
"""

import asyncio
import pytest
import tempfile
from pathlib import Path

from src.pipeline_v3.core.consistency_checker import (
    ConsistencyChecker, ConsistencyReport, DocumentInconsistency,
    InconsistencyType, RepairStrategy, RepairResult
)
from src.pipeline_v3.core.registry import DocumentRegistry, DocumentState
from src.pipeline_v3.core.fingerprint import FingerprintManager
from src.pipeline_v3.utils.config import PipelineConfig


class MockIndexManager:
    """Mock IndexManager for testing"""
    
    def __init__(self):
        self.vector_docs = {}
        self.keyword_docs = {}
        
    async def verify_vector_index_state(self, doc_id: str) -> dict:
        """Mock vector index state"""
        return {"exists": doc_id in self.vector_docs}
    
    async def verify_keyword_index_state(self, doc_id: str) -> dict:
        """Mock keyword index state"""
        return {"exists": doc_id in self.keyword_docs}
    
    async def delete_from_vector_index(self, doc_id: str) -> bool:
        """Mock delete from vector index"""
        if doc_id in self.vector_docs:
            del self.vector_docs[doc_id]
        return True
    
    async def delete_from_keyword_index(self, doc_id: str) -> bool:
        """Mock delete from keyword index"""
        if doc_id in self.keyword_docs:
            del self.keyword_docs[doc_id]
        return True
    
    def add_to_vector_index(self, doc_id: str):
        """Add document to vector index for testing"""
        self.vector_docs[doc_id] = True
    
    def add_to_keyword_index(self, doc_id: str):
        """Add document to keyword index for testing"""
        self.keyword_docs[doc_id] = True


class TestConsistencyChecker:
    """Test cases for ConsistencyChecker"""
    
    @pytest.fixture
    def setup_checker(self):
        """Set up test environment"""
        # Create temporary directories
        temp_dir = tempfile.mkdtemp()
        storage_dir = Path(temp_dir) / "storage"
        storage_dir.mkdir()
        
        # Create config
        config = PipelineConfig()
        config.storage.registry_path = str(Path(temp_dir) / "registry.db")
        config.storage.fingerprint_path = str(Path(temp_dir) / "fingerprint.db")
        
        # Create components
        registry = DocumentRegistry(config)
        fingerprint_manager = FingerprintManager(config)
        index_manager = MockIndexManager()
        
        # Create checker
        checker = ConsistencyChecker(
            registry=registry,
            index_manager=index_manager,
            fingerprint_manager=fingerprint_manager,
            storage_dir=str(storage_dir)
        )
        
        yield {
            "checker": checker,
            "registry": registry,
            "fingerprint_manager": fingerprint_manager,
            "index_manager": index_manager,
            "storage_dir": storage_dir,
            "temp_dir": temp_dir
        }
        
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir)
    
    @pytest.mark.asyncio
    async def test_all_consistent(self, setup_checker):
        """Test when all documents are consistent"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        index_manager = setup_checker["index_manager"]
        fingerprint_manager = setup_checker["fingerprint_manager"]
        storage_dir = setup_checker["storage_dir"]
        
        # Add consistent documents
        for i in range(3):
            doc_id = f"doc_{i}"
            
            # Add to registry
            registry.register_document(
                source=f"/path/to/{doc_id}.pdf",
                content_hash=f"hash_{i}",
                size=1000 + i,
                modified_time=1234567890.0,
                doc_id=doc_id,
                metadata={"meta": i}
            )
            registry.update_document_state(doc_id, DocumentState.INDEXED)
            
            # Add to indexes
            index_manager.add_to_vector_index(doc_id)
            index_manager.add_to_keyword_index(doc_id)
            
            # Add storage artifact
            (storage_dir / f"{doc_id}.jsonl").write_text('{"test": true}')
            
            # Add fingerprint
            # Note: FingerprintManager requires actual files, so we skip this in tests
        
        # Check consistency
        report = await checker.check_all_documents()
        
        # Verify
        # We should have at least our 3 test documents
        assert report.total_documents >= 3
        
        # Find our test documents in the report
        test_doc_inconsistencies = [
            inc for inc in report.inconsistencies 
            if inc.doc_id.startswith('doc_')
        ]
        
        # Our 3 test documents should be missing only fingerprints
        assert len(test_doc_inconsistencies) == 3
        for inconsistency in test_doc_inconsistencies:
            assert InconsistencyType.MISSING_FROM_FINGERPRINT in inconsistency.types
            assert len(inconsistency.types) == 1  # Only missing fingerprint
    
    @pytest.mark.asyncio
    async def test_missing_from_indexes(self, setup_checker):
        """Test detection of documents missing from indexes"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        index_manager = setup_checker["index_manager"]
        storage_dir = setup_checker["storage_dir"]
        
        # Add document to registry but not indexes
        doc_id = "missing_from_indexes"
        registry.register_document(
            source="/path/to/doc.pdf",
            content_hash="test_hash",
            size=1000,
            modified_time=1234567890.0,
            doc_id=doc_id,
            metadata={}
        )
        registry.update_document_state(doc_id, DocumentState.INDEXED)
        (storage_dir / f"{doc_id}.jsonl").write_text('{}')
        
        # Check consistency
        report = await checker.check_all_documents()
        
        # Verify
        assert report.inconsistent_documents == 1
        assert len(report.inconsistencies) == 1
        
        inconsistency = report.inconsistencies[0]
        assert inconsistency.doc_id == doc_id
        assert InconsistencyType.MISSING_FROM_VECTOR_INDEX in inconsistency.types
        assert InconsistencyType.MISSING_FROM_KEYWORD_INDEX in inconsistency.types
        assert "vector_index" in inconsistency.missing_from
        assert "keyword_index" in inconsistency.missing_from
    
    @pytest.mark.asyncio
    async def test_orphaned_data(self, setup_checker):
        """Test detection of orphaned data (not in registry)"""
        checker = setup_checker["checker"]
        index_manager = setup_checker["index_manager"]
        storage_dir = setup_checker["storage_dir"]
        
        # Add orphaned data
        doc_id = "orphaned_doc"
        index_manager.add_to_vector_index(doc_id)
        index_manager.add_to_keyword_index(doc_id)
        (storage_dir / f"{doc_id}.jsonl").write_text('{}')
        
        # Check consistency with orphan detection
        report = await checker.check_all_documents(include_orphans=True)
        
        # Verify
        assert report.inconsistent_documents == 1
        
        inconsistency = report.inconsistencies[0]
        assert inconsistency.doc_id == doc_id
        assert InconsistencyType.MISSING_FROM_REGISTRY in inconsistency.types
        assert InconsistencyType.ORPHANED_DATA in inconsistency.types
        assert inconsistency.severity == "high"
    
    @pytest.mark.asyncio
    async def test_repair_trust_registry(self, setup_checker):
        """Test repair using TRUST_REGISTRY strategy"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        index_manager = setup_checker["index_manager"]
        storage_dir = setup_checker["storage_dir"]
        
        # Create inconsistency: orphaned data
        orphan_id = "orphan_to_remove"
        index_manager.add_to_vector_index(orphan_id)
        index_manager.add_to_keyword_index(orphan_id)
        (storage_dir / f"{orphan_id}.jsonl").write_text('{}')
        
        # Check and repair
        report = await checker.check_all_documents(include_orphans=True)
        repair_results = await checker.repair_inconsistencies(
            report, 
            RepairStrategy.TRUST_REGISTRY,
            dry_run=False
        )
        
        # Verify
        assert len(repair_results) == 1
        result = repair_results[0]
        assert result.doc_id == orphan_id
        assert result.success
        assert "Remove from vector index" in result.actions_taken
        assert "Remove from keyword index" in result.actions_taken
        
        # Verify data was actually removed
        assert orphan_id not in index_manager.vector_docs
        assert orphan_id not in index_manager.keyword_docs
        assert not (storage_dir / f"{orphan_id}.jsonl").exists()
    
    @pytest.mark.asyncio
    async def test_repair_dry_run(self, setup_checker):
        """Test that dry run doesn't actually modify data"""
        checker = setup_checker["checker"]
        index_manager = setup_checker["index_manager"]
        storage_dir = setup_checker["storage_dir"]
        
        # Create orphaned data
        orphan_id = "dry_run_test"
        index_manager.add_to_vector_index(orphan_id)
        (storage_dir / f"{orphan_id}.jsonl").write_text('{}')
        
        # Check and repair with dry_run=True
        report = await checker.check_all_documents(include_orphans=True)
        repair_results = await checker.repair_inconsistencies(
            report,
            RepairStrategy.TRUST_REGISTRY,
            dry_run=True
        )
        
        # Verify
        assert len(repair_results) == 1
        result = repair_results[0]
        assert result.success
        assert len(result.actions_taken) > 0
        
        # Verify data was NOT removed (dry run)
        assert orphan_id in index_manager.vector_docs
        assert (storage_dir / f"{orphan_id}.jsonl").exists()
    
    @pytest.mark.asyncio
    async def test_repair_remove_all(self, setup_checker):
        """Test REMOVE_ALL repair strategy"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        index_manager = setup_checker["index_manager"]
        fingerprint_manager = setup_checker["fingerprint_manager"]
        
        # Create partially inconsistent document
        doc_id = "partial_doc"
        registry.register_document(
            source="/path/to/doc.pdf",
            content_hash="test_hash",
            size=1000,
            modified_time=1234567890.0,
            doc_id=doc_id,
            metadata={}
        )
        index_manager.add_to_vector_index(doc_id)
        # Missing from keyword index and storage
        
        # Check and repair
        report = await checker.check_all_documents()
        repair_results = await checker.repair_inconsistencies(
            report,
            RepairStrategy.REMOVE_ALL,
            dry_run=False
        )
        
        # Verify
        assert len(repair_results) == 1
        result = repair_results[0]
        assert result.success
        assert "Remove from registry" in result.actions_taken
        assert "Remove from vector_index" in result.actions_taken
        
        # Verify complete removal
        assert registry.get_document(doc_id) is None
        assert doc_id not in index_manager.vector_docs
    
    @pytest.mark.asyncio
    async def test_consistency_report_serialization(self, setup_checker):
        """Test that ConsistencyReport can be serialized"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        
        # Add some test data
        registry.register_document(
            source="/path/1",
            content_hash="hash1",
            size=1000,
            modified_time=1234567890.0,
            doc_id="doc1",
            metadata={}
        )
        
        # Check consistency
        report = await checker.check_all_documents()
        
        # Serialize
        report_dict = report.to_dict()
        
        # Verify structure
        assert "timestamp" in report_dict
        assert "total_documents" in report_dict
        assert "consistent_documents" in report_dict
        assert "inconsistent_documents" in report_dict
        assert "consistency_rate" in report_dict
        assert "inconsistencies" in report_dict
        assert "duration_ms" in report_dict
    
    @pytest.mark.asyncio
    async def test_batch_processing(self, setup_checker):
        """Test that large numbers of documents are processed in batches"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        
        # Add many documents
        num_docs = 250
        for i in range(num_docs):
            doc_id = f"batch_doc_{i}"
            registry.register_document(
                source=f"/path/{i}",
                content_hash=f"hash_{i}",
                size=1000,
                modified_time=1234567890.0,
                doc_id=doc_id,
                metadata={}
            )
        
        # Check with small batch size
        report = await checker.check_all_documents(batch_size=50)
        
        # Verify
        assert report.total_documents == num_docs
        # Should process without issues despite small batch size
    
    @pytest.mark.asyncio
    async def test_error_handling(self, setup_checker):
        """Test that errors during checking are handled gracefully"""
        checker = setup_checker["checker"]
        registry = setup_checker["registry"]
        
        # Add document
        doc_id = "error_test"
        registry.register_document(
            source="/path",
            content_hash="test_hash",
            size=1000,
            modified_time=1234567890.0,
            doc_id=doc_id,
            metadata={}
        )
        
        # Mock an error in index manager
        original_verify = checker.index_manager.verify_vector_index_state
        
        async def failing_verify(doc_id):
            raise Exception("Simulated error")
        
        checker.index_manager.verify_vector_index_state = failing_verify
        
        # Check consistency
        report = await checker.check_all_documents()
        
        # Verify error was captured
        assert len(report.errors) > 0
        assert "error_test" in report.errors[0]
        
        # Restore original
        checker.index_manager.verify_vector_index_state = original_verify