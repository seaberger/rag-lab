"""
Document Queue Manager - Phase 1 Implementation

Queue-based document processing with job management, priority handling,
and configurable concurrency for production-scale document processing.
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from queue import PriorityQueue

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.common_utils import logger
from utils.config import PipelineConfig


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobPriority(Enum):
    """Job priority levels."""
    LOW = 3
    NORMAL = 2
    HIGH = 1
    URGENT = 0


@dataclass
class QueueJob:
    """Represents a job in the document processing queue."""
    job_id: str
    source: Union[str, Path]
    job_type: str  # "add", "update", "remove"
    priority: int = JobPriority.NORMAL.value
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    status: JobStatus = JobStatus.PENDING
    error_message: Optional[str] = None
    progress: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other):
        """Priority queue comparison - lower number = higher priority."""
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


class DocumentQueue:
    """Queue-based document processing with job management."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize document queue with configuration."""
        self.config = config or PipelineConfig()
        
        # Job queues and tracking
        self.pending = PriorityQueue()
        self.processing: Dict[str, QueueJob] = {}
        self.completed: Dict[str, QueueJob] = {}
        self.failed: Dict[str, QueueJob] = {}
        
        # Configuration
        self.max_workers = self.config.job_queue.max_concurrent
        self.is_paused = False
        self.is_shutdown = False
        
        # Worker management
        self.workers: List[asyncio.Task] = []
        self.worker_semaphore = asyncio.Semaphore(self.max_workers)
        
        # Statistics
        self.stats = {
            "jobs_submitted": 0,
            "jobs_completed": 0,
            "jobs_failed": 0,
            "total_processing_time": 0.0,
            "average_processing_time": 0.0,
            "start_time": time.time()
        }
        
        logger.info(f"DocumentQueue initialized with {self.max_workers} max workers")
    
    async def add_job(
        self, 
        source: Union[str, Path],
        job_type: str = "add",
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Add a job to the processing queue."""
        job_id = str(uuid.uuid4())
        
        job = QueueJob(
            job_id=job_id,
            source=source,
            job_type=job_type,
            priority=priority.value,
            metadata=metadata or {}
        )
        
        self.pending.put(job)
        self.stats["jobs_submitted"] += 1
        
        logger.info(f"Added job {job_id[:8]} for {source} (priority: {priority.name})")
        return job_id
    
    async def add_batch(
        self, 
        sources: List[Union[str, Path]], 
        job_type: str = "add",
        priority: JobPriority = JobPriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[str]:
        """Add multiple jobs to the queue efficiently."""
        job_ids = []
        
        for source in sources:
            job_id = await self.add_job(source, job_type, priority, metadata)
            job_ids.append(job_id)
        
        logger.info(f"Added batch of {len(sources)} jobs to queue")
        return job_ids
    
    async def start_processing(self) -> None:
        """Start the queue processing workers."""
        if self.workers:
            logger.warning("Queue processing already started")
            return
        
        logger.info(f"Starting {self.max_workers} processing workers")
        
        # Create worker tasks
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._worker(f"worker-{i}"))
            self.workers.append(worker)
        
        # Wait for all workers to complete
        try:
            await asyncio.gather(*self.workers)
        except Exception as e:
            logger.error(f"Error in queue processing: {e}")
        finally:
            self.workers.clear()
    
    async def _worker(self, worker_name: str) -> None:
        """Individual worker that processes jobs from the queue."""
        logger.info(f"{worker_name} started")
        
        while not self.is_shutdown:
            try:
                # Wait if paused
                while self.is_paused and not self.is_shutdown:
                    await asyncio.sleep(0.1)
                
                if self.is_shutdown:
                    break
                
                # Get next job (non-blocking check)
                try:
                    job = self.pending.get_nowait()
                except:
                    # No job available - check if we should exit
                    if self.pending.empty() and not self.processing:
                        # No jobs pending or processing, worker can exit
                        logger.info(f"{worker_name} exiting - no work available")
                        break
                    # Brief wait before checking again
                    await asyncio.sleep(0.1)
                    continue
                
                # Acquire semaphore for concurrency control
                async with self.worker_semaphore:
                    await self._process_job(job, worker_name)
                    
            except Exception as e:
                logger.error(f"{worker_name} error: {e}")
                await asyncio.sleep(1.0)  # Brief pause on error
        
        logger.info(f"{worker_name} stopped")
    
    async def _process_job(self, job: QueueJob, worker_name: str) -> None:
        """Process a single job."""
        job.status = JobStatus.PROCESSING
        job.updated_at = time.time()
        job.progress = 0.0
        
        # Move job to processing tracker
        self.processing[job.job_id] = job
        
        start_time = time.time()
        logger.info(f"{worker_name} processing job {job.job_id[:8]} - {job.source}")
        
        try:
            # TODO: This will be replaced with actual document processing
            # For now, simulate processing
            await self._simulate_processing(job)
            
            # Job completed successfully
            job.status = JobStatus.COMPLETED
            job.progress = 1.0
            processing_time = time.time() - start_time
            
            # Move to completed
            self.processing.pop(job.job_id, None)
            self.completed[job.job_id] = job
            
            # Update statistics
            self.stats["jobs_completed"] += 1
            self.stats["total_processing_time"] += processing_time
            self.stats["average_processing_time"] = (
                self.stats["total_processing_time"] / self.stats["jobs_completed"]
            )
            
            logger.info(f"{worker_name} completed job {job.job_id[:8]} in {processing_time:.2f}s")
            
        except Exception as e:
            # Job failed
            job.status = JobStatus.FAILED
            job.error_message = str(e)
            job.updated_at = time.time()
            
            # Move to failed
            self.processing.pop(job.job_id, None)
            self.failed[job.job_id] = job
            
            self.stats["jobs_failed"] += 1
            
            logger.error(f"{worker_name} failed job {job.job_id[:8]}: {e}")
    
    async def _simulate_processing(self, job: QueueJob) -> None:
        """Simulate document processing for testing."""
        # Simulate variable processing time based on job type
        processing_times = {
            "add": 2.0,
            "update": 1.5,
            "remove": 0.5
        }
        
        total_time = processing_times.get(job.job_type, 2.0)
        steps = 10
        step_time = total_time / steps
        
        for i in range(steps):
            if self.is_shutdown:
                raise Exception("Processing interrupted by shutdown")
                
            job.progress = (i + 1) / steps
            job.updated_at = time.time()
            await asyncio.sleep(step_time)
    
    def pause_processing(self) -> None:
        """Pause queue processing (current jobs continue, new jobs wait)."""
        self.is_paused = True
        logger.info("Queue processing paused")
    
    def resume_processing(self) -> None:
        """Resume paused queue processing."""
        self.is_paused = False
        logger.info("Queue processing resumed")
    
    async def shutdown(self, wait_for_completion: bool = True) -> None:
        """Shutdown the queue processing."""
        logger.info("Shutting down document queue...")
        self.is_shutdown = True
        
        if wait_for_completion and self.workers:
            # Wait for workers to finish current jobs
            logger.info("Waiting for workers to complete current jobs...")
            await asyncio.gather(*self.workers, return_exceptions=True)
        
        # Cancel any remaining jobs
        while not self.pending.empty():
            try:
                job = self.pending.get_nowait()
                job.status = JobStatus.CANCELLED
                self.failed[job.job_id] = job
            except:
                break
        
        logger.info("Document queue shutdown complete")
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive queue status."""
        pending_count = self.pending.qsize()
        processing_count = len(self.processing)
        completed_count = len(self.completed)
        failed_count = len(self.failed)
        
        uptime = time.time() - self.stats["start_time"]
        
        return {
            "queue_status": {
                "pending": pending_count,
                "processing": processing_count,
                "completed": completed_count,
                "failed": failed_count,
                "total": pending_count + processing_count + completed_count + failed_count
            },
            "worker_status": {
                "max_workers": self.max_workers,
                "active_workers": len(self.workers),
                "is_paused": self.is_paused,
                "is_shutdown": self.is_shutdown
            },
            "performance": {
                "jobs_submitted": self.stats["jobs_submitted"],
                "jobs_completed": self.stats["jobs_completed"],
                "jobs_failed": self.stats["jobs_failed"],
                "success_rate": (
                    self.stats["jobs_completed"] / max(1, self.stats["jobs_submitted"]) * 100
                ),
                "average_processing_time": self.stats["average_processing_time"],
                "total_processing_time": self.stats["total_processing_time"],
                "uptime": uptime
            },
            "timestamp": time.time()
        }
    
    def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific job."""
        # Check all job collections
        for collection_name, collection in [
            ("processing", self.processing),
            ("completed", self.completed),
            ("failed", self.failed)
        ]:
            if job_id in collection:
                job = collection[job_id]
                return {
                    "job_id": job.job_id,
                    "source": str(job.source),
                    "job_type": job.job_type,
                    "status": job.status.value,
                    "priority": job.priority,
                    "progress": job.progress,
                    "created_at": job.created_at,
                    "updated_at": job.updated_at,
                    "error_message": job.error_message,
                    "metadata": job.metadata
                }
        
        # Check pending queue (less efficient but comprehensive)
        temp_jobs = []
        found_job = None
        
        while not self.pending.empty():
            job = self.pending.get()
            temp_jobs.append(job)
            if job.job_id == job_id:
                found_job = job
        
        # Restore pending queue
        for job in temp_jobs:
            self.pending.put(job)
        
        if found_job:
            return {
                "job_id": found_job.job_id,
                "source": str(found_job.source),
                "job_type": found_job.job_type,
                "status": found_job.status.value,
                "priority": found_job.priority,
                "progress": found_job.progress,
                "created_at": found_job.created_at,
                "updated_at": found_job.updated_at,
                "error_message": found_job.error_message,
                "metadata": found_job.metadata
            }
        
        return None
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a specific job if it's not yet processing."""
        # Can't cancel jobs that are already processing or completed
        if job_id in self.processing or job_id in self.completed:
            return False
        
        # Remove from pending queue if present
        temp_jobs = []
        cancelled = False
        
        while not self.pending.empty():
            job = self.pending.get()
            if job.job_id == job_id:
                job.status = JobStatus.CANCELLED
                self.failed[job.job_id] = job
                cancelled = True
                logger.info(f"Cancelled job {job_id[:8]}")
            else:
                temp_jobs.append(job)
        
        # Restore pending queue without cancelled job
        for job in temp_jobs:
            self.pending.put(job)
        
        return cancelled