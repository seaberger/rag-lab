#!/usr/bin/env python3
"""
Quick Integration Test for Pipeline v3

Fast integration test focused on core functionality without heavy external API usage.
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


class QuickIntegrationTester:
    """Quick integration testing suite."""
    
    def __init__(self, test_docs_path: str):
        self.test_docs_path = Path(test_docs_path)
        self.temp_dir = None
        self.config = None
        self.pipeline = None
        self.test_results = {}
        
    async def setup_test_environment(self):
        """Set up isolated test environment."""
        print("🔧 Setting up test environment...")
        
        # Create temporary directory for test data
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pipeline_v3_quick_test_"))
        print(f"Test directory: {self.temp_dir}")
        
        # Initialize configuration with test-specific settings
        self.config = PipelineConfig()
        
        # Update storage paths for testing
        self.config.storage.base_dir = str(self.temp_dir / 'storage_data')
        self.config.storage.keyword_db_path = str(self.temp_dir / 'keyword_index.db')
        self.config.storage.document_registry_path = str(self.temp_dir / 'registry.db')
        
        # Update cache path
        self.config.cache.directory = str(self.temp_dir / 'cache')
        
        # Update Qdrant path
        self.config.qdrant.path = str(self.temp_dir / 'qdrant_data')
        
        # Update job queue settings
        self.config.job_queue.max_concurrent = 1  # Single threaded for testing
        self.config.job_queue.job_storage_path = str(self.temp_dir / 'jobs.db')
        
        # Update fingerprint settings
        self.config.fingerprint.storage_path = str(self.temp_dir / 'fingerprints.db')
        
        # Update chunking for faster testing
        self.config.chunking.chunk_size = 256  # Smaller chunks
        self.config.chunking.chunk_overlap = 25
        
        # Add helper methods for CLI compatibility
        def get_config_value(key, default=None):
            parts = key.split('.')
            if len(parts) == 2:
                section, attr = parts
                if hasattr(self.config, section):
                    section_obj = getattr(self.config, section)
                    return getattr(section_obj, attr, default)
            return default
        
        def get_storage_config():
            return {
                'jobs_db_path': self.config.job_queue.job_storage_path,
                'registry_db_path': self.config.storage.document_registry_path,
                'keyword_db_path': self.config.storage.keyword_db_path,
                'base_dir': self.config.storage.base_dir
            }
        
        # Monkey patch methods for CLI compatibility
        self.config.get = get_config_value
        self.config.storage_config = get_storage_config()
        
        # Initialize pipeline
        if IMPORTS_AVAILABLE:
            try:
                self.pipeline = EnhancedPipeline(self.config)
                print("✅ Pipeline initialized successfully")
                return True
            except Exception as e:
                print(f"❌ Pipeline initialization failed: {e}")
                return False
        else:
            print("❌ Required imports not available")
            return False
    
    async def cleanup_test_environment(self):
        """Clean up test environment."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)
            print(f"🧹 Cleaned up test directory: {self.temp_dir}")
    
    def get_test_documents(self) -> List[Path]:
        """Get list of test documents (limited for speed)."""
        if not self.test_docs_path.exists():
            print(f"❌ Test docs path not found: {self.test_docs_path}")
            return []
        
        # Get PDF files from main directory only for speed
        main_pdfs = [f for f in self.test_docs_path.glob("*.pdf") if not f.name.endswith("Zone.Identifier")]
        
        # Limit to first 2 files for quick testing
        selected_files = main_pdfs[:2]
        print(f"📄 Selected {len(selected_files)} files for quick testing:")
        for f in selected_files:
            print(f"   - {f.name}")
        
        return selected_files
    
    async def test_document_ingestion(self) -> bool:
        """Test document ingestion with real PDFs."""
        print("\n📥 Testing Document Ingestion...")
        
        test_docs = self.get_test_documents()
        if not test_docs:
            print("❌ No test documents found")
            return False
        
        ingestion_results = []
        
        for doc_path in test_docs:
            print(f"  Processing: {doc_path.name}")
            start_time = time.time()
            
            try:
                # Test document addition (focus on keyword indexing only for speed)
                result = await self.pipeline.process_document(
                    str(doc_path),
                    metadata={
                        'source': 'quick_integration_test',
                        'document_type': 'datasheet'
                    }
                )
                
                processing_time = time.time() - start_time
                
                ingestion_results.append({
                    'document': doc_path.name,
                    'success': True,
                    'processing_time': processing_time,
                    'result': result
                })
                
                print(f"    ✅ Success ({processing_time:.2f}s)")
                
            except Exception as e:
                processing_time = time.time() - start_time
                ingestion_results.append({
                    'document': doc_path.name,
                    'success': False,
                    'processing_time': processing_time,
                    'error': str(e)
                })
                print(f"    ❌ Failed: {e}")
        
        self.test_results['ingestion'] = ingestion_results
        
        success_count = sum(1 for r in ingestion_results if r['success'])
        total_count = len(ingestion_results)
        
        print(f"📊 Ingestion Results: {success_count}/{total_count} successful")
        return success_count > 0
    
    async def test_keyword_search(self) -> bool:
        """Test keyword search functionality only (faster than vector search)."""
        print("\n🔍 Testing Keyword Search...")
        
        search_queries = [
            "laser",
            "sensor", 
            "power",
            "measurement"
        ]
        
        search_results = []
        
        for query in search_queries:
            try:
                start_time = time.time()
                
                # Only test keyword search for speed
                results = self.pipeline.search(
                    query,
                    search_type='keyword',
                    top_k=3
                )
                
                search_time = time.time() - start_time
                
                search_results.append({
                    'query': query,
                    'success': True,
                    'results_count': len(results),
                    'search_time': search_time
                })
                
                print(f"    '{query}': {len(results)} results ({search_time:.2f}s)")
                
            except Exception as e:
                search_results.append({
                    'query': query,
                    'success': False,
                    'error': str(e)
                })
                print(f"    '{query}': ❌ Failed - {e}")
        
        self.test_results['search'] = search_results
        
        success_count = sum(1 for r in search_results if r['success'])
        total_count = len(search_results)
        print(f"📊 Keyword Search: {success_count}/{total_count} successful")
        
        return success_count > 0
    
    async def test_system_status(self) -> bool:
        """Test system status and monitoring."""
        print("\n📊 Testing System Status...")
        
        try:
            # Test pipeline status
            pipeline_status = self.pipeline.get_comprehensive_status()
            print(f"  Pipeline status: ✅ Retrieved")
            
            # Test registry statistics
            registry_stats = self.pipeline.registry.get_statistics()
            print(f"  Registry stats: ✅ Retrieved ({registry_stats.get('total_documents', 0)} docs)")
            
            # Test queue status
            queue_status = self.pipeline.document_queue.get_status()
            print(f"  Queue status: ✅ Retrieved")
            
            self.test_results['status'] = {
                'success': True,
                'pipeline_status': True,
                'registry_stats': True,
                'queue_status': True
            }
            
            return True
            
        except Exception as e:
            print(f"  ❌ Status test failed: {e}")
            self.test_results['status'] = {
                'success': False,
                'error': str(e)
            }
            return False
    
    def generate_test_report(self):
        """Generate quick test report."""
        print("\n" + "="*60)
        print("🧪 QUICK INTEGRATION TEST REPORT")
        print("="*60)
        
        total_tests = 0
        passed_tests = 0
        
        # Ingestion results
        if 'ingestion' in self.test_results:
            ingestion_results = self.test_results['ingestion']
            ingestion_success = sum(1 for r in ingestion_results if r['success'])
            total_tests += len(ingestion_results)
            passed_tests += ingestion_success
            print(f"📥 Document Ingestion: {ingestion_success}/{len(ingestion_results)} passed")
            
            if ingestion_results:
                avg_time = sum(r['processing_time'] for r in ingestion_results) / len(ingestion_results)
                print(f"   Average processing time: {avg_time:.2f}s")
        
        # Search results
        if 'search' in self.test_results:
            search_results = self.test_results['search']
            search_success = sum(1 for r in search_results if r['success'])
            total_tests += len(search_results)
            passed_tests += search_success
            print(f"🔍 Keyword Search: {search_success}/{len(search_results)} passed")
        
        # Status results
        if 'status' in self.test_results:
            status_result = self.test_results['status']
            total_tests += 1
            if status_result['success']:
                passed_tests += 1
                print("📊 System Status: 1/1 passed")
            else:
                print("📊 System Status: 0/1 passed")
        
        print(f"\n🎯 OVERALL RESULTS: {passed_tests}/{total_tests} tests passed ({passed_tests/total_tests*100:.1f}%)")
        
        if passed_tests == total_tests:
            print("🎉 ALL QUICK TESTS PASSED! Core pipeline functionality verified.")
            return True
        elif passed_tests / total_tests >= 0.8:
            print("⚠️ Most tests passed. Core functionality appears working.")
            return True
        else:
            print("❌ Multiple test failures. Pipeline needs review.")
            return False
    
    async def run_quick_test_suite(self):
        """Run the quick integration test suite."""
        print("🚀 Starting Pipeline v3 Quick Integration Tests")
        print("="*60)
        
        # Setup
        if not await self.setup_test_environment():
            print("❌ Failed to set up test environment")
            return False
        
        try:
            # Run core tests
            tests = [
                ("Document Ingestion", self.test_document_ingestion),
                ("Keyword Search", self.test_keyword_search),
                ("System Status", self.test_system_status),
            ]
            
            for test_name, test_func in tests:
                print(f"\n▶️ Running {test_name} tests...")
                try:
                    await test_func()
                except Exception as e:
                    print(f"❌ {test_name} test suite failed: {e}")
            
            # Generate report
            success = self.generate_test_report()
            
            return success
            
        finally:
            # Cleanup
            await self.cleanup_test_environment()


async def main():
    """Run quick integration tests."""
    test_docs_path = "/Users/seanbergman/Repositories/rag_lab/data/lmc_docs"
    
    tester = QuickIntegrationTester(test_docs_path)
    success = await tester.run_quick_test_suite()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    if not IMPORTS_AVAILABLE:
        print("❌ Cannot run integration tests - required components not available")
        sys.exit(1)
    
    asyncio.run(main())