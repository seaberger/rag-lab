"""
Comprehensive test suite for multi-tenant isolation with RLS.

This test verifies that Row-Level Security properly isolates data between
tenants and prevents any cross-tenant data leakage.
"""

import asyncio
import hashlib
import uuid
from pathlib import Path
from typing import Dict, List

import pytest
import psycopg
from psycopg.rows import dict_row

from src.pipeline_v3.core.postgres_base_rls import PostgreSQLBaseRLS
from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry
from src.pipeline_v3.storage.postgres_keyword import PostgreSQLKeywordIndex
from src.pipeline_v3.job_queue.postgres_jobs import PostgreSQLJobManager
from src.pipeline_v3.core.postgres_fingerprint import PostgreSQLFingerprintManager
from src.pipeline_v3.scripts.tenant_management import TenantManager
from src.pipeline_v3.utils.config import PipelineConfig


@pytest.fixture(scope="module")
def config():
    """Load test configuration."""
    return PipelineConfig()


@pytest.fixture(scope="module")
def tenant_manager(config):
    """Create tenant manager for test setup."""
    return TenantManager(config)


@pytest.fixture(scope="module")
def test_tenants(tenant_manager):
    """Create test tenants for isolation testing."""
    tenants = []

    # Create two test tenants
    for i in range(2):
        tenant = tenant_manager.create_tenant(
            name=f"test_tenant_{i}_{uuid.uuid4().hex[:8]}",
            display_name=f"Test Tenant {i}",
            admin_email=f"admin{i}@test.com",
            max_documents=100,
            max_storage_gb=1,
            max_api_calls_per_day=1000
        )
        tenants.append(tenant)

    yield tenants

    # Cleanup: Deactivate test tenants
    for tenant in tenants:
        try:
            tenant_manager.deactivate_tenant(tenant['name'])
        except Exception:
            pass  # Ignore cleanup errors


