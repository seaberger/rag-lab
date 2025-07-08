"""
Database Factory for Pipeline v3.

This module provides a factory pattern to create database adapters based on
configuration, supporting both SQLite and PostgreSQL backends.
"""

from typing import Any, Protocol, runtime_checkable

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig

# Conditional imports based on backend - imported at module level for clarity
# These will be used conditionally in the factory methods
try:
    # PostgreSQL adapters
    from src.pipeline_v3.core.postgres_fingerprint import PostgreSQLFingerprintManager
    from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
    from src.pipeline_v3.core.tenant_connection_manager import get_tenant_connection_manager
    from src.pipeline_v3.job_queue.postgres_jobs import PostgreSQLJobManager
    from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex

    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False
    PostgreSQLDocumentRegistry = None
    PostgreSQLFingerprintManager = None
    get_tenant_connection_manager = None
    PostgreSQLJobManager = None
    PostgreSQLKeywordIndex = None

# SQLite adapters (kept for fallback compatibility only)


@runtime_checkable
class DocumentRegistryProtocol(Protocol):
    """Protocol for document registry implementations."""

    def register_document(
        self,
        source: str,
        content_hash: str,
        size: int,
        modified_time: float,
        doc_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Register a new document."""
        ...

    def get_document(self, doc_id: str):
        """Get document by ID."""
        ...

    def get_document_by_source(self, source: str):
        """Get document by source path."""
        ...

    def update_document_state(self, doc_id: str, state, error_msg: str | None = None) -> bool:
        """Update document state."""
        ...

    def remove_document(self, doc_id: str) -> bool:
        """Remove document."""
        ...

    def list_documents(self, state=None, indexed: bool | None = None, limit: int | None = None):
        """List documents with filtering."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


@runtime_checkable
class KeywordIndexProtocol(Protocol):
    """Protocol for keyword index implementations."""

    def add_document(
        self,
        doc_id: str,
        chunk_id: str,
        text: str,
        keywords: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        """Add document to index."""
        ...

    def remove_document(self, doc_id: str):
        """Remove document from index."""
        ...

    def search(self, query: str, limit: int = 10, filters: dict[str, Any] | None = None):
        """Search the index."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


@runtime_checkable
class JobManagerProtocol(Protocol):
    """Protocol for job manager implementations."""

    def add_job(self, job_type: str, payload: dict[str, Any], priority: int = 0):
        """Add a job to the queue."""
        ...

    def get_next_job(self, worker_id: str):
        """Get next job for processing."""
        ...

    def complete_job(self, job_id: str, result: dict[str, Any] | None = None):
        """Mark job as completed."""
        ...

    def fail_job(self, job_id: str, error_message: str):
        """Mark job as failed."""
        ...

    def get_queue_stats(self):
        """Get queue statistics."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


@runtime_checkable
class FingerprintManagerProtocol(Protocol):
    """Protocol for fingerprint manager implementations."""

    def get_fingerprint(self, source: str):
        """Get stored fingerprint."""
        ...

    def update_fingerprint(self, fingerprint, doc_id: str | None = None) -> bool:
        """Update fingerprint."""
        ...

    def has_changed(self, source: str) -> bool:
        """Check if document has changed."""
        ...

    def mark_processing_status(self, source: str, status: str, doc_id: str | None = None) -> bool:
        """Mark processing status."""
        ...

    def close(self) -> None:
        """Close database connection."""
        ...


class DatabaseFactory:
    """Factory for creating database adapters based on configuration."""

    def __init__(self, config: PipelineConfig | None = None, tenant_id: str | None = None):
        """
        Initialize database factory.

        Args:
            config: Pipeline configuration
            tenant_id: Tenant ID for multi-tenant isolation (PostgreSQL only)
        """
        self.config = config or PipelineConfig()
        self.tenant_id = tenant_id
        self.backend = self.config.database.backend

        # Initialize connection manager for PostgreSQL
        self._connection_manager = None
        if self.backend == "postgresql" and POSTGRESQL_AVAILABLE:
            self._connection_manager = get_tenant_connection_manager(self.config)

        logger.info(f"DatabaseFactory initialized with backend: {self.backend}")

    def create_document_registry(self) -> DocumentRegistryProtocol:
        """Create document registry adapter."""
        if self.backend == "postgresql":
            if not POSTGRESQL_AVAILABLE:
                raise ImportError(
                    "PostgreSQL adapters not available. Install required dependencies."
                )
            registry = PostgreSQLDocumentRegistry(
                self.config, self.tenant_id, connection_manager=self._connection_manager
            )
            logger.info("Created PostgreSQL document registry")
            return registry
        else:
            raise ValueError(
                "SQLite backend is no longer supported. Please use 'postgresql' backend."
            )

    def create_keyword_index(self) -> KeywordIndexProtocol:
        """Create keyword index adapter."""
        if self.backend == "postgresql":
            if not POSTGRESQL_AVAILABLE:
                raise ImportError(
                    "PostgreSQL adapters not available. Install required dependencies."
                )
            index = PostgreSQLKeywordIndex(
                self.config, self.tenant_id, connection_manager=self._connection_manager
            )
            logger.info("Created PostgreSQL keyword index")
            return index
        else:
            raise ValueError(
                "SQLite backend is no longer supported. Please use 'postgresql' backend."
            )

    def create_job_manager(self) -> JobManagerProtocol:
        """Create job manager adapter."""
        if self.backend == "postgresql":
            if not POSTGRESQL_AVAILABLE:
                raise ImportError(
                    "PostgreSQL adapters not available. Install required dependencies."
                )
            manager = PostgreSQLJobManager(
                self.config, self.tenant_id, connection_manager=self._connection_manager
            )
            logger.info("Created PostgreSQL job manager")
            return manager
        else:
            raise ValueError(
                "SQLite backend is no longer supported. Please use 'postgresql' backend."
            )

    def create_fingerprint_manager(self) -> FingerprintManagerProtocol:
        """Create fingerprint manager adapter."""
        if self.backend == "postgresql":
            if not POSTGRESQL_AVAILABLE:
                raise ImportError(
                    "PostgreSQL adapters not available. Install required dependencies."
                )
            manager = PostgreSQLFingerprintManager(
                self.config, self.tenant_id, connection_manager=self._connection_manager
            )
            logger.info("Created PostgreSQL fingerprint manager")
            return manager
        else:
            raise ValueError(
                "SQLite backend is no longer supported. Please use 'postgresql' backend."
            )

    def create_all(self) -> dict[str, Any]:
        """Create all database adapters."""
        adapters = {
            "registry": self.create_document_registry(),
            "keyword_index": self.create_keyword_index(),
            "job_manager": self.create_job_manager(),
            "fingerprint_manager": self.create_fingerprint_manager(),
        }

        logger.info(f"Created all {self.backend} database adapters")
        return adapters

    def validate_backend_configuration(self) -> bool:
        """Validate that the backend is properly configured."""
        if self.backend == "postgresql":
            # Check PostgreSQL configuration
            pg_settings = self.config.database.postgresql

            required_fields = ["host", "port", "database", "user"]
            missing_fields = []

            for field in required_fields:
                if not getattr(pg_settings, field, None):
                    missing_fields.append(field)

            if missing_fields:
                logger.error(f"Missing PostgreSQL configuration: {missing_fields}")
                return False

            if not pg_settings.password:
                logger.warning("PostgreSQL password not set - connection may fail")

            logger.info("PostgreSQL configuration validated")
            return True

        elif self.backend == "sqlite":
            # SQLite needs minimal configuration
            logger.info("SQLite configuration validated")
            return True

        else:
            logger.error(f"Unknown database backend: {self.backend}")
            return False

    def get_migration_info(self) -> dict[str, Any]:
        """Get information about migration between backends."""
        current_backend = self.backend

        if current_backend == "sqlite":
            target_backend = "postgresql"
            migration_available = True
            migration_direction = "SQLite → PostgreSQL"
        elif current_backend == "postgresql":
            target_backend = "sqlite"
            migration_available = False  # Not implemented yet
            migration_direction = "PostgreSQL → SQLite (not available)"
        else:
            target_backend = None
            migration_available = False
            migration_direction = "Unknown backend"

        return {
            "current_backend": current_backend,
            "target_backend": target_backend,
            "migration_available": migration_available,
            "migration_direction": migration_direction,
            "migration_tool": "migrate to-postgres" if migration_available else None,
        }

    def close_all(self, adapters: dict[str, Any]) -> None:
        """Close all database connections."""
        for name, adapter in adapters.items():
            try:
                adapter.close()
                logger.debug(f"Closed {name} adapter")
            except Exception as e:
                logger.warning(f"Error closing {name} adapter: {e}")

        logger.info("All database adapters closed")


class DatabaseContext:
    """Context manager for database adapters."""

    def __init__(self, config: PipelineConfig | None = None, tenant_id: str | None = None):
        """Initialize database context."""
        self.factory = DatabaseFactory(config, tenant_id)
        self.adapters = None

    def __enter__(self):
        """Enter context - create all adapters."""
        if not self.factory.validate_backend_configuration():
            raise ValueError(f"Invalid database backend configuration: {self.factory.backend}")

        self.adapters = self.factory.create_all()
        return self.adapters

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context - close all adapters."""
        if self.adapters:
            self.factory.close_all(self.adapters)


# Convenience functions for quick access
def create_database_adapters(
    config: PipelineConfig | None = None, tenant_id: str | None = None
) -> dict[str, Any]:
    """Convenience function to create all database adapters."""
    factory = DatabaseFactory(config, tenant_id)
    return factory.create_all()


def get_database_factory(
    config: PipelineConfig | None = None, tenant_id: str | None = None
) -> DatabaseFactory:
    """Get a database factory instance."""
    return DatabaseFactory(config, tenant_id)
