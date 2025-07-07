#!/usr/bin/env python3
"""
Setup demo tenants for RAG Lab Pipeline v3

Creates three demo tenants: LMC, CellX, and Matrix
"""

import sys
from pathlib import Path

# Add pipeline_v3 to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from src.pipeline_v3.scripts.setup_rls import RLSSetup
from src.pipeline_v3.scripts.tenant_management import TenantManager
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


def setup_demo_tenants():
    """Create three demo tenants for testing multi-tenant functionality."""

    # Load configuration
    config = PipelineConfig()

    # First ensure RLS is set up
    logger.info("Checking RLS setup...")
    rls_setup = RLSSetup(config)

    if not rls_setup.verify_rls_enabled():
        logger.info("RLS not enabled, setting up now...")
        if not rls_setup.setup_rls():
            logger.error("Failed to set up RLS")
            return False

    # Create tenant manager
    manager = TenantManager(config)

    # Define demo tenants
    demo_tenants = [
        {
            "name": "lmc",
            "display_name": "Laser Measurement & Control",
            "admin_email": "admin@lmc.example.com",
            "admin_name": "LMC Administrator",
            "settings": {
                "industry": "laser_measurement",
                "features": ["datasheets", "technical_specs", "calibration"],
                "primary_use": "Technical documentation for laser measurement devices",
            },
            "max_documents": 50000,
            "max_storage_gb": 500,
            "max_api_calls_per_day": 1000000,
        },
        {
            "name": "cellx",
            "display_name": "CellX Biotechnology",
            "admin_email": "admin@cellx.example.com",
            "admin_name": "CellX Administrator",
            "settings": {
                "industry": "biotechnology",
                "features": ["research_papers", "lab_protocols", "clinical_data"],
                "primary_use": "Biotech research documentation and protocols",
            },
            "max_documents": 30000,
            "max_storage_gb": 300,
            "max_api_calls_per_day": 500000,
        },
        {
            "name": "matrix",
            "display_name": "Matrix Manufacturing",
            "admin_email": "admin@matrix.example.com",
            "admin_name": "Matrix Administrator",
            "settings": {
                "industry": "manufacturing",
                "features": ["specifications", "quality_reports", "compliance"],
                "primary_use": "Manufacturing specifications and quality documentation",
            },
            "max_documents": 40000,
            "max_storage_gb": 400,
            "max_api_calls_per_day": 750000,
        },
    ]

    created_tenants = []

    print("\n" + "=" * 60)
    print("CREATING DEMO TENANTS FOR RAG LAB")
    print("=" * 60)

    for tenant_config in demo_tenants:
        try:
            # Check if tenant already exists
            try:
                existing = manager.get_tenant_info(tenant_config["name"])
                logger.info(f"Tenant '{tenant_config['name']}' already exists, skipping...")
                print(f"\n✓ Tenant '{tenant_config['name']}' already exists")
                continue
            except ValueError:
                # Tenant doesn't exist, create it
                pass

            logger.info(f"Creating tenant: {tenant_config['name']}")

            result = manager.create_tenant(
                name=tenant_config["name"],
                display_name=tenant_config["display_name"],
                admin_email=tenant_config["admin_email"],
                admin_name=tenant_config["admin_name"],
                settings=tenant_config["settings"],
                max_documents=tenant_config["max_documents"],
                max_storage_gb=tenant_config["max_storage_gb"],
                max_api_calls_per_day=tenant_config["max_api_calls_per_day"],
            )

            created_tenants.append(result)

            print(f"\n✓ Created tenant: {tenant_config['display_name']}")
            print(f"  Name: {result['name']}")
            print(f"  ID: {result['tenant_id']}")
            print(f"  API Key: {result['api_key']}")

        except Exception as e:
            logger.error(f"Failed to create tenant {tenant_config['name']}: {e}")
            print(f"\n✗ Failed to create tenant {tenant_config['name']}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("DEMO TENANT SETUP COMPLETE")
    print("=" * 60)

    if created_tenants:
        print(f"\nCreated {len(created_tenants)} new tenants:")
        for tenant in created_tenants:
            print(f"  - {tenant['display_name']} ({tenant['name']})")

        print("\n⚠️  IMPORTANT: Save the API keys above securely!")
        print("    They cannot be retrieved later.")

        print("\n📝 Example usage:")
        print("    # Set tenant context in your code:")
        print("    registry = PostgreSQLDocumentRegistry(")
        print("        config=config,")
        print(f"        tenant_id='{created_tenants[0]['tenant_id']}'")
        print("    )")

        print("\n    # Or use API key for authentication:")
        print(f"    headers = {{'Authorization': 'Bearer {created_tenants[0]['api_key']}'}}")

    # List all tenants
    print("\n" + "-" * 60)
    print("ALL TENANTS IN SYSTEM:")
    print("-" * 60)

    all_tenants = manager.list_tenants()
    for tenant in all_tenants:
        status = "✓ Active" if tenant["is_active"] else "✗ Inactive"
        print(f"\n{tenant['display_name']} ({tenant['name']})")
        print(f"  Status: {status}")
        print(f"  Documents: {tenant['document_count']}")
        print(f"  API Keys: {tenant['api_key_count']}")
        print(f"  Created: {tenant['created_at']}")

    return True


def test_tenant_isolation():
    """Quick test to verify tenant isolation is working."""
    config = PipelineConfig()
    manager = TenantManager(config)

    print("\n" + "=" * 60)
    print("TESTING TENANT ISOLATION")
    print("=" * 60)

    # Get tenant IDs
    tenants = {}
    for name in ["lmc", "cellx", "matrix"]:
        try:
            info = manager.get_tenant_info(name)
            tenants[name] = info["tenant"]["tenant_id"]
        except Exception as e:
            print(f"✗ Could not find tenant '{name}': {e}")
            return None

    # Test document isolation
    from src.pipeline_v3.core.postgres_registry import PostgreSQLDocumentRegistry

    # Create test documents for each tenant
    test_results = []

    for tenant_name, tenant_id in tenants.items():
        registry = PostgreSQLDocumentRegistry(config=config, tenant_id=tenant_id)

        # Register a test document
        doc_id = registry.register_document(
            source=f"test_{tenant_name}_isolation.pdf",
            content_hash=f"test_hash_{tenant_name}",
            size=1000,
            modified_time=1234567890.0,
            metadata={"test": "isolation", "tenant": tenant_name},
        )

        # Verify can see own document
        own_docs = registry.list_documents()
        own_count = len([d for d in own_docs if d.source == f"test_{tenant_name}_isolation.pdf"])

        # Try to access other tenants' documents (should fail)
        cross_access = []
        for other_name, other_id in tenants.items():
            if other_name != tenant_name:
                other_docs = registry.list_documents()
                # Should NOT see other tenant's test documents
                other_count = len(
                    [d for d in other_docs if "test_" in d.source and tenant_name not in d.source]
                )
                if other_count > 0:
                    cross_access.append(other_name)

        test_results.append(
            {"tenant": tenant_name, "can_see_own": own_count == 1, "cross_access": cross_access}
        )

    # Print results
    print("\nIsolation Test Results:")
    all_passed = True

    for result in test_results:
        if result["can_see_own"] and not result["cross_access"]:
            print(f"  ✓ {result['tenant']}: Properly isolated")
        else:
            all_passed = False
            print(f"  ✗ {result['tenant']}: ISOLATION FAILURE")
            if not result["can_see_own"]:
                print("    - Cannot see own documents")
            if result["cross_access"]:
                print(f"    - Can see documents from: {', '.join(result['cross_access'])}")

    if all_passed:
        print("\n✓ All tenant isolation tests PASSED!")
    else:
        print("\n✗ Tenant isolation tests FAILED!")

    return all_passed


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Setup demo tenants for RAG Lab")
    parser.add_argument("--test-only", action="store_true", help="Only run isolation tests")

    args = parser.parse_args()

    try:
        if args.test_only:
            success = test_tenant_isolation()
        else:
            success = setup_demo_tenants()
            if success:
                print("\n\nRunning isolation tests...")
                test_tenant_isolation()

        sys.exit(0 if success else 1)

    except Exception as e:
        logger.error(f"Setup failed: {e}")
        print(f"\n✗ Setup failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
