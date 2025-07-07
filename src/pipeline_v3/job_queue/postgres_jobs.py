"""
PostgreSQL implementation of Job Queue.

This module provides a PostgreSQL-backed job queue with advanced features
like SKIP LOCKED for concurrent processing and NOTIFY/LISTEN for real-time updates.
"""

import uuid
from pathlib import Path
from typing import Any, Dict

from src.pipeline_v3.core.postgres_base import PostgreSQLBase
from src.pipeline_v3.job_queue.job import JobRecord, JobStatus, JobType
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class PostgreSQLJobManager:
    """PostgreSQL implementation of job queue with multi-tenant support."""

    def __init__(
        self,
        config: PipelineConfig | None = None,
        tenant_id: str | None = None,
        connection_manager=None,
    ):
        """
        Initialize PostgreSQL job manager.

        Args:
            config: Pipeline configuration
            tenant_id: Tenant ID for multi-tenant isolation
            connection_manager: Optional tenant connection manager for pooling
        """
        self.config = config or PipelineConfig()

        # Get database settings
        if not hasattr(self.config, "database") or self.config.database.backend != "postgresql":
            raise ValueError("PostgreSQL backend not configured")

        self.db_settings = self.config.database
        self.pg_settings = self.db_settings.postgresql

        # Set tenant ID
        self.tenant_id = tenant_id or self.pg_settings.default_tenant_id

        # Job queue settings
        self.retention_days = self.config.job_queue.job_retention_days

        # Initialize PostgreSQL base with connection manager
        if connection_manager:
            # Use shared connection pool from tenant manager
            self.db = connection_manager.get_pool(self.tenant_id, self.pg_settings.jobs_schema)
        else:
            # Create dedicated connection pool
            self.db = PostgreSQLBase(
                self.pg_settings,
                self.pg_settings.jobs_schema,
                log_queries=self.db_settings.log_queries,
            )
            # Initialize connection pool
            self.db.initialize()

        # Set tenant context for RLS
        self._set_tenant_context()

        logger.info(f"PostgreSQLJobManager initialized for tenant: {self.tenant_id}")

    def _set_tenant_context(self):
        """Set the tenant context for Row Level Security."""
        try:
            self.db.execute(
                "SELECT tenants.set_current_tenant(%s)",
                (self.tenant_id,),
            )
            logger.debug(f"Set tenant context to: {self.tenant_id}")
        except Exception as e:
            # Fallback if tenant functions don't exist (single-tenant mode)
            logger.warning(f"Could not set tenant context: {e}")

    def create_job(
        self,
        source: str | Path,
        job_type: JobType,
        priority: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new job and add it to the queue."""
        job_id = str(uuid.uuid4())
        source_key = str(Path(source).resolve())

        query = """
            INSERT INTO queue (
                job_id, tenant_id, source, job_type, priority, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s
            )
        """

        self.db.execute(
            query,
            (
                uuid.UUID(job_id),
                self.tenant_id,
                source_key,
                job_type.value,
                priority,
                self.db.json_to_jsonb(metadata) if metadata else None,
            ),
        )

        logger.info(f"Created job: {job_id[:8]} - {job_type.value} for {source}")
        return job_id

    def get_job(self, job_id: str) -> JobRecord | None:
        """Get job by ID."""
        query = """
            SELECT * FROM queue
            WHERE job_id = %s AND tenant_id = %s
        """

        row = self.db.fetch_one(query, (uuid.UUID(job_id), self.tenant_id))

        if row:
            return self._row_to_job(row)
        return None

    def _row_to_job(self, row: Dict[str, Any]) -> JobRecord:
        """Convert database row to JobRecord."""
        return JobRecord(
            job_id=str(row["job_id"]),
            source=row["source"],
            job_type=row["job_type"],
            priority=row["priority"],
            created_at=row["created_at"].timestamp(),
            updated_at=row["updated_at"].timestamp(),
            started_at=row["started_at"].timestamp() if row["started_at"] else None,
            completed_at=row["completed_at"].timestamp() if row["completed_at"] else None,
            status=row["status"],
            progress=float(row["progress"]),
            worker_id=row["worker_id"],
            error_message=row["error_message"],
            retry_count=row["retry_count"],
            max_retries=row["max_retries"],
            metadata=self.db.jsonb_to_dict(row["metadata"]) or {},
            intermediate_state=self.db.jsonb_to_dict(row["intermediate_state"]) or {},
        )

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        worker_id: str | None = None,
        progress: float | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Update job status and related fields."""
        updates = ["status = %s", "updated_at = NOW()"]
        params = [status.value]

        if worker_id is not None:
            updates.append("worker_id = %s")
            params.append(worker_id)

        if progress is not None:
            updates.append("progress = %s")
            params.append(progress)

        if error_message is not None:
            updates.append("error_message = %s")
            params.append(error_message)

        # Set timestamps based on status
        if status == JobStatus.PROCESSING:
            updates.append("started_at = COALESCE(started_at, NOW())")
        elif status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            updates.append("completed_at = NOW()")

        query = f"""
            UPDATE queue
            SET {", ".join(updates)}
            WHERE job_id = %s AND tenant_id = %s
        """

        params.extend([uuid.UUID(job_id), self.tenant_id])

        result = self.db.execute(query, tuple(params))

        success = result > 0
        if success:
            logger.info(f"Updated job status: {job_id[:8]} -> {status.value}")

        return success

    def claim_next_job(self, worker_id: str) -> JobRecord | None:
        """
        Claim the next available job atomically using SKIP LOCKED.

        This ensures no two workers can claim the same job.
        """
        # Use the stored function for atomic job claiming
        query = "SELECT * FROM jobs.claim_next_job(%s, %s)"

        row = self.db.fetch_one(query, (worker_id, self.tenant_id))

        if row and row.get("job_id"):
            job = self._row_to_job(row)
            logger.info(f"Worker {worker_id} claimed job: {job.job_id[:8]}")
            return job

        return None

    def save_job_state(self, job_id: str, state: dict[str, Any]) -> bool:
        """Save intermediate job state for resume capability."""
        query = """
            UPDATE queue
            SET intermediate_state = %s,
                updated_at = NOW()
            WHERE job_id = %s AND tenant_id = %s
        """

        result = self.db.execute(
            query, (self.db.json_to_jsonb(state), uuid.UUID(job_id), self.tenant_id)
        )

        return result > 0

    def increment_retry_count(self, job_id: str) -> bool:
        """Increment retry count for a job."""
        query = """
            UPDATE queue
            SET retry_count = retry_count + 1,
                updated_at = NOW()
            WHERE job_id = %s AND tenant_id = %s
            RETURNING retry_count, max_retries
        """

        row = self.db.fetch_one(query, (uuid.UUID(job_id), self.tenant_id))

        if row:
            retry_count = row["retry_count"]
            max_retries = row["max_retries"]

            if retry_count >= max_retries:
                self.update_job_status(
                    job_id, JobStatus.FAILED, error_message="Max retries exceeded"
                )
                logger.warning(f"Job {job_id[:8]} exceeded max retries ({max_retries})")

            return True

        return False

    def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[JobRecord]:
        """List jobs with optional filtering."""
        conditions = ["tenant_id = %s"]
        params = [self.tenant_id]

        if status:
            conditions.append("status = %s")
            params.append(status.value)

        query = f"""
            SELECT * FROM queue
            WHERE {" AND ".join(conditions)}
            ORDER BY priority DESC, created_at ASC
            LIMIT %s OFFSET %s
        """

        params.extend([limit or 100, offset])

        rows = self.db.fetch_all(query, tuple(params))

        return [self._row_to_job(row) for row in rows]

    def resume_interrupted_jobs(self) -> list[JobRecord]:
        """Find and mark interrupted jobs for resumption."""
        # Mark processing jobs as interrupted
        update_query = """
            UPDATE queue
            SET status = %s,
                updated_at = NOW()
            WHERE tenant_id = %s
            AND status = %s
            AND worker_id IS NOT NULL
        """

        self.db.execute(
            update_query,
            (JobStatus.INTERRUPTED.value, self.tenant_id, JobStatus.PROCESSING.value),
        )

        # Get interrupted jobs
        select_query = """
            SELECT * FROM queue
            WHERE tenant_id = %s
            AND status = %s
            AND retry_count < max_retries
            ORDER BY priority DESC, created_at ASC
        """

        rows = self.db.fetch_all(select_query, (self.tenant_id, JobStatus.INTERRUPTED.value))

        jobs = [self._row_to_job(row) for row in rows]

        if jobs:
            logger.info(f"Found {len(jobs)} interrupted jobs to resume")

        return jobs

    def requeue_job(self, job_id: str, reset_retries: bool = False) -> bool:
        """Requeue a job for processing."""
        updates = [
            "status = %s",
            "worker_id = NULL",
            "progress = 0.0",
            "error_message = NULL",
            "updated_at = NOW()",
        ]
        params = [JobStatus.PENDING.value]

        if reset_retries:
            updates.append("retry_count = 0")

        query = f"""
            UPDATE queue
            SET {", ".join(updates)}
            WHERE job_id = %s AND tenant_id = %s
        """

        params.extend([uuid.UUID(job_id), self.tenant_id])

        result = self.db.execute(query, tuple(params))

        if result > 0:
            logger.info(f"Requeued job: {job_id[:8]}")

        return result > 0

    def get_job_statistics(self) -> dict[str, Any]:
        """Get comprehensive job queue statistics."""
        # Overall statistics
        stats_query = """
            SELECT
                COUNT(*) as total_jobs,
                COUNT(CASE WHEN status = %s THEN 1 END) as pending,
                COUNT(CASE WHEN status = %s THEN 1 END) as processing,
                COUNT(CASE WHEN status = %s THEN 1 END) as completed,
                COUNT(CASE WHEN status = %s THEN 1 END) as failed,
                COUNT(CASE WHEN status = %s THEN 1 END) as cancelled,
                COUNT(CASE WHEN status = %s THEN 1 END) as interrupted,
                AVG(CASE
                    WHEN completed_at IS NOT NULL AND started_at IS NOT NULL
                    THEN EXTRACT(EPOCH FROM (completed_at - started_at))
                END) as avg_processing_time,
                COUNT(DISTINCT worker_id) as active_workers
            FROM queue
            WHERE tenant_id = %s
        """

        stats = self.db.fetch_one(
            stats_query,
            (
                JobStatus.PENDING.value,
                JobStatus.PROCESSING.value,
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                JobStatus.INTERRUPTED.value,
                self.tenant_id,
            ),
        )

        # Jobs by type
        type_query = """
            SELECT job_type, COUNT(*) as count
            FROM queue
            WHERE tenant_id = %s
            GROUP BY job_type
        """

        type_rows = self.db.fetch_all(type_query, (self.tenant_id,))
        jobs_by_type = {row["job_type"]: row["count"] for row in type_rows}

        # Recent performance
        recent_query = """
            SELECT
                COUNT(*) as recent_completed,
                AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as recent_avg_time
            FROM queue
            WHERE tenant_id = %s
            AND status = %s
            AND completed_at > NOW() - INTERVAL '1 hour'
        """

        recent = self.db.fetch_one(recent_query, (self.tenant_id, JobStatus.COMPLETED.value))

        return {
            "total_jobs": stats["total_jobs"] or 0,
            "status_breakdown": {
                "pending": stats["pending"] or 0,
                "processing": stats["processing"] or 0,
                "completed": stats["completed"] or 0,
                "failed": stats["failed"] or 0,
                "cancelled": stats["cancelled"] or 0,
                "interrupted": stats["interrupted"] or 0,
            },
            "jobs_by_type": jobs_by_type,
            "performance": {
                "avg_processing_time_seconds": float(stats["avg_processing_time"] or 0),
                "active_workers": stats["active_workers"] or 0,
                "recent_completed_last_hour": recent["recent_completed"] or 0,
                "recent_avg_time_seconds": float(recent["recent_avg_time"] or 0),
            },
            "tenant_id": self.tenant_id,
        }

    def cleanup_completed_jobs(self, older_than_days: int | None = None) -> int:
        """Remove old completed jobs to maintain database size."""
        days = older_than_days or self.retention_days

        query = """
            DELETE FROM queue
            WHERE tenant_id = %s
            AND status IN (%s, %s, %s)
            AND completed_at < NOW() - INTERVAL '%s days'
        """

        result = self.db.execute(
            query,
            (
                self.tenant_id,
                JobStatus.COMPLETED.value,
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                days,
            ),
        )

        if result > 0:
            logger.info(f"Cleaned up {result} old jobs")

        return result

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a pending or processing job."""
        query = """
            UPDATE queue
            SET status = %s,
                completed_at = NOW(),
                updated_at = NOW()
            WHERE job_id = %s
            AND tenant_id = %s
            AND status IN (%s, %s)
        """

        result = self.db.execute(
            query,
            (
                JobStatus.CANCELLED.value,
                uuid.UUID(job_id),
                self.tenant_id,
                JobStatus.PENDING.value,
                JobStatus.PROCESSING.value,
            ),
        )

        if result > 0:
            logger.info(f"Cancelled job: {job_id[:8]}")

        return result > 0

    def get_queue_health(self) -> dict[str, Any]:
        """Get queue health metrics for monitoring."""
        query = """
            SELECT
                (SELECT COUNT(*) FROM queue WHERE tenant_id = %s AND status = %s) as pending_count,
                (SELECT COUNT(*) FROM queue WHERE tenant_id = %s AND status = %s AND created_at < NOW() - INTERVAL '10 minutes') as stale_pending,
                (SELECT COUNT(*) FROM queue WHERE tenant_id = %s AND status = %s AND started_at < NOW() - INTERVAL '30 minutes') as long_running,
                (SELECT COUNT(*) FROM queue WHERE tenant_id = %s AND retry_count >= max_retries) as max_retries_reached,
                (SELECT MAX(EXTRACT(EPOCH FROM (NOW() - created_at))) FROM queue WHERE tenant_id = %s AND status = %s) as oldest_pending_age
        """

        health = self.db.fetch_one(
            query,
            (
                self.tenant_id,
                JobStatus.PENDING.value,
                self.tenant_id,
                JobStatus.PENDING.value,
                self.tenant_id,
                JobStatus.PROCESSING.value,
                self.tenant_id,
                self.tenant_id,
                JobStatus.PENDING.value,
            ),
        )

        return {
            "healthy": health["stale_pending"] == 0 and health["long_running"] == 0,
            "pending_jobs": health["pending_count"] or 0,
            "stale_pending_jobs": health["stale_pending"] or 0,
            "long_running_jobs": health["long_running"] or 0,
            "max_retries_reached": health["max_retries_reached"] or 0,
            "oldest_pending_seconds": float(health["oldest_pending_age"] or 0),
            "tenant_id": self.tenant_id,
        }

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