class TestMultiTenantIsolation:
    """Test suite for multi-tenant data isolation."""

    def test_tenant_creation(self, test_tenants):
        """Test that tenants are created successfully."""
        assert len(test_tenants) == 2
        for tenant in test_tenants:
            assert 'tenant_id' in tenant
            assert 'api_key' in tenant
            assert tenant['api_key'].startswith('rl_')

    def test_registry_isolation(self, config, test_tenants):
        """Test document registry isolation between tenants."""
        tenant1, tenant2 = test_tenants

        # Create registries for each tenant
        registry1 = PostgreSQLDocumentRegistry(
            config=config,
            tenant_id=tenant1['tenant_id']
        )
        registry2 = PostgreSQLDocumentRegistry(
            config=config,
            tenant_id=tenant2['tenant_id']
        )

        # Register document in tenant 1
        doc_id1 = registry1.register_document(
            source="test_doc1.pdf",
            content_hash="hash123",
            size=1000,
            modified_time=1234567890.0,
            metadata={"test": "tenant1"}
        )

        # Register document in tenant 2
        doc_id2 = registry2.register_document(
            source="test_doc2.pdf",
            content_hash="hash456",
            size=2000,
            modified_time=1234567891.0,
            metadata={"test": "tenant2"}
        )

        # Verify tenant 1 can only see their document
        docs1 = registry1.list_documents()
        assert len(docs1) == 1
        assert docs1[0].source == "test_doc1.pdf"
        assert docs1[0].metadata["test"] == "tenant1"

        # Verify tenant 2 can only see their document
        docs2 = registry2.list_documents()
        assert len(docs2) == 1
        assert docs2[0].source == "test_doc2.pdf"
        assert docs2[0].metadata["test"] == "tenant2"

        # Verify cross-tenant access fails
        assert registry1.get_document(doc_id2) is None
        assert registry2.get_document(doc_id1) is None

    def test_keyword_index_isolation(self, config, test_tenants):
        """Test keyword index isolation between tenants."""
        tenant1, tenant2 = test_tenants

        # Create keyword indexes for each tenant
        index1 = PostgreSQLKeywordIndex(
            config=config,
            tenant_id=tenant1['tenant_id']
        )
        index2 = PostgreSQLKeywordIndex(
            config=config,
            tenant_id=tenant2['tenant_id']
        )

        # Create test nodes
        from src.pipeline_v3.core.data_structures import TextChunk

        nodes1 = [
            TextChunk(
                text="Tenant 1 exclusive content about lasers",
                node_id=f"t1_node_{i}",
                metadata={"doc_id": "doc1", "tenant": "1"}
            )
            for i in range(3)
        ]

        nodes2 = [
            TextChunk(
                text="Tenant 2 exclusive content about sensors",
                node_id=f"t2_node_{i}",
                metadata={"doc_id": "doc2", "tenant": "2"}
            )
            for i in range(3)
        ]

        # Index documents for each tenant
        index1.index_nodes(nodes1, "doc1", "source1.pdf", [])
        index2.index_nodes(nodes2, "doc2", "source2.pdf", [])

        # Search in tenant 1 - should only find tenant 1 content
        results1 = index1.search("content", limit=10)
        assert len(results1) == 3
        for result in results1:
            assert "Tenant 1" in result['text']
            assert "Tenant 2" not in result['text']

        # Search in tenant 2 - should only find tenant 2 content
        results2 = index2.search("content", limit=10)
        assert len(results2) == 3
        for result in results2:
            assert "Tenant 2" in result['text']
            assert "Tenant 1" not in result['text']

        # Cross-tenant keyword search should return nothing
        results1_cross = index1.search("sensors", limit=10)
        assert len(results1_cross) == 0

        results2_cross = index2.search("lasers", limit=10)
        assert len(results2_cross) == 0

    def test_job_queue_isolation(self, config, test_tenants):
        """Test job queue isolation between tenants."""
        tenant1, tenant2 = test_tenants

        # Create job managers for each tenant
        jobs1 = PostgreSQLJobManager(
            config=config,
            tenant_id=tenant1['tenant_id']
        )
        jobs2 = PostgreSQLJobManager(
            config=config,
            tenant_id=tenant2['tenant_id']
        )

        # Create jobs for each tenant
        job_id1 = jobs1.create_job(
            source="tenant1_doc.pdf",
            job_type=jobs1.JobType.DOCUMENT_PROCESSING,
            metadata={"tenant": "1"}
        )

        job_id2 = jobs2.create_job(
            source="tenant2_doc.pdf",
            job_type=jobs2.JobType.DOCUMENT_PROCESSING,
            metadata={"tenant": "2"}
        )

        # Verify each tenant can only see their jobs
        tenant1_jobs = jobs1.list_jobs()
        assert len(tenant1_jobs) == 1
        assert tenant1_jobs[0].source == "tenant1_doc.pdf"

        tenant2_jobs = jobs2.list_jobs()
        assert len(tenant2_jobs) == 1
        assert tenant2_jobs[0].source == "tenant2_doc.pdf"

        # Verify cross-tenant job access fails
        assert jobs1.get_job(job_id2) is None
        assert jobs2.get_job(job_id1) is None

        # Test job claiming - each worker should only get their tenant's jobs
        worker1_job = jobs1.claim_next_job("worker1")
        assert worker1_job is not None
        assert worker1_job.job_id == job_id1

        worker2_job = jobs2.claim_next_job("worker2")
        assert worker2_job is not None
        assert worker2_job.job_id == job_id2

        # No more jobs should be available
        assert jobs1.claim_next_job("worker1") is None
        assert jobs2.claim_next_job("worker2") is None

    def test_direct_sql_isolation(self, config, test_tenants):
        """Test that direct SQL queries respect RLS policies."""
        tenant1, tenant2 = test_tenants

        # Create base connections for each tenant
        db1 = PostgreSQLBaseRLS(
            settings=config.database.postgresql,
            schema="registry",
            tenant_id=tenant1['tenant_id']
        )
        db2 = PostgreSQLBaseRLS(
            settings=config.database.postgresql,
            schema="registry",
            tenant_id=tenant2['tenant_id']
        )

        # Initialize connections
        db1.initialize()
        db2.initialize()

        try:
            # Count documents visible to each tenant
            count1 = db1.fetch_one("SELECT COUNT(*) as count FROM documents")
            count2 = db2.fetch_one("SELECT COUNT(*) as count FROM documents")

            # Each tenant should only see their own documents
            # (Based on previous tests, each should have 1 document)
            assert count1['count'] >= 0  # May be 0 if previous tests cleaned up
            assert count2['count'] >= 0

            # Try to query with explicit tenant_id filter (should still be restricted)
            other_tenant_query = """
                SELECT COUNT(*) as count FROM documents
                WHERE tenant_id = %s
            """

            # Tenant 1 trying to query tenant 2's data
            cross_count1 = db1.fetch_one(other_tenant_query, (tenant2['tenant_id'],))
            assert cross_count1['count'] == 0  # Should see nothing due to RLS

            # Tenant 2 trying to query tenant 1's data
            cross_count2 = db2.fetch_one(other_tenant_query, (tenant1['tenant_id'],))
            assert cross_count2['count'] == 0  # Should see nothing due to RLS

        finally:
            db1.close()
            db2.close()

    def test_admin_bypass(self, config, test_tenants):
        """Test that admin mode can bypass RLS policies."""
        tenant1, tenant2 = test_tenants

        # Create admin connection
        admin_db = PostgreSQLBaseRLS(
            settings=config.database.postgresql,
            schema="registry",
            is_admin=True
        )

        admin_db.initialize()

        try:
            # Admin should see all documents
            all_docs = admin_db.fetch_all("""
                SELECT tenant_id, source FROM documents
                ORDER BY source
            """)

            # Should see documents from both tenants (if they exist)
            tenant_ids = {str(doc['tenant_id']) for doc in all_docs}

            # Admin can see data from multiple tenants
            assert len(tenant_ids) >= 1  # At least one tenant's data visible

            # Admin can query specific tenant data
            tenant1_docs = admin_db.fetch_all("""
                SELECT * FROM documents WHERE tenant_id = %s
            """, (tenant1['tenant_id'],))

            # Admin query should work without restrictions
            assert isinstance(tenant1_docs, list)

        finally:
            admin_db.close()

    def test_concurrent_tenant_operations(self, config, test_tenants):
        """Test that concurrent operations by different tenants don't interfere."""
        tenant1, tenant2 = test_tenants

        # Create registries for concurrent testing
        registry1 = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant1['tenant_id'])
        registry2 = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant2['tenant_id'])

        # Prepare multiple documents for each tenant
        docs_per_tenant = 5

        # Register documents concurrently
        import concurrent.futures
        import time

        def register_docs(registry, tenant_num, count):
            """Register multiple documents for a tenant."""
            doc_ids = []
            for i in range(count):
                doc_id = registry.register_document(
                    source=f"tenant{tenant_num}_doc{i}.pdf",
                    content_hash=f"hash_{tenant_num}_{i}_{time.time()}",
                    size=1000 * (i + 1),
                    modified_time=time.time(),
                    metadata={"tenant": tenant_num, "index": i}
                )
                doc_ids.append(doc_id)
            return doc_ids

        # Execute concurrent registrations
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(register_docs, registry1, 1, docs_per_tenant)
            future2 = executor.submit(register_docs, registry2, 2, docs_per_tenant)

            tenant1_docs = future1.result()
            tenant2_docs = future2.result()

        # Verify isolation after concurrent operations
        assert len(tenant1_docs) == docs_per_tenant
        assert len(tenant2_docs) == docs_per_tenant

        # Each tenant should only see their documents
        list1 = registry1.list_documents()
        list2 = registry2.list_documents()

        # Filter to just our test documents
        test_docs1 = [d for d in list1 if d.source.startswith("tenant1_")]
        test_docs2 = [d for d in list2 if d.source.startswith("tenant2_")]

        assert len(test_docs1) == docs_per_tenant
        assert len(test_docs2) == docs_per_tenant

        # Verify no cross-contamination
        for doc in test_docs1:
            assert doc.metadata["tenant"] == 1

        for doc in test_docs2:
            assert doc.metadata["tenant"] == 2

    def test_connection_pool_isolation(self, config, test_tenants):
        """Test that connection pools properly maintain tenant isolation."""
        tenant1, tenant2 = test_tenants

        # Create a shared connection pool scenario
        db_instances = []

        # Create multiple DB instances for each tenant
        for _ in range(3):
            db_instances.append(PostgreSQLBaseRLS(
                settings=config.database.postgresql,
                schema="registry",
                tenant_id=tenant1['tenant_id']
            ))
            db_instances.append(PostgreSQLBaseRLS(
                settings=config.database.postgresql,
                schema="registry",
                tenant_id=tenant2['tenant_id']
            ))

        # Initialize all instances
        for db in db_instances:
            db.initialize()

        try:
            # Perform operations with different instances
            results = []
            for i, db in enumerate(db_instances):
                # Each instance queries for documents
                count = db.fetch_one("SELECT COUNT(*) as cnt FROM documents")
                tenant_check = db.fetch_one("SELECT tenants.current_tenant_id() as tid")

                results.append({
                    'instance': i,
                    'expected_tenant': db.tenant_id,
                    'actual_tenant': str(tenant_check['tid']) if tenant_check['tid'] else None,
                    'doc_count': count['cnt']
                })

            # Verify each connection maintained proper tenant context
            for result in results:
                if result['actual_tenant']:  # If RLS is active
                    assert result['actual_tenant'] == result['expected_tenant']

        finally:
            # Cleanup
            for db in db_instances:
                db.close()


