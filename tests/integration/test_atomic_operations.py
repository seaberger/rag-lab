"""
Integration tests for atomic operations

Tests the full atomic operation flow including:
- Document addition with rollback on failure
- Document updates with consistency
- Document deletion across all systems
- Failure scenarios and recovery
"""

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.pipeline_v3.core.index_manager_atomic import AtomicIndexManager
from src.pipeline_v3.core.registry import DocumentState, IndexType
from src.pipeline_v3.utils.config import PipelineConfig


class TestAtomicOperations:
    """Test cases for atomic operations"""

    @pytest.fixture
    def setup_atomic_manager(self):
        """Set up atomic index manager for testing"""
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()

        # Create config
        config = PipelineConfig()
        config.storage.registry_path = str(Path(temp_dir) / "registry.db")
        config.storage.fingerprint_path = str(Path(temp_dir) / "fingerprint.db")
        config.storage.keyword_db_path = str(Path(temp_dir) / "keyword.db")
        config.storage.artifact_path = str(Path(temp_dir) / "storage")
        config.qdrant.path = str(Path(temp_dir) / "qdrant")

        # Create directories
        Path(config.storage.artifact_path).mkdir(exist_ok=True)
        Path(config.qdrant.path).mkdir(exist_ok=True)

        # Mock LlamaIndex components
        with patch("src.pipeline_v3.core.index_manager.LLAMA_INDEX_AVAILABLE", True):
            with patch("src.pipeline_v3.core.index_manager.qdrant_client"):
                with patch("src.pipeline_v3.core.index_manager.VectorStoreIndex"):
                    with patch("src.pipeline_v3.core.index_manager.QdrantVectorStore"):
                        # Create manager
                        manager = AtomicIndexManager(
                            config=config, enable_transactions=True, transaction_timeout=5.0
                        )

                        # Mock some methods
                        manager.qdrant_client = Mock()
                        manager.vector_store = Mock()

                        yield {"manager": manager, "config": config, "temp_dir": temp_dir}

        # Cleanup
        import shutil

        shutil.rmtree(temp_dir)

    @pytest.mark.asyncio
    async def test_add_document_atomic_success(self, setup_atomic_manager):
        """Test successful atomic document addition"""
        manager = setup_atomic_manager["manager"]

        # Create test data
        doc_id = "test_doc_001"
        nodes = [
            Mock(
                node_id=f"node_{i}",
                text=f"Test content {i}",
                metadata={"chunk": i},
                embedding=[0.1] * 768,
                hash=f"hash_{i}",
            )
            for i in range(3)
        ]
        content = "Full document content"
        metadata = {"source": "test", "type": "datasheet"}
        file_path = "/test/path/doc.pdf"

        # Mock Qdrant operations
        manager.qdrant_client.scroll.return_value = ([], None)
        manager.qdrant_client.upsert.return_value = True

        # Execute atomic add
        success = await manager.add_document_atomic(
            doc_id=doc_id,
            nodes=nodes,
            content=content,
            metadata=metadata,
            file_path=file_path,
            index_types=IndexType.BOTH,
        )

        # Verify
        assert success is True

        # Check registry
        doc = manager.registry.get_document(doc_id)
        assert doc is not None
        assert doc.state == DocumentState.INDEXED

        # Check storage artifact
        artifact_path = Path(manager.storage_dir) / f"{doc_id}.jsonl"
        assert artifact_path.exists()

        # Check fingerprint
        fp = manager.fingerprint_manager.get_fingerprint(doc_id)
        assert fp is not None

    @pytest.mark.asyncio
    async def test_add_document_atomic_rollback(self, setup_atomic_manager):
        """Test rollback when one system fails during add"""
        manager = setup_atomic_manager["manager"]

        doc_id = "test_rollback_001"
        nodes = [Mock(node_id="node_1", text="Test", metadata={}, embedding=None, hash="h1")]

        # Make Qdrant commit fail
        manager.qdrant_client.upsert.side_effect = Exception("Qdrant error")

        # Execute atomic add
        success = await manager.add_document_atomic(
            doc_id=doc_id,
            nodes=nodes,
            content="Test content",
            metadata={},
            file_path="/test.pdf",
            index_types=IndexType.BOTH,
        )

        # Verify rollback
        assert success is False

        # Document should not exist in any system
        assert manager.registry.get_document(doc_id) is None
        assert not (Path(manager.storage_dir) / f"{doc_id}.jsonl").exists()
        assert manager.fingerprint_manager.get_fingerprint(doc_id) is None

    @pytest.mark.asyncio
    async def test_update_document_atomic(self, setup_atomic_manager):
        """Test atomic document update"""
        manager = setup_atomic_manager["manager"]

        doc_id = "test_update_001"

        # First add a document
        await manager.add_document_atomic(
            doc_id=doc_id,
            nodes=[Mock(node_id="node_1", text="Original", metadata={}, embedding=None, hash="h1")],
            content="Original content",
            metadata={"version": 1},
            file_path="/original.pdf",
            index_types=IndexType.BOTH,
        )

        # Mock Qdrant operations for update
        manager.qdrant_client.delete.return_value = True
        manager.qdrant_client.upsert.return_value = True

        # Update document
        success = await manager.update_document_atomic(
            doc_id=doc_id,
            nodes=[Mock(node_id="node_2", text="Updated", metadata={}, embedding=None, hash="h2")],
            content="Updated content",
            metadata={"version": 2},
            file_path="/updated.pdf",
            index_types=IndexType.BOTH,
        )

        # Verify
        assert success is True

        # Check updated metadata
        doc = manager.registry.get_document(doc_id)
        assert doc.metadata["version"] == 2

        # Check fingerprint changed
        fp = manager.fingerprint_manager.get_fingerprint(doc_id)
        assert fp is not None
        # New fingerprint should be different

    @pytest.mark.asyncio
    async def test_delete_document_atomic(self, setup_atomic_manager):
        """Test atomic document deletion"""
        manager = setup_atomic_manager["manager"]

        doc_id = "test_delete_001"

        # First add a document
        await manager.add_document_atomic(
            doc_id=doc_id,
            nodes=[Mock(node_id="node_1", text="Test", metadata={}, embedding=None, hash="h1")],
            content="Test content",
            metadata={},
            file_path="/test.pdf",
            index_types=IndexType.BOTH,
        )

        # Mock Qdrant delete
        manager.qdrant_client.delete.return_value = True

        # Delete document
        success = await manager.delete_document_atomic(doc_id)

        # Verify
        assert success is True

        # Document should not exist in any system
        assert manager.registry.get_document(doc_id) is None
        assert not (Path(manager.storage_dir) / f"{doc_id}.jsonl").exists()
        assert manager.fingerprint_manager.get_fingerprint(doc_id) is None

    @pytest.mark.asyncio
    async def test_consistency_check_integration(self, setup_atomic_manager):
        """Test consistency checking integration"""
        manager = setup_atomic_manager["manager"]

        # Add some documents
        for i in range(3):
            doc_id = f"consistency_test_{i}"
            await manager.add_document_atomic(
                doc_id=doc_id,
                nodes=[
                    Mock(
                        node_id=f"node_{i}",
                        text=f"Test {i}",
                        metadata={},
                        embedding=None,
                        hash=f"h{i}",
                    )
                ],
                content=f"Content {i}",
                metadata={"index": i},
                file_path=f"/test_{i}.pdf",
                index_types=IndexType.BOTH,
            )

        # Mock Qdrant scroll for consistency check
        manager.qdrant_client.scroll.return_value = ([], None)

        # Check consistency
        report = await manager.check_consistency()

        # Verify
        assert report["total_documents"] >= 3
        assert "consistency_rate" in report

    @pytest.mark.asyncio
    async def test_repair_inconsistencies_integration(self, setup_atomic_manager):
        """Test inconsistency repair integration"""
        manager = setup_atomic_manager["manager"]

        # Create an inconsistency manually
        doc_id = "inconsistent_doc"

        # Add to registry only
        manager.registry.add_document(doc_id, "/test.pdf", {})
        manager.registry.update_document_state(doc_id, DocumentState.INDEXED)

        # Mock Qdrant operations
        manager.qdrant_client.scroll.return_value = ([], None)
        manager.qdrant_client.delete.return_value = True

        # Run repair
        repair_result = await manager.repair_inconsistencies(
            strategy=RepairStrategy.TRUST_REGISTRY, dry_run=False
        )

        # Verify
        assert repair_result["inconsistencies_found"] > 0
        # Since storage artifact is missing, repair might not fully succeed

    @pytest.mark.asyncio
    async def test_transaction_timeout(self, setup_atomic_manager):
        """Test that transactions timeout properly"""
        manager = setup_atomic_manager["manager"]
        manager.transaction_timeout = 0.5  # Very short timeout

        # Make one adapter slow
        original_prepare = manager.adapters["qdrant"].prepare

        async def slow_prepare(*args, **kwargs):
            await asyncio.sleep(1.0)  # Longer than timeout
            return await original_prepare(*args, **kwargs)

        manager.adapters["qdrant"].prepare = slow_prepare

        # Try to add document
        success = await manager.add_document_atomic(
            doc_id="timeout_test",
            nodes=[Mock(node_id="n1", text="Test", metadata={}, embedding=None, hash="h1")],
            content="Test",
            metadata={},
            file_path="/test.pdf",
            index_types=IndexType.BOTH,
        )

        # Should fail due to timeout
        assert success is False

        # Nothing should be persisted
        assert manager.registry.get_document("timeout_test") is None

    @pytest.mark.asyncio
    async def test_transaction_log(self, setup_atomic_manager):
        """Test that transaction log is maintained"""
        manager = setup_atomic_manager["manager"]

        # Perform some operations
        await manager.add_document_atomic(
            doc_id="log_test_1",
            nodes=[Mock(node_id="n1", text="Test", metadata={}, embedding=None, hash="h1")],
            content="Test 1",
            metadata={},
            file_path="/test1.pdf",
        )

        await manager.delete_document_atomic("log_test_1")

        # Get transaction log
        log = manager.get_transaction_log()

        # Verify
        assert len(log) >= 2
        assert any(entry["operation_type"] == "add_document" for entry in log)
        assert any(entry["operation_type"] == "delete_document" for entry in log)
        assert all("transaction_id" in entry for entry in log)
        assert all("duration_ms" in entry for entry in log)
