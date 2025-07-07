#!/usr/bin/env python3
"""
Debug script to inspect Qdrant vector database contents
"""

import json
import sys
from pathlib import Path

# Add the project root to path so we can import modules
sys.path.insert(0, str(Path(__file__).parent))

import qdrant_client
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.pipeline_v3.utils.config import PipelineConfig


def inspect_qdrant_collection():
    """Inspect the Qdrant collection to understand tenant isolation issues."""

    print("🔍 Inspecting Qdrant Collection")
    print("=" * 50)

    # Load configuration
    config = PipelineConfig()

    # Initialize Qdrant client
    if config.qdrant.mode == "server":
        client = qdrant_client.QdrantClient(
            host=config.qdrant.server.host,
            port=config.qdrant.server.port,
        )
        print(
            f"📡 Connected to Qdrant server at {config.qdrant.server.host}:{config.qdrant.server.port}"
        )
    else:
        client = qdrant_client.QdrantClient(path=config.qdrant.path)
        print(f"📂 Connected to local Qdrant at {config.qdrant.path}")

    collection_name = config.qdrant.collection_name
    print(f"🗂️  Collection: {collection_name}")
    print()

    try:
        # Get collection info
        collection_info = client.get_collection(collection_name)
        print("📊 Collection Statistics:")
        print(f"   • Total points: {collection_info.points_count}")
        print(f"   • Total vectors: {collection_info.vectors_count}")
        print(
            f"   • Indexed vectors: {getattr(collection_info, 'indexed_vectors_count', 'unknown')}"
        )
        print()

        # Get all points with their payloads
        print("🔍 Retrieving all points...")

        # Scroll through all points
        all_points = []
        offset = None

        while True:
            result = client.scroll(
                collection_name=collection_name,
                limit=100,
                offset=offset,
                with_payload=True,
                with_vectors=False,  # We don't need the vectors for this analysis
            )

            points, next_offset = result
            all_points.extend(points)

            if next_offset is None:
                break
            offset = next_offset

        print(f"📋 Found {len(all_points)} total points")
        print()

        # Analyze points by tenant_id
        tenant_counts = {}
        doc_id_counts = {}
        points_without_tenant = []
        tenant_doc_mapping = {}  # Track which docs belong to which tenants

        for point in all_points:
            payload = point.payload

            # Check for tenant_id in metadata
            metadata = payload.get("metadata", {})
            tenant_id = metadata.get("tenant_id")
            doc_id = payload.get("doc_id", "unknown")
            source = metadata.get("source", "unknown")

            # Count by tenant
            if tenant_id:
                tenant_counts[tenant_id] = tenant_counts.get(tenant_id, 0) + 1

                # Track tenant-doc mapping
                if tenant_id not in tenant_doc_mapping:
                    tenant_doc_mapping[tenant_id] = {}
                if doc_id not in tenant_doc_mapping[tenant_id]:
                    tenant_doc_mapping[tenant_id][doc_id] = {"source": source, "count": 0}
                tenant_doc_mapping[tenant_id][doc_id]["count"] += 1
            else:
                points_without_tenant.append(
                    {"id": point.id, "doc_id": doc_id, "metadata": metadata}
                )

            # Count by doc_id
            doc_id_counts[doc_id] = doc_id_counts.get(doc_id, 0) + 1

        # Report findings
        print("🏢 Points by Tenant ID:")
        if tenant_counts:
            for tenant_id, count in tenant_counts.items():
                print(f"   • {tenant_id}: {count} points")
        else:
            print("   • No points found with tenant_id!")
        print()

        print("📄 Points by Document ID:")
        for doc_id, count in doc_id_counts.items():
            print(f"   • {doc_id}: {count} points")
        print()

        print("🔗 Tenant-Document Mapping:")
        for tenant_id, docs in tenant_doc_mapping.items():
            print(f"   • Tenant {tenant_id}:")
            for doc_id, info in docs.items():
                print(f"     - Document {doc_id[:8]}... ({info['count']} points)")
                print(f"       Source: {info['source']}")
        print()

        if points_without_tenant:
            print(f"⚠️  Found {len(points_without_tenant)} points WITHOUT tenant_id:")
            for point in points_without_tenant[:5]:  # Show first 5
                print(f"   • ID: {point['id']}")
                print(f"     Doc ID: {point['doc_id']}")
                print(f"     Metadata: {json.dumps(point['metadata'], indent=6)}")

            if len(points_without_tenant) > 5:
                print(f"   ... and {len(points_without_tenant) - 5} more")
            print()

        # Test tenant filtering
        print("🔍 Testing Tenant Filtering...")

        # Test search with tenant filter for each tenant
        for tenant_id in tenant_counts:
            print(f"\n   Testing search for tenant '{tenant_id[:8]}...':")

            # Search with tenant filter
            search_results = client.search(
                collection_name=collection_name,
                query_vector=[0.0] * config.openai.dimensions,  # Dummy vector
                query_filter=Filter(
                    must=[
                        FieldCondition(key="metadata.tenant_id", match=MatchValue(value=tenant_id))
                    ]
                ),
                limit=10,
                with_payload=True,
            )

            print(f"     • Found {len(search_results)} results")

            # Check if results are properly filtered
            wrong_tenant_count = 0
            for result in search_results:
                result_tenant = result.payload.get("metadata", {}).get("tenant_id")
                if result_tenant != tenant_id:
                    wrong_tenant_count += 1
                    print(f"     ⚠️  Found result with wrong tenant: {result_tenant[:8]}...")

            if wrong_tenant_count == 0:
                print("     ✅ All results correctly filtered for this tenant")
            else:
                print(f"     ❌ {wrong_tenant_count} results had wrong tenant!")

        # Test search without tenant filter
        print("\n   Testing search WITHOUT tenant filter:")
        search_results = client.search(
            collection_name=collection_name,
            query_vector=[0.0] * config.openai.dimensions,  # Dummy vector
            limit=10,
            with_payload=True,
        )
        print(f"     • Found {len(search_results)} results")

        # Show which tenants are represented in unfiltered results
        unfiltered_tenants = set()
        for result in search_results:
            result_tenant = result.payload.get("metadata", {}).get("tenant_id")
            if result_tenant:
                unfiltered_tenants.add(result_tenant)
        print(f"     • Tenants in unfiltered results: {len(unfiltered_tenants)} different tenants")

        # Test with a specific search query
        print("\n   Testing search with meaningful query 'power':")
        search_results = client.search(
            collection_name=collection_name,
            query_vector=[0.0] * config.openai.dimensions,  # Dummy vector
            limit=10,
            with_payload=True,
        )
        print(f"     • Found {len(search_results)} results without tenant filter")

        # Test same query with first tenant filter
        first_tenant = list(tenant_counts.keys())[0]
        search_results = client.search(
            collection_name=collection_name,
            query_vector=[0.0] * config.openai.dimensions,  # Dummy vector
            query_filter=Filter(
                must=[
                    FieldCondition(key="metadata.tenant_id", match=MatchValue(value=first_tenant))
                ]
            ),
            limit=10,
            with_payload=True,
        )
        print(
            f"     • Found {len(search_results)} results with tenant filter for {first_tenant[:8]}..."
        )

        # Show sample point structure
        if all_points:
            print("\n📋 Sample Point Structure:")
            sample_point = all_points[0]
            print(f"   • ID: {sample_point.id}")
            print(f"   • Payload keys: {list(sample_point.payload.keys())}")
            print(
                f"   • Metadata: {json.dumps(sample_point.payload.get('metadata', {}), indent=6)}"
            )

        # Show all unique tenant_ids found
        print(f"\n🔑 All unique tenant_ids found: {list(tenant_counts.keys())}")

    except Exception as e:
        print(f"❌ Error inspecting collection: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    inspect_qdrant_collection()
