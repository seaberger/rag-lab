#!/usr/bin/env python3
"""
Test script for Issue #27: Cross-System Consistency
Full test with document addition and consistency checking
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline_v3.core.consistency_checker import ConsistencyChecker, RepairStrategy
from src.pipeline_v3.core.fingerprint import FingerprintManager
from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.utils.config import PipelineConfig


async def check_system_state():
    """Check current state of all systems"""
    print("\n=== Current System State ===")

    config = PipelineConfig()
    registry = DocumentRegistry(config)

    # Check registry
    docs = registry.list_documents()
    print(f"\nRegistry: {len(docs)} documents")
    for doc in docs[:3]:  # Show first 3
        print(f"  - {doc.doc_id}: state={doc.state}")

    # Check storage
    storage_dir = Path("storage_data_v3")
    if storage_dir.exists():
        artifacts = list(storage_dir.glob("*.jsonl"))
        print(f"\nStorage artifacts: {len(artifacts)} files")
        for artifact in artifacts[:3]:
            print(f"  - {artifact.name}")

    # Check Qdrant
    from qdrant_client import QdrantClient

    client = QdrantClient(path="./qdrant_data_v3")
    try:
        info = client.get_collection("datasheets_v3")
        print(f"\nQdrant collection: {info.points_count} points")
    except:
        print("\nQdrant collection: Not found or empty")

    # Check keyword index
    import sqlite3

    conn = sqlite3.connect("keyword_index_v3.db")
    cursor = conn.execute("SELECT COUNT(*) FROM keyword_index")
    count = cursor.fetchone()[0]
    print(f"\nKeyword index: {count} documents")
    conn.close()


async def test_consistency_with_repair():
    """Test consistency checking and repair functionality"""
    print("\n=== Issue #27: Consistency Test with Repair ===\n")

    # Initialize components
    config = PipelineConfig()
    registry = DocumentRegistry(config)
    index_manager = IndexManager(config, registry=registry)
    fingerprint_manager = FingerprintManager(config)

    # Create consistency checker
    checker = ConsistencyChecker(
        registry=registry,
        index_manager=index_manager,
        fingerprint_manager=fingerprint_manager,
        storage_dir="storage_data_v3",
    )

    # First check
    print("1. Initial consistency check...")
    report = await checker.check_all_documents(include_orphans=True)

    print("\n📊 Initial Report:")
    print(f"   Total documents: {report.total_documents}")
    print(f"   Consistent: {report.consistent_documents}")
    print(f"   Inconsistent: {report.inconsistent_documents}")
    print(f"   Consistency rate: {report.consistency_rate:.1f}%")

    if report.inconsistencies:
        print(f"\n⚠️  Found {len(report.inconsistencies)} inconsistencies:")
        for inc in report.inconsistencies[:5]:  # Show first 5
            print(f"\n   Document: {inc.doc_id}")
            print(f"   Issues: {[t.value for t in inc.types]}")
            print(f"   Missing from: {inc.missing_from}")
            print(f"   Present in: {inc.present_in}")

    # If we have inconsistencies, try to repair
    if report.inconsistencies:
        print("\n2. Attempting repair with TRUST_REGISTRY strategy...")
        print(f"   Repairing {len(report.inconsistencies)} inconsistencies")

        # Repair in smaller batches to avoid issues
        batch_size = 5
        all_results = []

        for i in range(0, len(report.inconsistencies), batch_size):
            batch_inconsistencies = report.inconsistencies[i : i + batch_size]
            batch_report = ConsistencyReport(
                timestamp=report.timestamp,
                total_documents=len(batch_inconsistencies),
                consistent_documents=0,
                inconsistent_documents=len(batch_inconsistencies),
                inconsistencies=batch_inconsistencies,
                errors=[],
            )

            print(
                f"\n   Processing batch {i // batch_size + 1} ({len(batch_inconsistencies)} items)..."
            )
            repair_results = await checker.repair_inconsistencies(
                batch_report, RepairStrategy.TRUST_REGISTRY, dry_run=False
            )
            all_results.extend(repair_results)

            # Show results for this batch
            success_count = sum(1 for r in repair_results if r.success)
            print(f"   Batch results: {success_count}/{len(repair_results)} successful")

        # Summary
        total_success = sum(1 for r in all_results if r.success)
        print(f"\n   Total repair results: {total_success}/{len(all_results)} successful")

        # Show some failed repairs
        failed = [r for r in all_results if not r.success]
        if failed:
            print(f"\n   Failed repairs ({len(failed)} total):")
            for result in failed[:3]:
                print(f"   - {result.doc_id}: {result.errors}")

    # Final check
    print("\n3. Final consistency check...")
    final_report = await checker.check_all_documents()

    print("\n📊 Final Report:")
    print(f"   Total documents: {final_report.total_documents}")
    print(f"   Consistent: {final_report.consistent_documents}")
    print(f"   Inconsistent: {final_report.inconsistent_documents}")
    print(f"   Consistency rate: {final_report.consistency_rate:.1f}%")

    if final_report.consistency_rate < 100:
        print(f"\n⚠️  Still have {final_report.inconsistent_documents} inconsistent documents")
        print("   This may be due to:")
        print("   - Documents indexed with keywords but missing vector embeddings")
        print("   - Documents that need full reprocessing")
        print("   - Orphaned data that couldn't be repaired")


async def main():
    """Run all tests"""
    # Check current state
    await check_system_state()

    # Run consistency test
    await test_consistency_with_repair()

    print("\n✨ Test complete!")


if __name__ == "__main__":
    # Import the report class we need
    from src.pipeline_v3.core.consistency_checker import ConsistencyReport

    asyncio.run(main())
