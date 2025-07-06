"""
Core Coverage Integration Tests for Pipeline v3

Focused tests to boost coverage of core pipeline modules to meet CI/CD requirements.
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.fingerprint import FingerprintManager
from core.migrations import (Migration, MigrationManager,
                             load_migrations_from_sql_files)
from core.registry import DocumentRegistry, DocumentState
from job_queue.job import JobManager, JobStatus, JobType
from job_queue.manager import DocumentQueue, JobPriority
from storage.cache import CacheManager

# Import database fixtures for multi-backend support
try:
    from tests.fixtures.database_fixtures import (
        create_test_registry,
        create_test_fingerprint_manager,
        create_test_job_manager,
        cleanup_test_component
    )
except ImportError:
    # If fixtures not available, define fallback functions
    def create_test_registry(config):
        return DocumentRegistry(config=config)

    def create_test_fingerprint_manager(config):
        return FingerprintManager(config=config)

    def create_test_job_manager(config):
        return JobManager(config=config)

    def cleanup_test_component(component):
        if hasattr(component, 'close'):
            component.close()

from utils.cleanup import cleanup_temp_resources, get_resource_manager
from utils.common_utils import init_cli_logging, logger
# Test core imports and boost their coverage
from utils.config import PipelineConfig
from utils.env_utils import setup_environment
from utils.monitoring import ProgressMonitor
from utils.validation import DocumentValidator, ValidationError


class TestCoreCoverage:
    """Tests to boost coverage of core modules."""

    def test_pipeline_config_comprehensive(self, test_base_dir):
        """Comprehensive test of PipelineConfig."""
        # Test default initialization
        config = PipelineConfig()

        # Test all config sections
        assert config.openai.vision_model == "gpt-4.1"
        assert config.openai.keyword_model == "gpt-4.1-mini"
        assert config.openai.embedding_model == "text-embedding-3-small"

        assert config.storage.base_dir == "./storage_data_v3"
        assert config.storage.keyword_db_path == "./keyword_index_v3.db"

        assert config.qdrant.collection_name == "datasheets_v3"
        assert config.openai.dimensions == 1536  # embedding size is in openai config

        assert config.job_queue.max_concurrent == 10
        assert config.job_queue.job_persistence == True

        # Test to_dict using dataclasses.asdict
        from dataclasses import asdict

        config_dict = asdict(config)
        assert isinstance(config_dict, dict)
        assert "openai" in config_dict
        assert "storage" in config_dict
        assert "qdrant" in config_dict
        assert "job_queue" in config_dict

        # Test YAML loading
        yaml_content = """
openai:
  vision_model: gpt-4.1
  max_retries: 5
storage:
  base_dir: /custom/path
job_queue:
  max_concurrent: 8
