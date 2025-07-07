#!/usr/bin/env python3
"""
Debug script to test tenant filtering in search engine
"""

import asyncio
import sys
from pathlib import Path

# Add the project root to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline_v3.core.index_manager_v2 import IndexManagerV2
from src.pipeline_v3.core.unified_query_engine import QueryRequest
from src.pipeline_v3.utils.config import PipelineConfig


async def test_tenant_filtering():
    """Test tenant filtering in the search engine."""
    print("🔍 Testing Tenant Filtering in Search Engine")
    print("=" * 60)

    # Load configuration
    config = PipelineConfig()
    print(f"📋 Backend: {config.database.backend}")
    print(f"📋 PostgreSQL enabled: {config.database.backend == 'postgresql'}")

    # Initialize index manager
    index_manager = IndexManagerV2(config)

    # Get the unified query engine
    query_engine = index_manager.query_engine

    print(f"📋 Query Engine Backend: {query_engine.backend}")
    print(f"📋 Query Engine is_postgresql: {query_engine.is_postgresql}")
    print(f"📋 Query Engine tenant_id: {query_engine.tenant_id}")

    # Test tenant filtering with different scenarios
    print("\n🧪 Testing Search with Different Tenant Scenarios")
    print("-" * 50)

    # Test 1: Search without tenant_id (but system will use default tenant)
    print("\n1. Search WITHOUT explicit tenant_id filter:")
    print(f"   • System will use default tenant: {query_engine.tenant_id}")
    request = QueryRequest(query="power sensor", top_k=5, search_type="vector")

    results = await query_engine.search(request)
    print(f"   • Found {len(results)} results")

    # Show tenant_ids in results
    tenant_ids = set()
    for result in results:
        tenant_id = result.metadata.get("tenant_id")
        if tenant_id:
            tenant_ids.add(tenant_id)

    print(f"   • Unique tenant_ids in results: {len(tenant_ids)}")
    for tid in list(tenant_ids)[:3]:  # Show first 3
        print(f"     - {tid}")

    # Let's also try searching without any tenant filtering to see what's available
    print("\n1b. Search WITHOUT any tenant filtering (bypass system defaults):")
    request_no_filter = QueryRequest(
        query="power sensor",
        top_k=5,
        search_type="vector",
        tenant_id=None,  # Explicitly set to None
    )

    # Temporarily disable PostgreSQL backend to skip tenant filtering
    original_backend = query_engine.backend
    original_is_postgresql = query_engine.is_postgresql

    query_engine.backend = "sqlite"
    query_engine.is_postgresql = False

    results_no_filter = await query_engine.search(request_no_filter)

    # Restore original settings
    query_engine.backend = original_backend
    query_engine.is_postgresql = original_is_postgresql

    print(f"   • Found {len(results_no_filter)} results without tenant filtering")

    # Get actual tenant IDs from the unfiltered results
    actual_tenant_ids = set()
    for result in results_no_filter:
        tenant_id = result.metadata.get("tenant_id")
        if tenant_id:
            actual_tenant_ids.add(tenant_id)

    print(f"   • Actual tenant_ids in database: {len(actual_tenant_ids)}")
    for tid in list(actual_tenant_ids)[:3]:  # Show first 3
        print(f"     - {tid}")

    # Use actual tenant IDs for further testing
    tenant_ids = actual_tenant_ids

    # Test 2: Search with specific tenant_id
    print("\n2. Search WITH tenant_id filter:")
    first_tenant = list(tenant_ids)[0] if tenant_ids else None

    if first_tenant:
        request = QueryRequest(
            query="power sensor", top_k=5, search_type="vector", tenant_id=first_tenant
        )

        results = await query_engine.search(request)
        print(f"   • Found {len(results)} results for tenant {first_tenant[:8]}...")

        # Verify all results are from the same tenant
        wrong_tenant_count = 0
        for result in results:
            result_tenant = result.metadata.get("tenant_id")
            if result_tenant != first_tenant:
                wrong_tenant_count += 1
                print(f"     ⚠️  Found result with wrong tenant: {result_tenant[:8]}...")

        if wrong_tenant_count == 0:
            print(f"     ✅ All results correctly filtered for tenant {first_tenant[:8]}...")
        else:
            print(f"     ❌ {wrong_tenant_count} results had wrong tenant!")
    else:
        print("   • No tenant_id found in results to test with")

    # Test 3: Debug the filter building process
    print("\n3. Debug Filter Building Process:")

    # Test with filters containing tenant_id
    test_filters = {"tenant_id": first_tenant} if first_tenant else {}

    print(f"   • Test filters: {test_filters}")
    print(f"   • is_postgresql: {query_engine.is_postgresql}")

    # Call the filter building method directly
    qdrant_filter = query_engine._build_qdrant_filter(test_filters)
    print(f"   • Generated Qdrant filter: {qdrant_filter}")

    if qdrant_filter:
        print(f"   • Filter conditions: {qdrant_filter.must}")
        for condition in qdrant_filter.must:
            print(f"     - Key: {condition.key}, Value: {condition.match}")

    # Test 4: Check configuration impact
    print("\n4. Configuration Impact Analysis:")
    print(f"   • Database backend: {config.database.backend}")
    print(f"   • PostgreSQL settings: {config.database.postgresql.default_tenant_id}")
    print(f"   • Backend detection: {query_engine.backend}")
    print(f"   • Tenant filtering enabled: {query_engine.is_postgresql}")

    # Test 5: Manual vector search with tenant filter
    print("\n5. Manual Vector Search with Tenant Filter:")

    if first_tenant and query_engine.qdrant_client:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Create manual filter
        manual_filter = Filter(
            must=[FieldCondition(key="metadata.tenant_id", match=MatchValue(value=first_tenant))]
        )

        print(f"   • Testing manual filter: {manual_filter}")

        # Get embedding
        embedding = await query_engine._get_embedding("power sensor")

        # Search with manual filter
        manual_results = query_engine.qdrant_client.search(
            collection_name=config.qdrant.collection_name,
            query_vector=embedding,
            limit=5,
            query_filter=manual_filter,
            with_payload=True,
        )

        print(f"   • Manual search found {len(manual_results)} results")

        # Check if all results have correct tenant
        manual_wrong_count = 0
        for result in manual_results:
            result_tenant = result.payload.get("metadata", {}).get("tenant_id")
            if result_tenant != first_tenant:
                manual_wrong_count += 1

        if manual_wrong_count == 0:
            print("   ✅ Manual search correctly filtered by tenant")
        else:
            print(f"   ❌ Manual search had {manual_wrong_count} wrong tenants")


if __name__ == "__main__":
    asyncio.run(test_tenant_filtering())
