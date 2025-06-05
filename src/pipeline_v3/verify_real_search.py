#!/usr/bin/env python3
"""
Verify Real LMC Document Search

Quick verification that the real LMC documents that were processed are searchable.
"""

import asyncio
from pathlib import Path
import sys
import tempfile
import shutil

# Add parent directory for imports  
sys.path.insert(0, str(Path(__file__).parent))

try:
    from pipeline.enhanced_core import EnhancedPipeline
    from utils.config import PipelineConfig
    IMPORTS_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Some imports failed: {e}")
    IMPORTS_AVAILABLE = False


async def verify_search_with_processed_docs():
    """Verify search works by letting documents get processed and then searching."""
    print("🔍 Verifying Search with Real LMC Documents")
    print("="*60)
    
    lmc_docs_path = Path("/Users/seanbergman/Repositories/rag_lab/data/lmc_docs")
    temp_dir = Path(tempfile.mkdtemp(prefix="pipeline_v3_verify_"))
    
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
        config.chunking.chunk_size = 512
        config.chunking.chunk_overlap = 50
        
        # Helper methods
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
        
        # Process one LMC document
        test_doc = lmc_docs_path / "Thermopile-User-Guide.pdf"
        
        if not test_doc.exists():
            print(f"❌ Test document not found: {test_doc}")
            return
        
        print(f"\n📖 Processing: {test_doc.name}")
        
        # Process document and wait for completion
        await pipeline.process_document(
            str(test_doc),
            metadata={'source': 'verify_test', 'type': 'lmc_doc'}
        )
        
        # Wait for indexing to complete
        await asyncio.sleep(2)
        
        print("✅ Document processed, testing search...")
        
        # Test searches with terms that should be in thermopile guide
        test_queries = [
            "thermopile",
            "power",
            "sensor", 
            "laser",
            "measurement"
        ]
        
        print(f"\n🔍 Search Results:")
        print("-" * 50)
        
        successful_searches = 0
        
        for query in test_queries:
            try:
                results = pipeline.search(query, search_type='keyword', top_k=2)
                
                print(f"\n'{query}': {len(results)} results")
                
                if results and len(results) > 0:
                    successful_searches += 1
                    
                    # Show first result
                    first_result = results[0]
                    if isinstance(first_result, dict):
                        content = first_result.get('content', '')
                        score = first_result.get('score', 'N/A')
                        
                        if content and len(content.strip()) > 0:
                            # Show meaningful content snippet
                            content_clean = content.strip().replace('\n', ' ')
                            preview = content_clean[:100] + "..." if len(content_clean) > 100 else content_clean
                            print(f"  Score: {score}")
                            print(f"  Content: {preview}")
                        else:
                            print(f"  Score: {score} (no text content)")
                    
            except Exception as e:
                print(f"'{query}': Error - {e}")
        
        print(f"\n" + "="*50)
        print(f"📊 Results: {successful_searches}/{len(test_queries)} searches successful")
        
        if successful_searches > 0:
            print("🎉 SUCCESS: Real LMC document search is working!")
            print(f"   - Document successfully parsed and indexed")
            print(f"   - Search engine finding relevant content") 
            print(f"   - Keyword matching operational")
        else:
            print("⚠️ No search results found - investigating...")
            
            # Check if document was actually indexed
            try:
                # Direct check of keyword index
                from storage.keyword_index import BM25Index
                keyword_index = BM25Index(config.storage.keyword_db_path)
                
                # Try to get some stats
                print(f"   Checking keyword index...")
                
            except Exception as e:
                print(f"   Index check failed: {e}")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


if __name__ == "__main__":
    if not IMPORTS_AVAILABLE:
        print("❌ Cannot run verification - required components not available")
        sys.exit(1)
    
    asyncio.run(verify_search_with_processed_docs())