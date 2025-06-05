#!/usr/bin/env python3
"""
Test script to verify Pipeline v3 foundation is working.

This tests the basic components without full queue functionality.
"""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test that all basic imports work."""
    print("🧪 Testing imports...")
    
    try:
        from utils.config import PipelineConfig
        print("✅ PipelineConfig import successful")
    except ImportError as e:
        print(f"❌ PipelineConfig import failed: {e}")
        return False
    
    try:
        from utils.common_utils import logger
        print("✅ Logger import successful")
    except ImportError as e:
        print(f"❌ Logger import failed: {e}")
        return False
    
    try:
        from storage.keyword_index import BM25Index
        print("✅ BM25Index import successful")
    except ImportError as e:
        print(f"❌ BM25Index import failed: {e}")
        return False
    
    try:
        from core.parsers import DocumentClassifier
        print("✅ DocumentClassifier import successful")
    except ImportError as e:
        print(f"❌ DocumentClassifier import failed: {e}")
        return False
    
    return True


def test_configuration():
    """Test configuration loading."""
    print("\n🧪 Testing configuration...")
    
    try:
        from utils.config import PipelineConfig
        config = PipelineConfig.from_yaml("config.yaml")
        
        print("✅ Configuration loaded successfully")
        print(f"   Pipeline version: {getattr(config.pipeline, 'version', 'unknown')}")
        print(f"   Max concurrent: {config.pipeline.max_concurrent}")
        print(f"   Job queue enabled: {config.job_queue.job_persistence}")
        print(f"   Fingerprint enabled: {config.fingerprint.enabled}")
        
        return True
    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


def test_basic_functionality():
    """Test basic functionality without full processing."""
    print("\n🧪 Testing basic functionality...")
    
    try:
        from utils.config import PipelineConfig
        from storage.keyword_index import BM25Index
        from core.parsers import DocumentClassifier
        
        # Test configuration
        config = PipelineConfig.from_yaml("config.yaml")
        
        # Test BM25Index initialization
        bm25 = BM25Index(config=config)
        stats = bm25.get_stats()
        print(f"✅ BM25Index initialized - {stats['total_documents']} documents")
        
        # Test document classifier
        classifier = DocumentClassifier()
        doc_type = classifier.classify("test.pdf", True)
        print(f"✅ DocumentClassifier working - classified test.pdf as {doc_type.value}")
        
        return True
    except Exception as e:
        print(f"❌ Basic functionality test failed: {e}")
        return False


def main():
    """Run all foundation tests."""
    print("🚀 Pipeline v3 Foundation Tests")
    print("=" * 50)
    
    tests = [
        ("Imports", test_imports),
        ("Configuration", test_configuration),
        ("Basic Functionality", test_basic_functionality)
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        if test_func():
            passed += 1
        else:
            print(f"\n❌ {test_name} test failed")
    
    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All foundation tests passed! Pipeline v3 is ready for development.")
        return 0
    else:
        print("⚠️  Some tests failed. Check issues before proceeding.")
        return 1


if __name__ == "__main__":
    sys.exit(main())