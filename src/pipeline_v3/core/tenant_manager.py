"""
Tenant Management for PostgreSQL Multi-Tenant System.

This module provides comprehensive tenant management capabilities including
tenant creation, configuration, quota management, and isolation enforcement.
"""

import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.postgres_base import PostgreSQLBase

from utils.common_utils import logger
from utils.config import PipelineConfig


class TenantError(Exception):
    """Base exception for tenant operations."""


class TenantNotFoundError(TenantError):
    """Raised when a tenant is not found."""


class TenantQuotaExceededError(TenantError):
    """Raised when a tenant exceeds their quota."""


class TenantManager:
    """
    Multi-tenant management system for PostgreSQL backend.

    Provides tenant creation, configuration, quota enforcement,
    and context management for proper data isolation.
    """

    def __init__(self, config: PipelineConfig | None = None):
        """
        Initialize tenant manager.

        Args:
            config: Pipeline configuration with PostgreSQL settings
        """
        self.config = config or PipelineConfig()

        # Validate PostgreSQL backend
        if not hasattr(self.config, "database") or self.config.database.backend != "postgresql":
            raise ValueError("TenantManager requires PostgreSQL backend configuration")

        self.pg_settings = self.config.database.postgresql

        # Initialize database connection
        self.db = PostgreSQLBase(
            self.pg_settings,
            "tenants",  # Use tenants schema
            log_queries=self.config.database.log_queries,
        )

        # Initialize connection pool
        self.db.initialize()

        logger.info("TenantManager initialized with PostgreSQL backend")

    def create_tenant(
        self,
        name: str,
        display_name: str | None = None,
        max_documents: int = 10000,
        max_storage_gb: int = 100,
        settings: Dict[str, Any] | None = None,
    ) -> str:
        """
        Create a new tenant with specified configuration.

        Args:
            name: Unique tenant name (used for identification)
            display_name: Human-readable display name
            max_documents: Maximum number of documents allowed
            max_storage_gb: Maximum storage in GB
            settings: Additional tenant-specific settings

        Returns:
            Tenant ID (UUID string)

        Raises:
            TenantError: If tenant creation fails
        """
        try:
            # Use PostgreSQL function for tenant creation
            result = self.db.fetch_one(
                "SELECT tenants.create_tenant(%s, %s, %s, %s) as tenant_id",
                (name, display_name, max_documents, max_storage_gb),
            )

            tenant_id = str(result["tenant_id"])

            # Update settings if provided
            if settings:
                self.update_tenant_settings(tenant_id, settings)

            # Log the operation
            self.db.execute(
                "SELECT tenants.log_operation(%s, %s, %s)",
                (
                    uuid.UUID(tenant_id),
                    "create_tenant",
                    self.db.json_to_jsonb(
                        {
                            "name": name,
                            "display_name": display_name,
                            "max_documents": max_documents,
                            "max_storage_gb": max_storage_gb,
                        }
                    ),
                ),
            )

            logger.info(f"Created new tenant: {tenant_id} ({name})")
            return tenant_id

        except Exception as e:
            logger.error(f"Failed to create tenant '{name}': {e}")
            raise TenantError(f"Tenant creation failed: {e}")

    def get_tenant_info(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get comprehensive tenant information.

        Args:
            tenant_id: Tenant ID

        Returns:
            Tenant information dictionary

        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        try:
            result = self.db.fetch_one(
                "SELECT * FROM tenants.get_tenant_info(%s)",
                (uuid.UUID(tenant_id),),
            )

            if not result:
                raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

            return {
                "tenant_id": str(result["tenant_id"]),
                "name": result["name"],
                "display_name": result["display_name"],
                "status": result["status"],
                "max_documents": result["max_documents"],
                "max_storage_gb": result["max_storage_gb"],
                "current_documents": result["current_documents"],
                "created_at": result["created_at"],
            }

        except Exception as e:
            if isinstance(e, TenantNotFoundError):
                raise
            logger.error(f"Failed to get tenant info for {tenant_id}: {e}")
            raise TenantError(f"Failed to retrieve tenant info: {e}")

    def list_tenants(self) -> List[Dict[str, Any]]:
        """
        List all tenants (admin operation).

        Returns:
            List of tenant information dictionaries
        """
        try:
            results = self.db.fetch_all("SELECT * FROM tenants.list_tenants()")

            return [
                {
                    "tenant_id": str(row["tenant_id"]),
                    "name": row["name"],
                    "display_name": row["display_name"],
                    "status": row["status"],
                    "document_count": row["document_count"],
                    "created_at": row["created_at"],
                }
                for row in results
            ]

        except Exception as e:
            logger.error(f"Failed to list tenants: {e}")
            raise TenantError(f"Failed to list tenants: {e}")

    def update_tenant_settings(self, tenant_id: str, settings: Dict[str, Any]) -> bool:
        """
        Update tenant-specific settings.

        Args:
            tenant_id: Tenant ID
            settings: Settings dictionary to update

        Returns:
            True if successful

        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        try:
            # Get current settings
            current = self.db.fetch_one(
                "SELECT settings FROM tenants.tenants WHERE tenant_id = %s",
                (uuid.UUID(tenant_id),),
            )

            if not current:
                raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

            # Merge settings
            current_settings = self.db.jsonb_to_dict(current["settings"]) or {}
            current_settings.update(settings)

            # Update in database
            self.db.execute(
                "UPDATE tenants.tenants SET settings = %s, updated_at = NOW() WHERE tenant_id = %s",
                (self.db.json_to_jsonb(current_settings), uuid.UUID(tenant_id)),
            )

            # Log the operation
            self.db.execute(
                "SELECT tenants.log_operation(%s, %s, %s)",
                (
                    uuid.UUID(tenant_id),
                    "update_settings",
                    self.db.json_to_jsonb({"updated_settings": settings}),
                ),
            )

            logger.info(f"Updated settings for tenant: {tenant_id}")
            return True

        except Exception as e:
            if isinstance(e, TenantNotFoundError):
                raise
            logger.error(f"Failed to update tenant settings for {tenant_id}: {e}")
            raise TenantError(f"Failed to update tenant settings: {e}")

    def disable_tenant(self, tenant_id: str) -> bool:
        """
        Disable a tenant (soft delete).

        Args:
            tenant_id: Tenant ID to disable

        Returns:
            True if successful

        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        try:
            result = self.db.fetch_one(
                "SELECT tenants.disable_tenant(%s) as success",
                (uuid.UUID(tenant_id),),
            )

            if not result["success"]:
                raise TenantNotFoundError(f"Tenant not found: {tenant_id}")

            # Log the operation
            self.db.execute(
                "SELECT tenants.log_operation(%s, %s, %s)",
                (uuid.UUID(tenant_id), "disable_tenant", self.db.json_to_jsonb({})),
            )

            logger.info(f"Disabled tenant: {tenant_id}")
            return True

        except Exception as e:
            if isinstance(e, TenantNotFoundError):
                raise
            logger.error(f"Failed to disable tenant {tenant_id}: {e}")
            raise TenantError(f"Failed to disable tenant: {e}")

    def check_quota(self, tenant_id: str, operation: str = "add_document") -> bool:
        """
        Check if tenant can perform an operation within quota limits.

        Args:
            tenant_id: Tenant ID
            operation: Operation type ('add_document', 'use_storage')

        Returns:
            True if within quota limits

        Raises:
            TenantQuotaExceededError: If quota is exceeded
            TenantNotFoundError: If tenant doesn't exist
        """
        try:
            tenant_info = self.get_tenant_info(tenant_id)

            if operation == "add_document":
                if tenant_info["current_documents"] >= tenant_info["max_documents"]:
                    raise TenantQuotaExceededError(
                        f"Document quota exceeded for tenant {tenant_id}: "
                        f"{tenant_info['current_documents']}/{tenant_info['max_documents']}"
                    )

            # Additional quota checks can be added here (storage, API calls, etc.)

            return True

        except (TenantQuotaExceededError, TenantNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Failed to check quota for tenant {tenant_id}: {e}")
            raise TenantError(f"Quota check failed: {e}")

    def set_tenant_context(self, tenant_id: str) -> None:
        """
        Set the current tenant context for database operations.

        Args:
            tenant_id: Tenant ID to set as current context

        Raises:
            TenantNotFoundError: If tenant doesn't exist
        """
        try:
            # Validate tenant exists
            self.get_tenant_info(tenant_id)

            # Set PostgreSQL session variable
            self.db.execute(
                "SELECT tenants.set_current_tenant(%s)",
                (uuid.UUID(tenant_id),),
            )

            logger.debug(f"Set tenant context to: {tenant_id}")

        except TenantNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to set tenant context to {tenant_id}: {e}")
            raise TenantError(f"Failed to set tenant context: {e}")

    def clear_tenant_context(self) -> None:
        """Clear the current tenant context."""
        try:
            self.db.execute("SELECT tenants.clear_tenant_context()")
            logger.debug("Cleared tenant context")
        except Exception as e:
            logger.error(f"Failed to clear tenant context: {e}")
            raise TenantError(f"Failed to clear tenant context: {e}")

    def get_current_tenant_id(self) -> str | None:
        """
        Get the current tenant ID from context.

        Returns:
            Current tenant ID or None if not set
        """
        try:
            result = self.db.fetch_one("SELECT tenants.current_tenant_id() as tenant_id")
            tenant_id = result["tenant_id"]

            # Return None for default tenant if no explicit context set
            default_tenant = uuid.UUID("00000000-0000-0000-0000-000000000000")
            if tenant_id == default_tenant:
                return None

            return str(tenant_id)

        except Exception as e:
            logger.error(f"Failed to get current tenant ID: {e}")
            return None

    def get_tenant_statistics(self, tenant_id: str) -> Dict[str, Any]:
        """
        Get comprehensive statistics for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Statistics dictionary
        """
        try:
            # Get basic tenant info
            tenant_info = self.get_tenant_info(tenant_id)

            # Get index statistics
            index_stats = self.db.fetch_all(
                "SELECT * FROM registry.get_index_statistics(%s)",
                (uuid.UUID(tenant_id),),
            )

            # Get job queue statistics (if exists)
            job_stats = self.db.fetch_one(
                """
                SELECT
                    COUNT(*) as total_jobs,
                    COUNT(CASE WHEN status = 'PENDING' THEN 1 END) as pending_jobs,
                    COUNT(CASE WHEN status = 'PROCESSING' THEN 1 END) as processing_jobs,
                    COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) as completed_jobs,
                    COUNT(CASE WHEN status = 'FAILED' THEN 1 END) as failed_jobs
                FROM jobs.queue
                WHERE tenant_id = %s
                """,
                (uuid.UUID(tenant_id),),
            )

            return {
                "tenant_info": tenant_info,
                "index_statistics": [
                    {
                        "index_type": row["index_type"],
                        "total_entries": row["total_entries"],
                        "unique_documents": row["unique_documents"],
                        "avg_chunks_per_doc": float(row["avg_chunks_per_doc"]),
                    }
                    for row in index_stats
                ],
                "job_statistics": {
                    "total_jobs": job_stats["total_jobs"],
                    "pending_jobs": job_stats["pending_jobs"],
                    "processing_jobs": job_stats["processing_jobs"],
                    "completed_jobs": job_stats["completed_jobs"],
                    "failed_jobs": job_stats["failed_jobs"],
                },
            }

        except Exception as e:
            logger.error(f"Failed to get tenant statistics for {tenant_id}: {e}")
            raise TenantError(f"Failed to get tenant statistics: {e}")

    def cleanup_tenant_data(self, tenant_id: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Clean up orphaned data for a tenant.

        Args:
            tenant_id: Tenant ID
            dry_run: If True, only report what would be cleaned up

        Returns:
            Cleanup report
        """
        try:
            # Set tenant context
            self.set_tenant_context(tenant_id)

            report = {"tenant_id": tenant_id, "dry_run": dry_run, "operations": []}

            # Find orphaned index entries
            orphaned_entries = self.db.fetch_all(
                "SELECT * FROM registry.find_orphaned_entries(%s)",
                (uuid.UUID(tenant_id),),
            )

            orphaned_count = sum(row["entry_count"] for row in orphaned_entries)

            if orphaned_count > 0:
                if not dry_run:
                    # Actually clean up
                    deleted_count = self.db.fetch_one(
                        "SELECT registry.cleanup_orphaned_entries(%s) as deleted",
                        (uuid.UUID(tenant_id),),
                    )["deleted"]

                    report["operations"].append(
                        {
                            "operation": "cleanup_orphaned_entries",
                            "deleted_count": deleted_count,
                        }
                    )
                else:
                    report["operations"].append(
                        {
                            "operation": "cleanup_orphaned_entries",
                            "would_delete": orphaned_count,
                            "orphaned_entries": [
                                {
                                    "doc_id": str(row["doc_id"]),
                                    "index_type": row["index_type"],
                                    "entry_count": row["entry_count"],
                                }
                                for row in orphaned_entries
                            ],
                        }
                    )

            # Clear tenant context
            self.clear_tenant_context()

            logger.info(f"Tenant cleanup {'dry run' if dry_run else 'completed'} for {tenant_id}")
            return report

        except Exception as e:
            self.clear_tenant_context()  # Ensure context is cleared
            logger.error(f"Failed to cleanup tenant data for {tenant_id}: {e}")
            raise TenantError(f"Tenant cleanup failed: {e}")

    def close(self) -> None:
        """Close database connections."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Convenience functions
def get_tenant_manager(config: PipelineConfig | None = None) -> TenantManager:
    """Get a TenantManager instance."""
    return TenantManager(config)


def create_tenant(
    name: str,
    display_name: str | None = None,
    max_documents: int = 10000,
    max_storage_gb: int = 100,
    config: PipelineConfig | None = None,
) -> str:
    """Convenience function to create a tenant."""
    with get_tenant_manager(config) as manager:
        return manager.create_tenant(name, display_name, max_documents, max_storage_gb)


def list_all_tenants(config: PipelineConfig | None = None) -> List[Dict[str, Any]]:
    """Convenience function to list all tenants."""
    with get_tenant_manager(config) as manager:
        return manager.list_tenants()