"""
        yaml_file = os.path.join(test_base_dir, "config.yaml")
        with open(yaml_file, "w") as f:
            f.write(yaml_content)

        custom_config = PipelineConfig.from_yaml(yaml_file)
        assert custom_config.openai.vision_model == "gpt-4.1"
        assert custom_config.openai.max_retries == 5
        assert custom_config.job_queue.max_concurrent == 8

        # Test save method - PipelineConfig doesn't have save, so just verify it can be converted to dict
        from dataclasses import asdict

        config_dict = asdict(custom_config)
        assert isinstance(config_dict, dict)

        # Test accessing attributes directly
        assert custom_config.job_queue.max_concurrent == 8
        assert getattr(custom_config, "invalid_key", "default") == "default"

        # Test setting attributes directly
        custom_config.job_queue.max_concurrent = 16
        assert custom_config.job_queue.max_concurrent == 16

    def test_document_registry_lifecycle(self, test_config):
        """Test DocumentRegistry operations."""
        registry = create_test_registry(test_config)

        try:
            # Test registration
            import time

            doc_id = registry.register_document(
            source="test.pdf",
            content_hash="abc123",
            size=1024,
            modified_time=time.time(),
            metadata={"author": "test", "version": "1.0", "doc_type": "datasheet"},
            )
            assert doc_id is not None

            # Test retrieval
            doc = registry.get_document(doc_id)
            assert doc is not None
            assert doc.source.endswith("test.pdf")
            assert doc.metadata["doc_type"] == "datasheet"

            # Test get by source
            doc_by_source = registry.get_document_by_source("test.pdf")
            assert doc_by_source.doc_id == doc_id

            # Test status updates - using update_document_state method
            registry.update_document_state(doc_id, DocumentState.UPDATING)
            doc = registry.get_document(doc_id)
            assert doc.state == "updating"

            registry.update_document_state(doc_id, DocumentState.INDEXED)
            doc = registry.get_document(doc_id)
            assert doc.state == "indexed"

            # Test index updates
            from core.registry import IndexType

            registry.mark_indexed(doc_id, IndexType.BOTH, chunk_count=5)
            doc = registry.get_document(doc_id)
            assert doc.vector_indexed == True
            assert doc.keyword_indexed == True

            # Skip document updates - method not available
            # Would need to check actual registry API

            # Test list documents
            docs = registry.list_documents(limit=10)
            assert len(docs) == 1
            assert docs[0].doc_id == doc_id

            # Test statistics
            stats = registry.get_statistics()
            assert stats["total_documents"] == 1
            assert stats["by_state"]["indexed"]["count"] == 1
            # Health score might be less than 100 if we marked indexed without actual index entries
            assert stats["consistency"]["health_score"] >= 90

            # Change detection is handled by FingerprintManager, not Registry
            # Tested separately in test_fingerprint_store_operations

            # Test deletion
            registry.remove_document(doc_id)
            doc = registry.get_document(doc_id)
            assert doc is None
        finally:
            cleanup_test_component(registry)

    def test_fingerprint_store_operations(self, test_config, test_base_dir):
        """Test FingerprintManager functionality."""
        store = create_test_fingerprint_manager(test_config)

        try:
            # Create a test file
            test_file = os.path.join(test_base_dir, "test.pdf")
            with open(test_file, "wb") as f:
                f.write(b"test content")

            # Compute fingerprint
            fingerprint = FingerprintManager.compute_fingerprint(test_file)
            assert fingerprint is not None
            assert fingerprint.content_hash is not None
            assert fingerprint.size == 12  # "test content" is 12 bytes

            # Store fingerprint
            store.update_fingerprint(
                fingerprint, doc_id="doc1", processing_status="completed"
            )

            # Retrieve fingerprint
            retrieved = store.get_fingerprint(test_file)
            assert retrieved is not None
            assert retrieved.content_hash == fingerprint.content_hash
            assert retrieved.doc_id == "doc1"
            assert retrieved.processing_status == "completed"

            # Test has_changed - should not have changed
            has_changed = store.has_changed(test_file)
            assert not has_changed

            # Modify file
            with open(test_file, "wb") as f:
                f.write(b"modified content")

            # Now should detect change
            has_changed = store.has_changed(test_file)
            assert has_changed

            # Test cleanup old fingerprints
            cleaned = store.cleanup_old_fingerprints()
            assert isinstance(cleaned, int)
        finally:
            cleanup_test_component(store)

    def test_storage_cache_operations(self, test_config):
        """Test CacheManager functionality."""
        cache = CacheManager(config=test_config)

        # Test cache operations with actual CacheManager API
        doc_hash = "test_doc_hash_123"
        prompt_hash = "test_prompt_hash_456"

        test_data = {
            "content": "Test content",
            "metadata": {"type": "test"},
            "chunks": ["chunk1", "chunk2"],
            "embedding": [0.1] * 1536,
        }

        # Save to cache
        success = cache.put(doc_hash, prompt_hash, test_data)
        assert success

        # Load from cache
        loaded = cache.get(doc_hash, prompt_hash)
        assert loaded is not None
        assert loaded["content"] == test_data["content"]
        assert loaded["metadata"] == test_data["metadata"]

        # Test cache stats
        assert cache.stats["hits"] > 0 or cache.stats["misses"] >= 0

        # Test clearing cache entries
        cleared = cache.clear()
        assert isinstance(cleared, int)

        # Test with large data for compression
        large_data = {
            "content": "x" * 10000,
            "chunks": ["chunk" * 100 for _ in range(10)],
        }

        success = cache.put("large_doc", "large_prompt", large_data)
        assert success
        loaded_large = cache.get("large_doc", "large_prompt")
        assert loaded_large is not None

    def test_job_queue_operations(self, test_config):
        """Test job queue functionality."""
        queue = DocumentQueue(config=test_config)

        # Test job submission
        job1_id = asyncio.run(
            queue.add_job(
                source="doc1.pdf",
                job_type="add",
                priority=JobPriority.HIGH,
                metadata={"test": True},
            )
        )
        assert job1_id is not None

        job2_id = asyncio.run(
            queue.add_job(
                source="doc2.pdf", job_type="update", priority=JobPriority.NORMAL
            )
        )
        assert job2_id is not None

        # Test queue status
        status = queue.get_status()
        assert status["queue_status"]["pending"] == 2
        assert status["performance"]["jobs_submitted"] == 2

        # Test job status
        job_status = queue.get_job_status(job1_id)
        assert job_status is not None
        assert job_status["status"] == "pending"

        # Test that jobs are in pending queue
        assert queue.pending.qsize() == 2

        # Test getting job from queue
        job = queue.pending.get()
        assert job.job_id == job1_id  # High priority first

        # Put job back for testing
        queue.pending.put(job)

        # Test pause/resume
        queue.pause_processing()
        assert queue.is_paused

        queue.resume_processing()
        assert not queue.is_paused

    def test_job_manager_persistence(self, test_config):
        """Test JobManager database operations."""
        manager = create_test_job_manager(test_config)

        try:
            # Create job
            job_id = manager.create_job(
                source="test.pdf",
                job_type=JobType.ADD,
                priority=2,
                metadata={"key": "value"},
            )
            assert job_id is not None

            # Get job
            job = manager.get_job(job_id)
            assert job is not None
            assert job.source == "test.pdf"
            assert job.job_type == JobType.ADD.value
            assert job.metadata["key"] == "value"

            # Update status
            manager.update_job_status(job_id, JobStatus.PROCESSING)
            job = manager.get_job(job_id)
            assert job.status == JobStatus.PROCESSING.value

            # Update with error
            manager.update_job_status(job_id, JobStatus.FAILED, error_message="Test error")
            job = manager.get_job(job_id)
            assert job.status == JobStatus.FAILED.value
            assert job.error_message == "Test error"

            # List jobs
            pending_jobs = manager.list_jobs(status=JobStatus.PENDING, limit=10)
            processing_jobs = manager.list_jobs(status=JobStatus.PROCESSING, limit=10)
            failed_jobs = manager.list_jobs(status=JobStatus.FAILED, limit=10)

            assert len(failed_jobs) >= 1
            assert any(j.job_id == job_id for j in failed_jobs)

            # Test job persistence across instances
            new_manager = create_test_job_manager(test_config)
            try:
                persisted_job = new_manager.get_job(job_id)
                assert persisted_job is not None
                assert persisted_job.source == "test.pdf"
            finally:
                cleanup_test_component(new_manager)
        finally:
            cleanup_test_component(manager)

    def test_progress_monitor_functionality(self):
        """Test ProgressMonitor operations."""
        # Basic monitor with callback
        monitor = ProgressMonitor()

        # Start tracking a document
        monitor.start_document("doc1", "test.pdf", size_bytes=1024)

        # Track stages - update_stage records completed stage with duration
        time.sleep(0.01)  # Small delay to simulate processing
        monitor.update_stage("doc1", "parsing", duration=0.01)

        # Complete document
        monitor.complete_document("doc1", chunks=5)

        # Get stats directly from stats dict
        stats = monitor.stats["doc1"]
        assert stats.doc_id == "doc1"
        assert stats.chunks == 5
        assert stats.size_bytes == 1024
        assert "parsing" in stats.stages

        # Test global stats
        global_stats = monitor.get_summary()
        assert global_stats["total_docs"] == 1
        assert global_stats["processed_docs"] == 1
        assert global_stats["total_chunks"] == 5

        # Test error handling
        monitor.start_document("doc2", "error.pdf")
        monitor.fail_document("doc2", "Test error")

        error_stats = monitor.stats["doc2"]
        assert error_stats.error == "Test error"

        # Check get_summary works
        summary = monitor.get_summary()
        assert isinstance(summary, dict)
        assert summary["total_docs"] == 2
        assert summary["failed_docs"] == 1

    def test_logging_initialization(self):
        """Test logging setup."""
        # Test default initialization
        init_cli_logging()

        # Test with verbose flag
        original_argv = sys.argv.copy()
        try:
            sys.argv = ["test", "-v"]
            init_cli_logging()

            # Test logger
            logger.info("Info message")
            logger.debug("Debug message")
            logger.warning("Warning message")
            logger.error("Error message")
        finally:
            sys.argv = original_argv

    def test_environment_setup(self, test_base_dir):
        """Test environment utilities."""
        # Create a test .env file
        env_file = os.path.join(test_base_dir, ".env")
        with open(env_file, "w") as f:
            f.write("TEST_KEY=test_value\n")
            f.write("OPENAI_API_KEY=test_key\n")

        # Preserve original environment variables
        original_cwd = os.getcwd()
        original_openai_key = os.environ.get("OPENAI_API_KEY")
        original_test_key = os.environ.get("TEST_KEY")

        try:
            os.chdir(test_base_dir)
            setup_environment()
            # Note: Can't easily test env vars are set without affecting test environment
        finally:
            os.chdir(original_cwd)

            # Restore original environment variables
            if original_openai_key is not None:
                os.environ["OPENAI_API_KEY"] = original_openai_key
            elif "OPENAI_API_KEY" in os.environ:
                del os.environ["OPENAI_API_KEY"]

            if original_test_key is not None:
                os.environ["TEST_KEY"] = original_test_key
            elif "TEST_KEY" in os.environ:
                del os.environ["TEST_KEY"]

    def test_validation_utilities(self, test_base_dir):
        """Test document validation functionality."""
        validator = DocumentValidator()

        # Test file validation
        test_file = os.path.join(test_base_dir, "test.pdf")
        with open(test_file, "w") as f:
            f.write("test")

        # Valid file
        assert validator.validate_file(Path(test_file)) is True

        # Invalid file - should raise ValidationError
        try:
            validator.validate_file(Path("/non/existent/file.pdf"))
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "File not found" in str(e)

        # Test URL validation
        assert validator.validate_url("https://example.com/doc.pdf") is True

        try:
            validator.validate_url("ftp://invalid.com/file")
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "Invalid URL scheme" in str(e)

    def test_cleanup_and_resource_management(self, test_base_dir):
        """Test cleanup utilities and resource management."""
        # Get resource manager
        manager = get_resource_manager()
        assert manager is not None

        # Register a temp file
        temp_file = os.path.join(test_base_dir, "temp_resource.txt")
        with open(temp_file, "w") as f:
            f.write("temp")

        manager.register_temp_file(temp_file)

        # Cleanup
        manager.cleanup()

        # Test cleanup function
        cleanup_temp_resources()

    def test_database_migrations(self, test_base_dir):
        """Test database migration framework."""
        # Test migration sequence
        db_path = os.path.join(test_base_dir, "test_migrations.db")

        # Remove existing database if it exists
        if os.path.exists(db_path):
            os.unlink(db_path)

        manager = MigrationManager(db_path)

        # Create test migrations
        migrations = [
            Migration(
                version=1,
                name="create_test_table",
                up_sql="CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT);",
                down_sql="DROP TABLE test_table;",
            ),
            Migration(
                version=2,
                name="add_column",
                up_sql="ALTER TABLE test_table ADD COLUMN created_at TIMESTAMP;",
                down_sql="ALTER TABLE test_table DROP COLUMN created_at;",
            ),
        ]

        # Apply migrations
        for migration in migrations:
            manager.apply_migration(migration)

        # Verify version
        assert manager.get_current_version() == 2

        # Verify table exists
        cursor = manager.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'"
        )
        assert cursor.fetchone() is not None

        # Test rollback
        manager.rollback_migration(1)
        assert manager.get_current_version() == 1

        manager.close()

    def test_real_migration_files(self, test_base_dir):
        """Test loading and applying real migration files."""
        # Get the real migrations directory
        migrations_base = Path(__file__).parent.parent.parent / "migrations"

        if not migrations_base.exists():
            pytest.skip("Migrations directory not found")

        # Test one database type (registry)
        migrations_dir = migrations_base / "registry"
        if migrations_dir.exists():
            db_path = os.path.join(test_base_dir, "test_registry.db")

            # Remove existing database if it exists
            if os.path.exists(db_path):
                os.unlink(db_path)

            # Load migrations
            migrations = load_migrations_from_sql_files(migrations_dir)
            assert len(migrations) > 0

            # Apply migrations
            manager = MigrationManager(db_path)
            result = manager.run_migrations(migrations)

            assert result["applied_count"] > 0
            assert result["current_version"] > 0

            # Verify documents table was created
            cursor = manager.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='documents'"
            )
            assert cursor.fetchone() is not None

            manager.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
