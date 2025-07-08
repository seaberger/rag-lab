"""Test to verify LlamaIndex availability in CI environment."""

import pytest


def test_llama_index_imports():
    """Test that all required LlamaIndex imports work."""
    errors = []

    # Test each import individually
    try:
        import qdrant_client
        print("✓ qdrant_client imported successfully")
    except ImportError as e:
        errors.append(f"qdrant_client: {e}")

    try:
        from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
        print("✓ llama_index.core imports successful")
    except ImportError as e:
        errors.append(f"llama_index.core: {e}")

    try:
        from llama_index.core.node_parser import SentenceSplitter
        print("✓ SentenceSplitter imported successfully")
    except ImportError as e:
        errors.append(f"SentenceSplitter: {e}")

    try:
        from llama_index.core.schema import TextNode
        print("✓ TextNode imported successfully")
    except ImportError as e:
        errors.append(f"TextNode: {e}")

    try:
        from llama_index.core.vector_stores import VectorStoreQuery
        print("✓ VectorStoreQuery imported successfully")
    except ImportError as e:
        errors.append(f"VectorStoreQuery: {e}")

    try:
        from llama_index.embeddings.openai import OpenAIEmbedding
        print("✓ OpenAIEmbedding imported successfully")
    except ImportError as e:
        errors.append(f"OpenAIEmbedding: {e}")

    try:
        from llama_index.vector_stores.qdrant import QdrantVectorStore
        print("✓ QdrantVectorStore imported successfully")
    except ImportError as e:
        errors.append(f"QdrantVectorStore: {e}")

    # Check if we can access the flag from index_manager
    try:
        # Try with relative import
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        from core.index_manager import LLAMA_INDEX_AVAILABLE
        print(f"✓ LLAMA_INDEX_AVAILABLE = {LLAMA_INDEX_AVAILABLE}")
        if not LLAMA_INDEX_AVAILABLE:
            errors.append("LLAMA_INDEX_AVAILABLE is False!")
    except ImportError as e:
        errors.append(f"Could not import index_manager: {e}")

    # If there were any errors, fail the test with details
    if errors:
        pytest.fail("Import errors found:\n" + "\n".join(errors))
    else:
        print("All imports successful!")


if __name__ == "__main__":
    test_llama_index_imports()
