#!/usr/bin/env python3
"""
Real Document Search Test for Pipeline v3

Tests search functionality using only real LMC documents to diagnose PDF processing.
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


async def test_real_document_processing():
    """Test processing of real LMC documents."""
    print("📄 Real LMC Document Processing Test")
    print("="*60)
    
    lmc_docs_path = Path("/Users/seanbergman/Repositories/rag_lab/data/lmc_docs")
    temp_dir = Path(tempfile.mkdtemp(prefix="pipeline_v3_real_test_"))
    
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
        config.chunking.chunk_size = 512  # Reasonable chunk size
        config.chunking.chunk_overlap = 50
        
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
        
        # Select specific real LMC documents for testing
        selected_docs = [
            lmc_docs_path / "Thermopile-User-Guide.pdf",
            lmc_docs_path / "datasheets" / "COHR_PowerMax-USB_UV-VIS_DS_0920_2.pdf"
        ]
        
        # Filter to only existing files
        existing_docs = [doc for doc in selected_docs if doc.exists()]
        
        if not existing_docs:
            print("❌ No test documents found")
            return
        
        print(f"\n📄 Processing {len(existing_docs)} real LMC documents:")
        for doc in existing_docs:
            print(f"   - {doc.name}")
        
        processed_docs = []
        
        # Process each document
        for doc_path in existing_docs:
            print(f"\n  📖 Processing: {doc_path.name}")
            start_time = time.time()
            
            try:
                # Process document (let the pipeline handle PDF parsing)
                result = await pipeline.process_document(
                    str(doc_path),
                    metadata={
                        'source': 'real_lmc_test',
                        'document_type': 'technical_document',
                        'filename': doc_path.name
                    }
                )
                
                processing_time = time.time() - start_time
                print(f"     Status: {result.get('status', 'unknown')}")
                print(f"     Time: {processing_time:.2f}s")
                
                if result.get('status') == 'success':
                    processed_docs.append(doc_path.name)
                    
                    # Try to get some info about what was indexed
                    doc_id = result.get('doc_id')
                    if doc_id:
                        print(f"     Doc ID: {doc_id}")
                
            except Exception as e:
                print(f"     ❌ Error: {e}")
        
        if not processed_docs:
            print("\n❌ No documents were successfully processed")
            return
        
        print(f"\n✅ Successfully processed {len(processed_docs)} documents")
        
        # Wait a moment for indexing to complete
        await asyncio.sleep(1)
        
        # Test searches with terms relevant to LMC documents
        lmc_search_queries = [
            "thermopile",
            "laser power",
            "sensor",
            "measurement", 
            "PowerMax",
            "wavelength",
            "detector",
            "calibration"
        ]
        
        print(f"\n🔍 Testing Search with Real LMC Content:")
        print("="*60)
        
        total_results = 0
        successful_searches = 0
        
        for i, query in enumerate(lmc_search_queries, 1):
            print(f"\n{i}. Query: '{query}'")
            print("-" * 40)
            
            try:
                start_time = time.time()
                results = pipeline.search(
                    query,
                    search_type='keyword',
                    top_k=3
                )
                search_time = time.time() - start_time
                
                print(f"   Results: {len(results)} found (in {search_time:.3f}s)")
                total_results += len(results)
                
                if len(results) > 0:
                    successful_searches += 1
                    
                    # Show first result details
                    if results:
                        first_result = results[0]
                        
                        # Handle both dict and string results
                        if isinstance(first_result, dict):
                            score = first_result.get('score', 'N/A')
                            content = first_result.get('content', '')
                            source = first_result.get('source', 'unknown')
                            
                            print(f"   Top result score: {score}")
                            
                            if content and isinstance(content, str):
                                # Show a snippet of the content
                                content_preview = content.strip()[:150]
                                if content_preview:
                                    print(f"   Content preview: {content_preview}...")
                                else:
                                    print(f"   Content: [Empty or non-text content]")
                            
                            # Show source info
                            if isinstance(source, str) and source != 'unknown':
                                source_file = Path(source).name if '/' in source else source
                                print(f"   Source: {source_file}")
                        else:
                            print(f"   Result format: {type(first_result)}")
                else:
                    print("   No results found")
                    
            except Exception as e:
                print(f"   ❌ Search error: {e}")
        
        # Summary
        print(f"\n" + "="*60)
        print("📊 Real Document Search Test Summary:")
        print(f"   Documents processed: {len(processed_docs)}")
        print(f"   Successful searches: {successful_searches}/{len(lmc_search_queries)}")
        print(f"   Total results found: {total_results}")
        
        if successful_searches > 0:
            print("✅ Search functionality working with real LMC documents!")
        else:
            print("⚠️ Search found no results - may indicate PDF processing issues")
        
        # Test registry statistics
        print(f"\n📈 Registry Statistics:")
        try:
            stats = pipeline.registry.get_statistics()
            print(f"   Total documents in registry: {stats.get('total_documents', 0)}")
            print(f"   Registry status: ✅ Working")
        except Exception as e:
            print(f"   Registry status: ❌ Error - {e}")
        
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
        print("❌ Cannot run test - required components not available")
        sys.exit(1)
    
    asyncio.run(test_real_document_processing())