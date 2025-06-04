#!/usr/bin/env python3
"""
Test the simplified pipeline.
"""

import asyncio
import sys
from pathlib import Path

# Import our simplified pipeline
from simple_pipeline import setup_environment, process_document


async def test_simple_pipeline():
    """Test the simplified pipeline."""
    
    print("🧪 Testing Simplified Pipeline")
    print("=" * 50)
    
    # Setup environment
    print("🔧 Setting up environment...")
    if not setup_environment():
        print("❌ Environment setup failed")
        return False
    
    # Test document path
    doc_path = Path("../../../data/sample_docs/pm10k-plus-ds.pdf")
    
    if not doc_path.exists():
        print(f"❌ Test document not found: {doc_path}")
        print("Note: This test expects the PM10K+ datasheet at the relative path above")
        return False
    
    print(f"📄 Testing with: {doc_path}")
    
    try:
        # Process the document
        print("🚀 Processing document...")
        artifact = await process_document(
            doc_path=doc_path,
            output_path=Path("test_output.json"),
            is_datasheet_mode=True
        )
        
        # Display results
        print("\n🎉 Processing successful!")
        print(f"📄 Document: {doc_path.name}")
        print(f"📋 Type: {artifact['metadata']['source_type']}")
        print(f"🔢 Pairs extracted: {len(artifact['pairs'])}")
        print(f"📝 Content length: {len(artifact['markdown']):,} chars")
        
        if artifact['pairs']:
            print("\n📋 Extracted model/part pairs:")
            for model, part in artifact['pairs']:
                print(f"   • {model}: {part}")
        
        # Show sample content
        print(f"\n📝 Sample content:")
        sample = artifact['markdown'][:300] + "..." if len(artifact['markdown']) > 300 else artifact['markdown']
        print("-" * 40)
        print(sample)
        print("-" * 40)
        
        return True
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_simple_pipeline())
    sys.exit(0 if success else 1)