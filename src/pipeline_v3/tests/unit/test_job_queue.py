"""
Unit tests for Job Queue components.

Tests cover job creation, state management, and queue operations.
"""

import sys
import tempfile
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from job_queue.job import JobManager
from job_queue.job import JobStatus as JobStatusPersistent
from job_queue.job import JobType
from job_queue.manager import DocumentQueue, JobPriority, JobStatus, QueueJob

from utils.config import PipelineConfig

try:
    from core.database_factory import DatabaseFactory
except ImportError:
    DatabaseFactory = None


class TestQueueJob:
    """Test suite for QueueJob class."""

    def test_job_creation(self):
        """Test basic job creation."""
        job = QueueJob(
            job_id=str(uuid.uuid4()),
            source="test.pdf",
            job_type="add",
            priority=JobPriority.NORMAL.value,
            metadata={"doc_id": "123"},
        )

        assert job.job_id is not None
        assert job.source == "test.pdf"
        assert job.status == JobStatus.PENDING
        assert job.priority == JobPriority.NORMAL.value
        assert job.metadata["doc_id"] == "123"

    def test_job_priority_comparison(self):
        """Test job priority ordering."""
        import uuid

        high_job = QueueJob(
            job_id=str(uuid.uuid4()),
            source="high.pdf",
            job_type="add",
            priority=JobPriority.HIGH.value,
        )

        normal_job = QueueJob(
            job_id=str(uuid.uuid4()),
            source="normal.pdf",
            job_type="add",
            priority=JobPriority.NORMAL.value,
        )

        # HIGH priority (1) should come before NORMAL priority (2)
        assert high_job < normal_job


class TestDocumentQueue:
    """Test suite for DocumentQueue manager."""

    @pytest.fixture
    def queue(self, test_config):
        """Create a test document queue."""
        test_config.job_queue.max_concurrent = 2
        queue = DocumentQueue(config=test_config)
        return queue

    @pytest.mark.asyncio
    async def test_submit_job(self, queue):
        """Test submitting jobs to the queue."""
        # Submit a job
        job_id = await queue.add_job(
            source="test.pdf",
            job_type="add",
            priority=JobPriority.NORMAL,
            metadata={"test": "data"},
        )

        assert job_id is not None
        assert queue.stats["jobs_submitted"] == 1

    @pytest.mark.asyncio
    async def test_job_priority_ordering(self, queue):
        """Test that jobs are added with correct priority."""
        # Submit jobs with different priorities
        await queue.add_job(
            source="low.pdf",
            job_type="add",
            priority=JobPriority.LOW,
            metadata={"priority": "low"},
        )

        await queue.add_job(
            source="high.pdf",
            job_type="add",
            priority=JobPriority.HIGH,
            metadata={"priority": "high"},
        )

        await queue.add_job(
            source="normal.pdf",
            job_type="add",
            priority=JobPriority.NORMAL,
            metadata={"priority": "normal"},
        )

        # Verify jobs were submitted
        assert queue.stats["jobs_submitted"] == 3
        assert queue.pending.qsize() == 3

    @pytest.mark.asyncio
    async def test_job_lifecycle(self, queue):
        """Test job status tracking."""
        # Submit a job
        job_id = await queue.add_job(
            source="test.pdf", job_type="add", metadata={"test": "data"}
        )

        # Check job status
        status = queue.get_job_status(job_id)
        assert status is not None
        assert status["job_id"] == job_id
        assert status["status"] == JobStatus.PENDING.value

        # Can't test actual processing without starting workers
        # Just verify the job is in the pending queue
        assert queue.pending.qsize() == 1

    @pytest.mark.asyncio
    async def test_job_cancellation(self, queue):
        """Test job cancellation."""
        # Submit a job
        job_id = await queue.add_job(
            source="test.pdf", job_type="add", metadata={"test": "data"}
        )

        # Cancel the job
        cancelled = queue.cancel_job(job_id)
        assert cancelled

        # Verify job was cancelled
        assert job_id in queue.failed
        assert queue.failed[job_id].status == JobStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_queue_statistics(self, queue):
        """Test queue statistics."""
        # Submit various jobs
        for i in range(5):
            await queue.add_job(
                source=f"doc{i}.pdf", job_type="add", metadata={"index": i}
            )

        # Cancel one job to simulate failure
        # Get a job ID from the pending queue (need to peek)
        temp_jobs = []
        job_to_cancel = None
        while not queue.pending.empty() and not job_to_cancel:
            job = queue.pending.get()
            temp_jobs.append(job)
            if len(temp_jobs) == 1:
                job_to_cancel = job.job_id

        # Restore jobs to queue
        for job in temp_jobs:
            queue.pending.put(job)

        # Cancel one job
        if job_to_cancel:
            queue.cancel_job(job_to_cancel)

        # Get statistics
        stats = queue.get_status()

        assert stats["performance"]["jobs_submitted"] == 5
        assert stats["queue_status"]["failed"] == 1  # Cancelled jobs go to failed

    @pytest.mark.asyncio
    async def test_pause_resume(self, queue):
        """Test pause and resume functionality."""
        # Submit jobs
        for i in range(3):
            await queue.add_job(source=f"doc{i}.pdf", job_type="add")

        # Pause queue
        queue.pause_processing()
        assert queue.is_paused

        # Resume queue
        queue.resume_processing()
        assert not queue.is_paused

        # Verify jobs are still pending
        assert queue.pending.qsize() == 3


