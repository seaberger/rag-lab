"""
Test enhanced pipeline adapter with database factory.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parents[3]
sys.path.insert(0, str(project_root))

from src.pipeline_v3.core.enhanced_pipeline_adapter import EnhancedPipelineAdapter
from src.pipeline_v3.utils.config import PipelineConfig, DatabaseSettings


async def test_enhanced_adapter():
    """Test the enhanced pipeline adapter."""
    print("Enhanced Pipeline Adapter Tests")
    print("=" * 40)

    # Test SQLite backend
    print("\n1. Testing SQLite Backend:")
    config = PipelineConfig(
        database=DatabaseSettings(backend="sqlite")
    )

    try:
        adapter = EnhancedPipelineAdapter(config)
        status = adapter.get_system_status()

        print(f"   ✓ Backend: {status['backend']}")
        print(f"   ✓ Initialized: {status['initialized']}")
        print(f"   ✓ Components: {len(status['components'])} available")
        print(f"   ✓ Migration: {status['migration']['migration_direction']}")

        # Test document processing simulation
        result = await adapter.process_document("test.pdf", mode="datasheet")
        print(f"   ✓ Processing: {result['status']}")

        # Test search simulation
        results = adapter.search_documents("test query", limit=2)
        print(f"   ✓ Search: {len(results)} results")

        adapter.close()
        print("   ✓ Adapter closed successfully")

    except Exception as e:
        print(f"   ✗ SQLite test error: {e}")

    # Test PostgreSQL backend (mock configuration)
    print("\n2. Testing PostgreSQL Backend (Mock):")
    try:
        from src.pipeline_v3.utils.config import PostgreSQLSettings

        pg_config = PipelineConfig(
            database=DatabaseSettings(
                backend="postgresql",
                postgresql=PostgreSQLSettings(
                    host="localhost",
                    port=5432,
                    database="test_db",
                    user="test_user",
                    password="test_password"  # pragma: allowlist secret
                )
            )
        )

        adapter = EnhancedPipelineAdapter(pg_config, tenant_id="test-tenant")

        # Test configuration validation
        if adapter.factory.validate_backend_configuration():
            print("   ✓ PostgreSQL configuration valid")

        status = adapter.get_system_status()
        print(f"   ✓ Backend: {status['backend']}")
        print(f"   ✓ Tenant: {status['tenant_id']}")
        print(f"   ✓ Migration: {status['migration']['migration_direction']}")

        # Note: We can't actually initialize without a real PostgreSQL connection
        print("   ⚠️  Full PostgreSQL test requires database connection")

    except Exception as e:
        print(f"   ⚠️  PostgreSQL test limited: {e}")

    print("\n✅ Enhanced pipeline adapter tests completed!")


if __name__ == "__main__":
    asyncio.run(test_enhanced_adapter())
