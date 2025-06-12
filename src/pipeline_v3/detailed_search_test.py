#!/usr/bin/env python3
"""
Detailed Search Test for Pipeline v3

Shows detailed search results including content chunks returned.
"""

import asyncio
import time
from pathlib import Path
import sys
import tempfile
import shutil
from typing import List, Dict, Any

# Add parent directory for imports  
sys.path.insert(0, str(Path(__file__).parent))

try:
    from pipeline.enhanced_core import EnhancedPipeline
    from utils.config import PipelineConfig
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some imports failed: {e}")
    IMPORTS_AVAILABLE = False


async def run_detailed_search_test():
    """Run detailed search test to show actual search results."""
    print("🔍 Detailed Search Results Test")
    print("="*60)
    
    test_docs_path = Path("/Users/seanbergman/Repositories/rag_lab/data/lmc_docs")
    temp_dir = Path(tempfile.mkdtemp(prefix="pipeline_v3_search_test_"))
    
    try:
        # Setup configuration
        config = PipelineConfig()
        config.storage.base_dir = str(temp_dir / 'storage_data')
        config.storage.keyword_db_path = str(temp_dir / 'keyword_index.db')
        config.storage.document_registry_path = str(temp_dir / 'registry.db')
        config.cache.directory = str(temp_dir / 'cache')
        config.qdrant.path = str(temp_dir / 'qdrant_data')
        config.job_queue.max_concurrent = 1
        config.job_queue.job_storage_path = str(temp_dir / 'jobs.db')
        config.fingerprint.storage_path = str(temp_dir / 'fingerprints.db')
        config.chunking.chunk_size = 256
        config.chunking.chunk_overlap = 25
        
        # Helper methods for compatibility
        def get_config_value(key, default=None):
            parts = key.split('.')
            if len(parts) == 2:
                section, attr = parts
                if hasattr(config, section):
                    section_obj = getattr(config, section)
                    return getattr(section_obj, attr, default)
            return default
        
        def get_storage_config():
            return {
                'jobs_db_path': config.job_queue.job_storage_path,
                'registry_db_path': config.storage.document_registry_path,
                'keyword_db_path': config.storage.keyword_db_path,
                'base_dir': config.storage.base_dir
            }
        
        config.get = get_config_value
        config.storage_config = get_storage_config()
        
        # Initialize pipeline
        pipeline = EnhancedPipeline(config)
        print("✅ Pipeline initialized")
        
        # Get test documents
        main_pdfs = [f for f in test_docs_path.glob("*.pdf") if not f.name.endswith("Zone.Identifier")]
        test_docs = main_pdfs[:2]  # Use first 2 documents
        
        print(f"\n📄 Processing documents:")
        for doc in test_docs:
            print(f"   - {doc.name}")
        
        # Process documents
        for doc_path in test_docs:
            print(f"\n  Processing: {doc_path.name}")
            result = await pipeline.process_document(
                str(doc_path),
                metadata={'source': 'search_test', 'document_type': 'datasheet'}
            )
            print(f"    Status: {result.get('status', 'unknown')}")
        
        # Test different search queries with detailed results
        search_queries = [
            "laser measurement",
            "sensor calibration", 
            "power detection",
            "optical",
            "USB interface"
        ]
        
        print(f"\n🔍 Testing Keyword Search with Detailed Results:")
        print("="*60)
        
        for i, query in enumerate(search_queries, 1):
            print(f"\n{i}. Search Query: '{query}'")
            print("-" * 40)
            
            try:
                start_time = time.time()
                results = pipeline.search(
                    query,
                    search_type='keyword',
                    top_k=5
                )
                search_time = time.time() - start_time
                
                print(f"   Results found: {len(results)} (in {search_time:.3f}s)")
                
                if results:
                    for j, result in enumerate(results, 1):
                        print(f"\n   Result {j}:")
                        print(f"     Source: {result.get('source', 'unknown')}")
                        print(f"     Score: {result.get('score', 0):.4f}")
                        
                        # Show content chunk
                        content = result.get('content', '')
                        if content:
                            # Truncate very long content for readability
                            display_content = content[:200] + "..." if len(content) > 200 else content
                            print(f"     Content: {display_content}")
                        
                        # Show metadata if available
                        metadata = result.get('metadata', {})
                        if metadata:
                            print(f"     Metadata: {metadata}")
                        
                        print()  # Empty line between results
                else:
                    print("   No results found")
                    
            except Exception as e:
                print(f"   ❌ Search failed: {e}")
        
        # Test a specific technical search to show domain relevance
        print(f"\n🎯 Technical Domain Search Example:")
        print("="*60)
        
        technical_query = "thermopile detector"
        print(f"Query: '{technical_query}'")
        print("-" * 40)
        
        try:
            results = pipeline.search(technical_query, search_type='keyword', top_k=3)
            
            if results:
                for i, result in enumerate(results, 1):
                    print(f"\nResult {i}:")
                    print(f"  File: {Path(result.get('source', '')).name}")
                    print(f"  Score: {result.get('score', 0):.4f}")
                    
                    content = result.get('content', '')
                    if content:
                        # Show more context for technical terms
                        print(f"  Context: {content[:300]}...")
            else:
                print("No results found for technical query")
                
        except Exception as e:
            print(f"❌ Technical search failed: {e}")
        
        print(f"\n" + "="*60)
        print("✅ Detailed search test completed!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        # Cleanup
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            print(f"🧹 Cleaned up test directory")


if __name__ == "__main__":
    if not IMPORTS_AVAILABLE:
        print("❌ Cannot run search test - required components not available")
        sys.exit(1)
    
    asyncio.run(run_detailed_search_test())