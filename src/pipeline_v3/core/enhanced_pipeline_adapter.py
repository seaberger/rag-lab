"""
Enhanced Pipeline Adapter with Database Factory Support.

This module provides an adapter that uses the database factory to create
the appropriate database adapters based on configuration.
"""

from typing import Any, Dict, List

from src.pipeline_v3.core.database_factory import DatabaseFactory
from utils.common_utils import logger
from utils.config import PipelineConfig


class EnhancedPipelineAdapter:
    """
    Adapter for enhanced pipeline that uses database factory.

    This class provides backward compatibility while supporting both
    SQLite and PostgreSQL backends through the database factory.
    """

    def __init__(self, config: PipelineConfig | None = None, tenant_id: str | None = None):
        """
        Initialize enhanced pipeline adapter.

        Args:
            config: Pipeline configuration
            tenant_id: Tenant ID for multi-tenant isolation (PostgreSQL only)
        """
        self.config = config or PipelineConfig()
        self.tenant_id = tenant_id

        # Create database factory
        self.factory = DatabaseFactory(self.config, tenant_id)

        # Initialize adapters
        self._adapters = None
        self._initialized = False

    def initialize(self) -> None:
        """Initialize database adapters."""
        if self._initialized:
            return

        # Validate configuration
        if not self.factory.validate_backend_configuration():
            raise ValueError(f"Invalid database backend configuration: {self.factory.backend}")

        # Create adapters
        self._adapters = self.factory.create_all()
        self._initialized = True

        logger.info(f"EnhancedPipelineAdapter initialized with {self.factory.backend} backend")

    @property
    def registry(self):
        """Get document registry adapter."""
        if not self._initialized:
            self.initialize()
        return self._adapters["registry"]

    @property
    def keyword_index(self):
        """Get keyword index adapter."""
        if not self._initialized:
            self.initialize()
        return self._adapters["keyword_index"]

    @property
    def job_manager(self):
        """Get job manager adapter."""
        if not self._initialized:
            self.initialize()
        return self._adapters["job_manager"]

    @property
    def fingerprint_manager(self):
        """Get fingerprint manager adapter."""
        if not self._initialized:
            self.initialize()
        return self._adapters["fingerprint_manager"]

    async def process_document(
        self,
        source: str,
        mode: str = "auto",
        force: bool = False,
        metadata: Dict[str, Any] | None = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        Process a document using the appropriate adapters.

        This is a simplified example - in practice this would delegate
        to the actual enhanced pipeline implementation.
        """
        if not self._initialized:
            self.initialize()

        # Check if document needs processing
        if not force:
            changed = self.fingerprint_manager.has_changed(source)
            if not changed:
                logger.info(f"Document unchanged, skipping: {source}")
                return {"status": "skipped", "reason": "unchanged"}

        # In a real implementation, this would:
        # 1. Parse the document
        # 2. Extract content and metadata
        # 3. Generate embeddings
        # 4. Store in vector and keyword indexes
        # 5. Update registry and fingerprints

        logger.info(f"Processing document: {source} (mode: {mode})")

        # Simulate processing result
        result = {
            "status": "completed",
            "source": source,
            "mode": mode,
            "backend": self.factory.backend,
            "tenant_id": self.tenant_id,
        }

        return result

    def search_documents(
        self,
        query: str,
        search_type: str = "hybrid",
        limit: int = 10,
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Search documents using the appropriate index.

        This is a simplified example - in practice this would implement
        actual search logic with scoring and ranking.
        """
        if not self._initialized:
            self.initialize()

        logger.info(f"Searching: {query} (type: {search_type}, backend: {self.factory.backend})")

        # In a real implementation, this would:
        # 1. Query the keyword index for text matches
        # 2. Query the vector index for semantic matches
        # 3. Combine and rank results
        # 4. Apply filters
        # 5. Return formatted results

        # Simulate search results
        results = [
            {
                "doc_id": f"doc_{i}",
                "score": 0.9 - (i * 0.1),
                "source": f"example_{i}.pdf",
                "snippet": f"Match for query: {query}",
                "backend": self.factory.backend,
            }
            for i in range(min(limit, 3))  # Simulate 3 results
        ]

        return results

    def get_system_status(self) -> Dict[str, Any]:
        """Get system status including backend information."""
        if not self._initialized:
            self.initialize()

        # Get migration information
        migration_info = self.factory.get_migration_info()

        status = {
            "backend": self.factory.backend,
            "tenant_id": self.tenant_id,
            "initialized": self._initialized,
            "migration": migration_info,
            "components": {
                "registry": "available",
                "keyword_index": "available",
                "job_manager": "available",
                "fingerprint_manager": "available",
            },
        }

        # Add backend-specific status
        if self.factory.backend == "postgresql":
            pg_settings = self.config.database.postgresql
            status["postgresql"] = {
                "host": f"{pg_settings.host}:{pg_settings.port}",
                "database": pg_settings.database,
                "schemas": {
                    "registry": pg_settings.registry_schema,
                    "search": pg_settings.search_schema,
                    "jobs": pg_settings.jobs_schema,
                    "fingerprints": pg_settings.fingerprints_schema,
                },
                "tenant_id": self.tenant_id or pg_settings.default_tenant_id,
            }
        elif self.factory.backend == "sqlite":
            status["sqlite"] = {
                "registry_db": "document_registry_v3.db",
                "keyword_db": "keyword_index_v3.db",
                "jobs_db": "jobs_v3.db",
                "fingerprints_db": "fingerprints_v3.db",
            }

        return status

    def close(self) -> None:
        """Close all database connections."""
        if self._adapters:
            self.factory.close_all(self._adapters)
            self._adapters = None
            self._initialized = False
            logger.info("EnhancedPipelineAdapter closed")

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# Example usage functions
def create_pipeline_adapter(
    backend: str = "sqlite", tenant_id: str | None = None
) -> EnhancedPipelineAdapter:
    """
    Create a pipeline adapter with specified backend.

    Args:
        backend: Database backend ("sqlite" or "postgresql")
        tenant_id: Tenant ID for PostgreSQL multi-tenancy

    Returns:
        Configured pipeline adapter
    """
    from utils.config import DatabaseSettings

    config = PipelineConfig(database=DatabaseSettings(backend=backend))

    return EnhancedPipelineAdapter(config, tenant_id)


async def example_usage():
    """Example of using the enhanced pipeline adapter."""
    print("Enhanced Pipeline Adapter Example")
    print("=" * 40)

    # SQLite example
    print("\n1. SQLite Backend:")
    with create_pipeline_adapter("sqlite") as pipeline:
        status = pipeline.get_system_status()
        print(f"   Backend: {status['backend']}")
        print(f"   Components: {len(status['components'])} available")

        # Example document processing
        result = await pipeline.process_document("example.pdf", mode="datasheet")
        print(f"   Processing result: {result['status']}")

        # Example search
        results = pipeline.search_documents("sensor specs", limit=2)
        print(f"   Search results: {len(results)} found")

    # PostgreSQL example (configuration only - won't actually connect)
    print("\n2. PostgreSQL Backend:")
    try:
        with create_pipeline_adapter("postgresql", "tenant-123") as pipeline:
            status = pipeline.get_system_status()
            print(f"   Backend: {status['backend']}")
            print(f"   Tenant: {status['tenant_id']}")
            print(f"   Migration available: {status['migration']['migration_available']}")
    except Exception as e:
        print(f"   PostgreSQL adapter demo limited: {e}")

    print("\n✅ Enhanced pipeline adapter examples completed!")


if __name__ == "__main__":
    import asyncio
    import sys
    from pathlib import Path

    # Add project root to path
    project_root = Path(__file__).parents[3]
    sys.path.insert(0, str(project_root))

    # Re-import with correct paths
    from src.pipeline_v3.core.enhanced_pipeline_adapter import example_usage

    asyncio.run(example_usage())
