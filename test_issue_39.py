#!/usr/bin/env python3
"""
Test script for Issue #39: IndexManager verification methods
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline_v3.core.index_manager import IndexManager
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.utils.config import PipelineConfig


async def test_verification_methods():
    """Test the new verification methods"""
    print("=== Testing Issue #39 IndexManager Methods ===\n")
    
    # Initialize components
    config = PipelineConfig()
    registry = DocumentRegistry(config)
    index_manager = IndexManager(config, registry=registry)
    
    # Get a document to test
    docs = registry.list_documents()
    if not docs:
        print("❌ No documents found in registry")
        return
        
    test_doc = docs[0]
    doc_id = test_doc.doc_id
    print(f"Testing with document: {doc_id}")
    print(f"Registry state: {test_doc.state}")
    print(f"Vector indexed: {getattr(test_doc, 'vector_indexed', 'N/A')}")
    print(f"Keyword indexed: {getattr(test_doc, 'keyword_indexed', 'N/A')}")
    
    # Test verify_vector_index_state
    print("\n1. Testing verify_vector_index_state...")
    vector_state = await index_manager.verify_vector_index_state(doc_id)
    print(f"   Result: {vector_state}")
    
    # Test verify_keyword_index_state
    print("\n2. Testing verify_keyword_index_state...")
    keyword_state = await index_manager.verify_keyword_index_state(doc_id)
    print(f"   Result: {keyword_state}")
    
    # Test with non-existent document
    print("\n3. Testing with non-existent document...")
    fake_id = "non-existent-doc-id"
    vector_state = await index_manager.verify_vector_index_state(fake_id)
    keyword_state = await index_manager.verify_keyword_index_state(fake_id)
    print(f"   Vector state: {vector_state}")
    print(f"   Keyword state: {keyword_state}")
    
    # Test delete methods if document exists in indexes
    if vector_state.get("exists"):
        print("\n4. Testing delete_from_vector_index...")
        success = await index_manager.delete_from_vector_index(fake_id)
        print(f"   Delete result: {success}")
        
    print("\n✅ Test complete!")


if __name__ == "__main__":
    asyncio.run(test_verification_methods())