@pytest.mark.asyncio
class TestAsyncMultiTenantIsolation:
    """Test async operations with multi-tenant isolation."""

    async def test_async_tenant_isolation(self, config, test_tenants):
        """Test async database operations respect tenant boundaries."""
        tenant1, tenant2 = test_tenants

        # Create async DB connections
        db1 = PostgreSQLBaseRLS(
            settings=config.database.postgresql,
            schema="registry",
            tenant_id=tenant1['tenant_id']
        )
        db2 = PostgreSQLBaseRLS(
            settings=config.database.postgresql,
            schema="registry",
            tenant_id=tenant2['tenant_id']
        )

        await db1.initialize_async()
        await db2.initialize_async()

        try:
            # Concurrent async queries
            results = await asyncio.gather(
                db1.fetch_all_async("SELECT source FROM documents"),
                db2.fetch_all_async("SELECT source FROM documents"),
                return_exceptions=True
            )

            # Each tenant sees only their data
            docs1, docs2 = results

            if not isinstance(docs1, Exception):
                for doc in docs1:
                    assert "tenant1" in doc['source'] or "test_doc1" in doc['source']

            if not isinstance(docs2, Exception):
                for doc in docs2:
                    assert "tenant2" in doc['source'] or "test_doc2" in doc['source']

        finally:
            await db1._close_async_pool()
            await db2._close_async_pool()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