class TestJobManager:
    """Test suite for persistent JobManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test databases."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def job_manager(self, test_config):
        """Create a test job manager."""
        # Try to use DatabaseFactory if available
        if DatabaseFactory and test_config.database.backend in ["sqlite", "postgresql"]:
            try:
                factory = DatabaseFactory(test_config)
                if factory.validate_backend_configuration():
                    adapters = factory.create_all()
                    job_manager = adapters["job_manager"]
                    # Store factory and adapters for cleanup
                    job_manager._test_factory = factory
                    job_manager._test_adapters = adapters
                    return job_manager
            except Exception:
                pass  # Fall back to direct initialization

        # Direct initialization as fallback
        return JobManager(config=test_config)

    @pytest.fixture(autouse=True)
    def cleanup_job_manager(self, job_manager):
        """Ensure proper cleanup after tests."""
        yield
        # Clean up DatabaseFactory resources if used
        if hasattr(job_manager, '_test_factory') and hasattr(job_manager, '_test_adapters'):
            job_manager._test_factory.close_all(job_manager._test_adapters)

    def test_create_job(self, job_manager):
        """Test creating a persistent job."""
        job_id = job_manager.create_job(
            source="test.pdf",
            job_type=JobType.ADD,
            priority=2,
            metadata={"test": "data"},
        )

        assert job_id is not None

        # Get the job to verify it was created
        job = job_manager.get_job(job_id)
        assert job is not None
        assert job.source == "test.pdf"
        assert job.job_type == JobType.ADD.value
        assert job.status == JobStatusPersistent.PENDING.value

    def test_get_job(self, job_manager):
        """Test retrieving a job."""
        # Create job
        job_id = job_manager.create_job(source="test.pdf", job_type=JobType.ADD)

        # Retrieve it
        retrieved = job_manager.get_job(job_id)
        assert retrieved is not None
        assert retrieved.job_id == job_id
        assert retrieved.source == "test.pdf"

    def test_update_job_status(self, job_manager):
        """Test updating job status."""
        # Create job
        job_id = job_manager.create_job(source="test.pdf", job_type=JobType.ADD)

        # Update status
        job_manager.update_job_status(job_id, JobStatusPersistent.PROCESSING)

        # Verify update
        updated = job_manager.get_job(job_id)
        assert updated.status == JobStatusPersistent.PROCESSING.value

    def test_list_jobs(self, job_manager):
        """Test listing jobs by status."""
        # Create multiple jobs
        job1_id = job_manager.create_job(source="doc1.pdf", job_type=JobType.ADD)
        job2_id = job_manager.create_job(source="doc2.pdf", job_type=JobType.UPDATE)
        job3_id = job_manager.create_job(source="doc3.pdf", job_type=JobType.ADD)

        # Update statuses
        job_manager.update_job_status(job1_id, JobStatusPersistent.COMPLETED)
        job_manager.update_job_status(job2_id, JobStatusPersistent.PROCESSING)

        # Verify job3_id status before listing
        job3 = job_manager.get_job(job3_id)
        assert job3 is not None, f"Job {job3_id} not found"
        assert (
            job3.status == JobStatusPersistent.PENDING.value
        ), f"Job {job3_id} has status {job3.status}, expected {JobStatusPersistent.PENDING.value}"

        # List by status - use larger limit to ensure we get our job
        pending_jobs = job_manager.list_jobs(
            status=JobStatusPersistent.PENDING, limit=1000
        )

        # Find our specific job in the list (there may be others from previous tests)
        pending_job_ids = [job.job_id for job in pending_jobs]
        assert job3_id in pending_job_ids, f"Job {job3_id} not found in pending jobs"

        completed_jobs = job_manager.list_jobs(
            status=JobStatusPersistent.COMPLETED, limit=1000
        )
        completed_job_ids = [job.job_id for job in completed_jobs]
        assert job1_id in completed_job_ids

    def test_job_persistence(self, job_manager):
        """Test that jobs persist across manager instances."""
        # Create job
        job_id = job_manager.create_job(
            source="test.pdf", job_type=JobType.ADD, metadata={"important": "data"}
        )

        # Create new manager instance
        config = job_manager.config
        new_manager = JobManager(config=config)

        # Should be able to retrieve the job
        retrieved = new_manager.get_job(job_id)
        assert retrieved is not None
        assert retrieved.metadata["important"] == "data"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
