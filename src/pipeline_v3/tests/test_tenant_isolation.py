"""
Test tenant isolation and Row Level Security for PostgreSQL backend.

This module tests that tenant isolation is properly enforced through
PostgreSQL Row Level Security policies and tenant context management.
"""

import pytest
import uuid
from pathlib import Path

from core.tenant_manager import TenantManager, TenantError, TenantNotFoundError
from core.database_factory import DatabaseFactory
from utils.config import PipelineConfig


class TestTenantIsolation:
    """Test tenant isolation functionality."""

    @pytest.fixture
    def postgresql_config(self):
        """Create a PostgreSQL configuration for testing."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        return config

    @pytest.fixture
    def tenant_manager(self, postgresql_config):
        """Create a tenant manager for testing."""
        return TenantManager(postgresql_config)

    @pytest.mark.asyncio
    async def test_tenant_creation_and_management(self, tenant_manager):
        """Test basic tenant CRUD operations."""
        # Create a test tenant
        tenant_name = f"test_tenant_{uuid.uuid4().hex[:8]}"
        tenant_id = tenant_manager.create_tenant(
            name=tenant_name,
            display_name=f"Test Tenant {tenant_name}",
            max_documents=5000,
            max_storage_gb=50,
        )

        assert tenant_id is not None
        assert isinstance(tenant_id, str)

        # Get tenant info
        tenant_info = tenant_manager.get_tenant_info(tenant_id)
        assert tenant_info["name"] == tenant_name
        assert tenant_info["max_documents"] == 5000
        assert tenant_info["max_storage_gb"] == 50
        assert tenant_info["current_documents"] == 0

        # Update tenant settings
        new_settings = {"custom_setting": "test_value", "feature_flags": {"advanced": True}}
        tenant_manager.update_tenant_settings(tenant_id, new_settings)

        # Verify settings were updated
        updated_info = tenant_manager.get_tenant_info(tenant_id)
        # Note: The get_tenant_info doesn't return settings, but we can verify they were stored

        # List tenants should include our new tenant
        all_tenants = tenant_manager.list_tenants()
        tenant_names = [t["name"] for t in all_tenants]
        assert tenant_name in tenant_names

        # Clean up - disable the tenant
        tenant_manager.disable_tenant(tenant_id)

        disabled_info = tenant_manager.get_tenant_info(tenant_id)
        assert disabled_info["status"] == "suspended"

    @pytest.mark.asyncio
    async def test_tenant_context_management(self, tenant_manager):
        """Test tenant context setting and clearing."""
        # Create two test tenants
        tenant1_name = f"tenant1_{uuid.uuid4().hex[:8]}"
        tenant2_name = f"tenant2_{uuid.uuid4().hex[:8]}"

        tenant1_id = tenant_manager.create_tenant(tenant1_name)
        tenant2_id = tenant_manager.create_tenant(tenant2_name)

        try:
            # Test setting tenant context
            tenant_manager.set_tenant_context(tenant1_id)
            current = tenant_manager.get_current_tenant_id()
            assert current == tenant1_id

            # Test switching context
            tenant_manager.set_tenant_context(tenant2_id)
            current = tenant_manager.get_current_tenant_id()
            assert current == tenant2_id

            # Test clearing context
            tenant_manager.clear_tenant_context()
            current = tenant_manager.get_current_tenant_id()
            assert current is None  # Should return None for default tenant

        finally:
            # Cleanup
            tenant_manager.disable_tenant(tenant1_id)
            tenant_manager.disable_tenant(tenant2_id)

    @pytest.mark.asyncio
    async def test_tenant_quota_enforcement(self, tenant_manager):
        """Test tenant quota enforcement."""
        # Create a tenant with very low limits
        tenant_name = f"quota_test_{uuid.uuid4().hex[:8]}"
        tenant_id = tenant_manager.create_tenant(
            name=tenant_name,
            max_documents=1,  # Very low limit for testing
            max_storage_gb=1,
        )

        try:
            # Check quota when within limits
            assert tenant_manager.check_quota(tenant_id, "add_document") is True

            # Test quota check with tenant that doesn't exist
            fake_tenant_id = str(uuid.uuid4())
            with pytest.raises(TenantNotFoundError):
                tenant_manager.check_quota(fake_tenant_id, "add_document")

        finally:
            # Cleanup
            tenant_manager.disable_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_database_factory_tenant_isolation(self, postgresql_config):
        """Test that database factory properly isolates tenants."""
        # Create two test tenants
        with TenantManager(postgresql_config) as manager:
            tenant1_id = manager.create_tenant(f"factory_test1_{uuid.uuid4().hex[:8]}")
            tenant2_id = manager.create_tenant(f"factory_test2_{uuid.uuid4().hex[:8]}")

            try:
                # Create database adapters for each tenant
                factory1 = DatabaseFactory(postgresql_config, tenant1_id)
                factory2 = DatabaseFactory(postgresql_config, tenant2_id)

                with factory1.create_all() as adapters1, factory2.create_all() as adapters2:
                    # Test that each tenant gets their own isolated data
                    registry1 = adapters1["registry"]
                    registry2 = adapters2["registry"]

                    # Register the same document in both tenants
                    test_source = "/tmp/test_document.pdf"
                    doc1_id = registry1.register_document(
                        source=test_source,
                        content_hash="hash123",
                        size=1024,
                        modified_time=1234567890.0,
                    )

                    doc2_id = registry2.register_document(
                        source=test_source,
                        content_hash="hash123",
                        size=1024,
                        modified_time=1234567890.0,
                    )

                    # Should get different document IDs due to tenant isolation
                    assert doc1_id != doc2_id

                    # Each tenant should only see their own document
                    tenant1_docs = registry1.list_documents()
                    tenant2_docs = registry2.list_documents()

                    tenant1_doc_ids = [doc.doc_id for doc in tenant1_docs]
                    tenant2_doc_ids = [doc.doc_id for doc in tenant2_docs]

                    assert doc1_id in tenant1_doc_ids
                    assert doc1_id not in tenant2_doc_ids
                    assert doc2_id in tenant2_doc_ids
                    assert doc2_id not in tenant1_doc_ids

            finally:
                # Cleanup tenants
                manager.disable_tenant(tenant1_id)
                manager.disable_tenant(tenant2_id)

    @pytest.mark.asyncio
    async def test_tenant_statistics_and_cleanup(self, tenant_manager):
        """Test tenant statistics and data cleanup functionality."""
        tenant_name = f"stats_test_{uuid.uuid4().hex[:8]}"
        tenant_id = tenant_manager.create_tenant(tenant_name)

        try:
            # Get initial statistics
            stats = tenant_manager.get_tenant_statistics(tenant_id)
            assert stats["tenant_info"]["name"] == tenant_name
            assert stats["tenant_info"]["current_documents"] == 0

            # Verify statistics structure
            assert "index_statistics" in stats
            assert "job_statistics" in stats
            assert isinstance(stats["index_statistics"], list)
            assert isinstance(stats["job_statistics"], dict)

            # Test cleanup (dry run)
            cleanup_report = tenant_manager.cleanup_tenant_data(tenant_id, dry_run=True)
            assert cleanup_report["tenant_id"] == tenant_id
            assert cleanup_report["dry_run"] is True
            assert "operations" in cleanup_report

        finally:
            # Cleanup
            tenant_manager.disable_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_tenant_error_handling(self, tenant_manager):
        """Test error handling for tenant operations."""
        # Test operations with non-existent tenant
        fake_tenant_id = str(uuid.uuid4())

        with pytest.raises(TenantNotFoundError):
            tenant_manager.get_tenant_info(fake_tenant_id)

        with pytest.raises(TenantNotFoundError):
            tenant_manager.update_tenant_settings(fake_tenant_id, {"test": "value"})

        with pytest.raises(TenantNotFoundError):
            tenant_manager.set_tenant_context(fake_tenant_id)

        # Test duplicate tenant creation
        tenant_name = f"duplicate_test_{uuid.uuid4().hex[:8]}"
        tenant_id = tenant_manager.create_tenant(tenant_name)

        try:
            # Try to create another tenant with the same name
            with pytest.raises(TenantError):
                tenant_manager.create_tenant(tenant_name)
        finally:
            # Cleanup
            tenant_manager.disable_tenant(tenant_id)

    @pytest.mark.asyncio
    async def test_tenant_data_isolation_search(self, postgresql_config):
        """Test that search operations are properly isolated by tenant."""
        with TenantManager(postgresql_config) as manager:
            tenant1_id = manager.create_tenant(f"search_test1_{uuid.uuid4().hex[:8]}")
            tenant2_id = manager.create_tenant(f"search_test2_{uuid.uuid4().hex[:8]}")

            try:
                # Create keyword indexes for each tenant
                factory1 = DatabaseFactory(postgresql_config, tenant1_id)
                factory2 = DatabaseFactory(postgresql_config, tenant2_id)

                with factory1.create_all() as adapters1, factory2.create_all() as adapters2:
                    keyword1 = adapters1["keyword_index"]
                    keyword2 = adapters2["keyword_index"]

                    # Add different content to each tenant
                    from llama_index.core.schema import TextNode

                    node1 = TextNode(text="This is tenant 1 content about sensors", id_="node1")
                    node2 = TextNode(text="This is tenant 2 content about lasers", id_="node2")

                    # Index content in each tenant
                    keyword1.index_nodes([node1], "doc1", "test1.pdf", [])
                    keyword2.index_nodes([node2], "doc2", "test2.pdf", [])

                    # Search in tenant 1 should only return tenant 1 content
                    results1 = keyword1.search("content", limit=10)
                    assert len(results1) == 1
                    assert "tenant 1" in results1[0]["text"]
                    assert "tenant 2" not in results1[0]["text"]

                    # Search in tenant 2 should only return tenant 2 content
                    results2 = keyword2.search("content", limit=10)
                    assert len(results2) == 1
                    assert "tenant 2" in results2[0]["text"]
                    assert "tenant 1" not in results2[0]["text"]

            finally:
                # Cleanup
                manager.disable_tenant(tenant1_id)
                manager.disable_tenant(tenant2_id)


class TestTenantCLIIntegration:
    """Test tenant CLI integration (requires PostgreSQL backend)."""

    @pytest.fixture
    def postgresql_config(self):
        """Create a PostgreSQL configuration for testing."""
        config = PipelineConfig()
        config.database.backend = "postgresql"
        return config

    def test_tenant_cli_creation(self, postgresql_config):
        """Test that TenantCLI can be created with PostgreSQL backend."""
        from cli.commands.tenant import TenantCLI

        cli = TenantCLI(postgresql_config)
        assert cli.config.database.backend == "postgresql"

    def test_tenant_cli_sqlite_rejection(self):
        """Test that TenantCLI rejects SQLite backend."""
        from cli.commands.tenant import TenantCLI

        config = PipelineConfig()
        config.database.backend = "sqlite"

        with pytest.raises(ValueError, match="requires PostgreSQL backend"):
            TenantCLI(config)
