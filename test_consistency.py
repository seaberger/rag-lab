#!/usr/bin/env python3
"""
Test script for Issue #27: Cross-System Consistency
Demonstrates the consistency checker functionality
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline_v3.core.consistency_checker import ConsistencyChecker, RepairStrategy
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.fingerprint import FingerprintManager
from src.pipeline_v3.utils.config import PipelineConfig


async def main():
    """Run consistency check demo"""
    print("=== Issue #27: Cross-System Consistency Demo ===\n")
    
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
        storage_dir="storage_data_v3"
    )
    
    print("1. Checking consistency across all storage systems...")
    report = await checker.check_all_documents(include_orphans=True)
    
    print(f"\n📊 Consistency Report:")
    print(f"   Total documents: {report.total_documents}")
    print(f"   Consistent: {report.consistent_documents}")
    print(f"   Inconsistent: {report.inconsistent_documents}")
    print(f"   Consistency rate: {report.consistency_rate:.1f}%")
    
    if report.inconsistencies:
        print(f"\n⚠️  Found {len(report.inconsistencies)} inconsistencies:")
        for inc in report.inconsistencies:
            print(f"\n   Document: {inc.doc_id}")
            print(f"   Issues: {[t.value for t in inc.types]}")
            print(f"   Missing from: {inc.missing_from}")
            print(f"   Present in: {inc.present_in}")
    else:
        print("\n✅ All documents are consistent across systems!")
    
    # Simulate an inconsistency
    print("\n\n2. Simulating an inconsistency...")
    print("   (Removing a document from vector index only)")
    
    # Get a document to corrupt
    docs = registry.list_documents()
    if docs:
        test_doc = docs[0]
        print(f"   Removing {test_doc.doc_id} from vector index...")
        
        # Remove from vector index only
        await index_manager.delete_from_vector_index(test_doc.doc_id)
        
        # Re-check consistency
        print("\n3. Re-checking consistency...")
        report2 = await checker.check_all_documents()
        
        print(f"\n📊 Updated Report:")
        print(f"   Inconsistent documents: {report2.inconsistent_documents}")
        
        if report2.inconsistencies:
            print("\n⚠️  Inconsistencies detected:")
            for inc in report2.inconsistencies:
                if inc.doc_id == test_doc.doc_id:
                    print(f"   Document {inc.doc_id} is missing from: {inc.missing_from}")
            
            # Demonstrate repair
            print("\n4. Attempting to repair using TRUST_REGISTRY strategy...")
            repair_results = await checker.repair_inconsistencies(
                report2,
                RepairStrategy.TRUST_REGISTRY,
                dry_run=False
            )
            
            for result in repair_results:
                if result.doc_id == test_doc.doc_id:
                    print(f"   Repair {'✅ successful' if result.success else '❌ failed'}")
                    print(f"   Actions: {result.actions_taken}")
            
            # Final check
            print("\n5. Final consistency check...")
            report3 = await checker.check_all_documents()
            print(f"   Consistency rate: {report3.consistency_rate:.1f}%")
    
    print("\n✨ Demo complete!")


if __name__ == "__main__":
    asyncio.run(main())