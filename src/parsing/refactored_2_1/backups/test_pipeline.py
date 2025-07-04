#!/usr/bin/env python3
"""
Test script for the datasheet ingestion pipeline.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add the parent directory to Python path for proper imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))
sys.path.insert(0, str(current_dir.parent))

# Set up environment
os.environ.setdefault("OPENAI_API_KEY", "test-key-not-set")


async def test_pipeline():
    """Test the pipeline with a sample document."""

    print("🧪 Testing Pipeline on pm10k-plus-ds.pdf")
    print("=" * 50)

    # Test document path
    doc_path = current_dir / "../../../data/sample_docs/pm10k-plus-ds.pdf"

    if not doc_path.exists():
        print(f"❌ Test document not found: {doc_path}")
        return False

    print(f"📄 Document found: {doc_path}")

    try:
        # Test imports
        print("🔍 Testing imports...")

        from pipeline.core import DatasheetArtefact, _resolve_prompt, fetch_document
        from pipeline.parsers import DocumentClassifier, _find_poppler

        from utils.env_utils import setup_environment

        print("✅ All imports successful")

        # Test environment setup
        print("🔧 Testing environment setup...")
        env_ok = setup_environment()
        if not env_ok:
            print("⚠️ Environment setup reported issues (expected without real API key)")

        # Test Poppler discovery
        print("🛠️ Testing Poppler discovery...")
        poppler_path = _find_poppler()
        if poppler_path:
            print(f"✅ Poppler found at: {poppler_path}")
        else:
            print("⚠️ Poppler not found in PATH")

        # Test document classification
        print("📋 Testing document classification...")
        doc_type = DocumentClassifier.classify(doc_path, is_datasheet_mode=True)
        confidence = DocumentClassifier.get_confidence(doc_path, doc_type)
        print(f"✅ Document classified as: {doc_type.value} (confidence: {confidence:.2f})")

        # Test document fetching
        print("📁 Testing document fetching...")
        pdf_path, doc_id, raw_bytes = await fetch_document(doc_path)
        print(f"✅ Document fetched: ID={doc_id}, Size={len(raw_bytes)} bytes")

        # Test artifact creation
        print("📝 Testing artifact creation...")
        artifact = DatasheetArtefact(
            doc_id=doc_id,
            source=str(doc_path),
            pairs=[("PM10K+", "2293937")],  # Test data
            markdown="# Test Markdown",
            parse_version=2,
            metadata={"test": True},
        )
        jsonl = artifact.to_jsonl()
        print(f"✅ Artifact created: {len(jsonl)} chars")

        # Test prompt resolution
        print("📄 Testing prompt resolution...")
        prompt = _resolve_prompt(None)
        print(f"✅ Prompt resolved: {len(prompt)} chars")

        print("\n🎉 All basic tests passed!")
        print("Note: Full pipeline test requires valid OpenAI API key")
        return True

    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_pipeline())
    sys.exit(0 if success else 1)
