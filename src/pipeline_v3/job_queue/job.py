"""
Job Manager - Phase 1 Implementation

Persistent job tracking with resume capability for enterprise-grade reliability.
Manages job state, progress, and recovery from interruptions.
"""

import json
import sqlite3
import time
import uuid
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent))

from utils.common_utils import logger
from utils.config import PipelineConfig


class JobType(Enum):
    """Types of jobs that can be processed."""
    ADD = "add"
    UPDATE = "update"
    REMOVE = "remove"
    REPROCESS = "reprocess"


class JobStatus(Enum):
    """Job status enumeration."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


@dataclass
class JobRecord:
    """Represents a persistent job record."""
    job_id: str
    source: str
    job_type: str
    priority: int
    created_at: float
    updated_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    status: str = JobStatus.PENDING.value
    progress: float = 0.0
    worker_id: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: Dict[str, Any] = None
    intermediate_state: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.intermediate_state is None:
            self.intermediate_state = {}


class JobManager:
    """Persistent job tracking with resume capability."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        """Initialize job manager with configuration."""
        self.config = config or PipelineConfig()
        
        # Use configured storage path
        self.storage_path = Path(self.config.job_queue.job_storage_path)
        self.retention_days = self.config.job_queue.job_retention_days
        
        # Initialize database
        self._init_database()
        
        logger.info(f"JobManager initialized with storage: {self.storage_path}")
    
    def _init_database(self) -> None:
        """Initialize SQLite database for job storage."""
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = sqlite3.connect(str(self.storage_path))
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                job_type TEXT NOT NULL,
                priority INTEGER NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                started_at REAL,
                completed_at REAL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0.0,
                worker_id TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                max_retries INTEGER NOT NULL DEFAULT 3,
                metadata TEXT,  -- JSON
                intermediate_state TEXT  -- JSON
            )
        """)
        
        # Create indexes for performance
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)
        """)
        
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_jobs_priority_created 
            ON jobs(priority, created_at)
        """)
        
        self.conn.commit()
        logger.info("Job database initialized")
    
    def create_job(
        self, 
        source: str,
        job_type: JobType,
        priority: int = 2,
        metadata: Optional[Dict[str, Any]] = None,
        max_retries: int = 3
    ) -> str:
        """Create a new job with unique ID."""
        job_id = str(uuid.uuid4())
        current_time = time.time()
        
        job = JobRecord(
            job_id=job_id,
            source=source,
            job_type=job_type.value,
            priority=priority,
            created_at=current_time,
            updated_at=current_time,
            metadata=metadata or {},
            max_retries=max_retries
        )
        
        self._save_job(job)
        
        logger.info(f"Created job {job_id[:8]} for {source} (type: {job_type.value})")
        return job_id
    
    def _save_job(self, job: JobRecord) -> None:
        """Save job record to database."""
        self.conn.execute("""
            INSERT OR REPLACE INTO jobs
            (job_id, source, job_type, priority, created_at, updated_at,
             started_at, completed_at, status, progress, worker_id, error_message,
             retry_count, max_retries, metadata, intermediate_state)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job.job_id,
            job.source,
            job.job_type,
            job.priority,
            job.created_at,
            job.updated_at,
            job.started_at,
            job.completed_at,
            job.status,
            job.progress,
            job.worker_id,
            job.error_message,
            job.retry_count,
            job.max_retries,
            json.dumps(job.metadata) if job.metadata else None,
            json.dumps(job.intermediate_state) if job.intermediate_state else None
        ))
        self.conn.commit()
    
    def get_job(self, job_id: str) -> Optional[JobRecord]:
        """Get job record by ID."""
        cursor = self.conn.execute("""
            SELECT job_id, source, job_type, priority, created_at, updated_at,
                   started_at, completed_at, status, progress, worker_id, error_message,
                   retry_count, max_retries, metadata, intermediate_state
            FROM jobs WHERE job_id = ?
        """, (job_id,))
        
        row = cursor.fetchone()
        if row:
            return self._row_to_job(row)
        return None
    
    def _row_to_job(self, row) -> JobRecord:
        """Convert database row to JobRecord."""
        metadata = json.loads(row[14]) if row[14] else {}
        intermediate_state = json.loads(row[15]) if row[15] else {}
        
        return JobRecord(
            job_id=row[0],
            source=row[1],
            job_type=row[2],
            priority=row[3],
            created_at=row[4],
            updated_at=row[5],
            started_at=row[6],
            completed_at=row[7],
            status=row[8],
            progress=row[9],
            worker_id=row[10],
            error_message=row[11],
            retry_count=row[12],
            max_retries=row[13],
            metadata=metadata,
            intermediate_state=intermediate_state
        )
    
    def update_job_status(
        self, 
        job_id: str,
        status: JobStatus,
        progress: float = None,
        worker_id: str = None,
        error_message: str = None
    ) -> bool:
        """Update job status and progress."""
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for status update")
            return False
        
        current_time = time.time()
        job.status = status.value
        job.updated_at = current_time
        
        if progress is not None:
            job.progress = progress
        
        if worker_id is not None:
            job.worker_id = worker_id
        
        if error_message is not None:
            job.error_message = error_message
        
        # Set timestamps based on status
        if status == JobStatus.PROCESSING and not job.started_at:
            job.started_at = current_time
        elif status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            job.completed_at = current_time
        
        self._save_job(job)
        
        logger.debug(f"Updated job {job_id[:8]} status to {status.value}")
        return True
    
    def save_job_state(self, job_id: str, state: Dict[str, Any]) -> bool:
        """Save intermediate job state for resume capability."""
        job = self.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found for state save")
            return False
        
        job.intermediate_state = state
        job.updated_at = time.time()
        
        self._save_job(job)
        
        logger.debug(f"Saved state for job {job_id[:8]}")
        return True
    
    def increment_retry_count(self, job_id: str) -> bool:
        """Increment retry count for a failed job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        job.retry_count += 1
        job.updated_at = time.time()
        
        # Reset status to pending if we haven't exceeded max retries
        if job.retry_count <= job.max_retries:
            job.status = JobStatus.PENDING.value
            job.error_message = None
            logger.info(f"Job {job_id[:8]} queued for retry {job.retry_count}/{job.max_retries}")
        else:
            job.status = JobStatus.FAILED.value
            logger.error(f"Job {job_id[:8]} failed permanently after {job.retry_count} retries")
        
        self._save_job(job)
        return True
    
    def list_jobs(
        self, 
        status: Optional[JobStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[JobRecord]:
        """List jobs with optional status filter."""
        query = """
            SELECT job_id, source, job_type, priority, created_at, updated_at,
                   started_at, completed_at, status, progress, worker_id, error_message,
                   retry_count, max_retries, metadata, intermediate_state
            FROM jobs
        """
        params = []
        
        if status:
            query += " WHERE status = ?"
            params.append(status.value)
        
        query += " ORDER BY priority ASC, created_at ASC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cursor = self.conn.execute(query, params)
        
        jobs = []
        for row in cursor.fetchall():
            jobs.append(self._row_to_job(row))
        
        return jobs
    
    def resume_interrupted_jobs(self) -> List[JobRecord]:
        """Find and return jobs that were interrupted during processing."""
        # Jobs marked as processing but not recently updated are likely interrupted
        stale_threshold = time.time() - 300  # 5 minutes
        
        cursor = self.conn.execute("""
            SELECT job_id, source, job_type, priority, created_at, updated_at,
                   started_at, completed_at, status, progress, worker_id, error_message,
                   retry_count, max_retries, metadata, intermediate_state
            FROM jobs 
            WHERE status = ? AND updated_at < ?
        """, (JobStatus.PROCESSING.value, stale_threshold))
        
        interrupted_jobs = []
        for row in cursor.fetchall():
            job = self._row_to_job(row)
            
            # Mark as interrupted
            job.status = JobStatus.INTERRUPTED.value
            job.updated_at = time.time()
            self._save_job(job)
            
            interrupted_jobs.append(job)
        
        if interrupted_jobs:
            logger.info(f"Found {len(interrupted_jobs)} interrupted jobs")
        
        return interrupted_jobs
    
    def requeue_job(self, job_id: str, reset_retries: bool = False) -> bool:
        """Requeue a failed or interrupted job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        job.status = JobStatus.PENDING.value
        job.progress = 0.0
        job.error_message = None
        job.worker_id = None
        job.updated_at = time.time()
        
        if reset_retries:
            job.retry_count = 0
        
        self._save_job(job)
        
        logger.info(f"Requeued job {job_id[:8]}")
        return True
    
    def get_job_statistics(self) -> Dict[str, Any]:
        """Get comprehensive job statistics."""
        cursor = self.conn.execute("""
            SELECT 
                status,
                COUNT(*) as count,
                AVG(CASE WHEN completed_at IS NOT NULL AND started_at IS NOT NULL 
                    THEN completed_at - started_at ELSE NULL END) as avg_duration,
                SUM(retry_count) as total_retries
            FROM jobs
            GROUP BY status
        """)
        
        stats_by_status = {}
        total_jobs = 0
        total_retries = 0
        
        for row in cursor.fetchall():
            status = row[0]
            count = row[1]
            avg_duration = row[2]
            retries = row[3] or 0
            
            stats_by_status[status] = {
                "count": count,
                "average_duration": avg_duration,
                "retries": retries
            }
            
            total_jobs += count
            total_retries += retries
        
        # Get oldest and newest jobs
        cursor = self.conn.execute("""
            SELECT MIN(created_at), MAX(created_at) FROM jobs
        """)
        row = cursor.fetchone()
        oldest_job = row[0]
        newest_job = row[1]
        
        return {
            "by_status": stats_by_status,
            "total_jobs": total_jobs,
            "total_retries": total_retries,
            "oldest_job": oldest_job,
            "newest_job": newest_job,
            "database_path": str(self.storage_path)
        }
    
    def cleanup_completed_jobs(self, older_than_days: Optional[int] = None) -> int:
        """Remove old completed/failed job records."""
        cutoff_days = older_than_days or self.retention_days
        cutoff_time = time.time() - (cutoff_days * 24 * 60 * 60)
        
        # Count jobs to be deleted
        cursor = self.conn.execute("""
            SELECT COUNT(*) FROM jobs 
            WHERE status IN ('completed', 'failed', 'cancelled') 
            AND completed_at < ?
        """, (cutoff_time,))
        count = cursor.fetchone()[0]
        
        if count > 0:
            # Delete old jobs
            self.conn.execute("""
                DELETE FROM jobs 
                WHERE status IN ('completed', 'failed', 'cancelled') 
                AND completed_at < ?
            """, (cutoff_time,))
            self.conn.commit()
            
            logger.info(f"Cleaned up {count} old job records (older than {cutoff_days} days)")
        
        return count
    
    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing job."""
        job = self.get_job(job_id)
        if not job:
            return False
        
        if job.status in [JobStatus.COMPLETED.value, JobStatus.FAILED.value, JobStatus.CANCELLED.value]:
            logger.warning(f"Cannot cancel job {job_id[:8]} in status {job.status}")
            return False
        
        job.status = JobStatus.CANCELLED.value
        job.completed_at = time.time()
        job.updated_at = time.time()
        
        self._save_job(job)
        
        logger.info(f"Cancelled job {job_id[:8]}")
        return True
    
    def close(self) -> None:
        """Close database connection."""
        if hasattr(self, 'conn'):
            self.conn.close()
            logger.debug("Job database connection closed")
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()