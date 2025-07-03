#!/usr/bin/env python3
"""
Test script for Phase 1 implementation: Queue & Fingerprinting

Tests the DocumentQueue, FingerprintManager, and JobManager components.
"""

import asyncio

# Add current directory to path for imports
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.fingerprint import FingerprintManager
from job_queue.job import JobManager, JobStatus, JobType
from job_queue.manager import DocumentQueue, JobPriority

from utils.config import PipelineConfig


async def test_document_queue():
    """Test DocumentQueue functionality."""
    print("🧪 Testing DocumentQueue...")

    try:
        # Create queue with test config
        config = PipelineConfig()
        config.job_queue.max_concurrent = 2

        queue = DocumentQueue(config)

        # Add some test jobs
        job_ids = []
        test_sources = ["test_doc1.pdf", "test_doc2.pdf", "test_doc3.pdf"]

        for i, source in enumerate(test_sources):
            priority = JobPriority.HIGH if i == 0 else JobPriority.NORMAL
            job_id = await queue.add_job(source, "add", priority)
            job_ids.append(job_id)

        print(f"✅ Added {len(job_ids)} jobs to queue")

        # Test batch addition
        batch_sources = ["batch1.pdf", "batch2.pdf"]
        batch_ids = await queue.add_batch(batch_sources, "add", JobPriority.LOW)
        print(f"✅ Added batch of {len(batch_ids)} jobs")

        # Start processing (simulate for 10 seconds)
        print("🔄 Starting queue processing...")

        # Create task for processing
        process_task = asyncio.create_task(queue.start_processing())

        # Let it run until jobs complete or timeout
        try:
            await asyncio.wait_for(process_task, timeout=15.0)
        except TimeoutError:
            print("⏰ Processing timeout - shutting down queue")

        # Check status
        status = queue.get_status()
        print(f"📊 Queue status: {status['queue_status']}")
        print(f"⚙️  Worker status: {status['worker_status']}")
        print(f"📈 Performance: {status['performance']}")

        # Shutdown queue if still running
        if not queue.is_shutdown:
            await queue.shutdown()

        # Final status
        final_status = queue.get_status()
        print(f"✅ Final queue status: {final_status['queue_status']}")

        return True

    except Exception as e:
        print(f"❌ DocumentQueue test failed: {e}")
        return False


def test_fingerprint_manager():
    """Test FingerprintManager functionality."""
    print("\n🧪 Testing FingerprintManager...")

    try:
        # Create temporary config
        config = PipelineConfig()
        config.fingerprint.storage_path = "./test_fingerprints.db"

        with FingerprintManager(config) as fingerprint_mgr:
            # Create test file
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                f.write("This is test content for fingerprinting")
                test_file = Path(f.name)

            try:
                # Test new document detection
                is_new = fingerprint_mgr.has_changed(test_file)
                print(f"✅ New document detected: {is_new}")

                # Compute and store fingerprint
                fingerprint = fingerprint_mgr.compute_fingerprint(test_file)
                fingerprint_mgr.update_fingerprint(fingerprint, "test_doc_id", "processed")
                print("✅ Fingerprint computed and stored")

                # Test unchanged document
                is_changed = fingerprint_mgr.has_changed(test_file)
                print(f"✅ Document unchanged detected: {not is_changed}")

                # Modify file and test change detection
                time.sleep(1)  # Ensure different timestamp
                with open(test_file, "a") as f:
                    f.write("\nModified content")

                is_changed = fingerprint_mgr.has_changed(test_file)
                print(f"✅ Document change detected: {is_changed}")

                # Test document history
                history = fingerprint_mgr.get_document_history(test_file)
                print(f"✅ Document history: {len(history)} entries")

                # Test statistics
                stats = fingerprint_mgr.get_stats()
                print(f"✅ Fingerprint stats: {stats['total_documents']} documents")

            finally:
                # Cleanup
                test_file.unlink(missing_ok=True)
                Path("./test_fingerprints.db").unlink(missing_ok=True)

        return True

    except Exception as e:
        print(f"❌ FingerprintManager test failed: {e}")
        return False


def test_job_manager():
    """Test JobManager functionality."""
    print("\n🧪 Testing JobManager...")

    try:
        # Create temporary config
        config = PipelineConfig()
        config.job_queue.job_storage_path = "./test_jobs.db"

        with JobManager(config) as job_mgr:
            # Create test jobs
            job_id1 = job_mgr.create_job("test1.pdf", JobType.ADD, priority=1)
            job_id2 = job_mgr.create_job("test2.pdf", JobType.UPDATE, priority=2)
            print("✅ Created 2 test jobs")

            # Test job status updates
            job_mgr.update_job_status(job_id1, JobStatus.PROCESSING, progress=0.5)
            job_mgr.update_job_status(job_id2, JobStatus.COMPLETED, progress=1.0)
            print("✅ Updated job statuses")

            # Test job state saving
            job_mgr.save_job_state(job_id1, {"stage": "parsing", "chunks_processed": 5})
            print("✅ Saved job state")

            # Test job retrieval
            job1 = job_mgr.get_job(job_id1)
            job2 = job_mgr.get_job(job_id2)
            print(f"✅ Retrieved jobs: {job1.status}, {job2.status}")

            # Test job listing
            all_jobs = job_mgr.list_jobs()
            pending_jobs = job_mgr.list_jobs(JobStatus.PROCESSING)
            print(f"✅ Job listing: {len(all_jobs)} total, {len(pending_jobs)} processing")

            # Test statistics
            stats = job_mgr.get_job_statistics()
            print(f"✅ Job statistics: {stats['total_jobs']} total jobs")

        # Cleanup
        Path("./test_jobs.db").unlink(missing_ok=True)

        return True

    except Exception as e:
        print(f"❌ JobManager test failed: {e}")
        return False


async def main():
    """Run all Phase 1 tests."""
    print("🚀 Phase 1 Component Tests")
    print("=" * 50)

    tests = [
        ("DocumentQueue", test_document_queue()),
        ("FingerprintManager", test_fingerprint_manager()),
        ("JobManager", test_job_manager()),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_coro in tests:
        if asyncio.iscoroutine(test_coro):
            result = await test_coro
        else:
            result = test_coro

        if result:
            passed += 1
        else:
            print(f"\n❌ {test_name} test failed")

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All Phase 1 tests passed! Queue & Fingerprinting components ready.")
        return 0
    print("⚠️  Some tests failed. Check issues before proceeding.")
    return 1


if __name__ == "__main__":
    import asyncio

    exit_code = asyncio.run(main())
    sys.exit(exit_code)
