#!/usr/bin/env python3
"""
Test script for Issue #11: Configurable timeout handling
"""

import asyncio
import time
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent))

from pipeline_v3.utils.config import PipelineConfig
from pipeline_v3.core.parsers import parse_document, DocumentType, DocumentClassifier
from pipeline_v3.utils.common_utils import logger, setup_logging

setup_logging(level="DEBUG")

async def test_timeout_calculation():
    """Test page-based timeout calculation."""
    print("\n=== Testing Timeout Calculation ===")
    
    config = PipelineConfig()
    print(f"Default timeout per page: {config.openai.timeout_per_page}s")
    print(f"Default base timeout: {config.openai.timeout_base}s")
    
    # Test with different page counts
    test_cases = [
        ("5 pages", 5),
        ("20 pages", 20),
        ("100 pages", 100),
        ("200 pages", 200)
    ]
    
    for description, page_count in test_cases:
        timeout = config.openai.timeout_base + (page_count * config.openai.timeout_per_page)
        print(f"{description}: {timeout}s timeout ({timeout/60:.1f} minutes)")
    
    print("\n✅ Timeout calculation test complete")

async def test_timeout_handling():
    """Test timeout handling with a sample document."""
    print("\n=== Testing Timeout Handling ===")
    
    # Look for test PDFs
    sample_docs = Path("data/sample_docs")
    if not sample_docs.exists():
        print("❌ Sample docs directory not found")
        return
    
    # Find a small PDF for testing
    pdfs = list(sample_docs.glob("*.pdf"))
    if not pdfs:
        print("❌ No PDF files found in sample_docs")
        return
    
    test_pdf = pdfs[0]
    print(f"Testing with: {test_pdf.name}")
    
    # Create config with very short timeout for testing
    config = PipelineConfig()
    config.openai.timeout_per_page = 1  # 1 second per page (too short)
    config.openai.timeout_base = 2  # 2 seconds base
    
    print(f"Using artificially short timeout: {config.openai.timeout_per_page}s per page")
    
    # Try to parse document with short timeout
    doc_type = DocumentClassifier.classify(test_pdf, is_datasheet_mode=True)
    prompt = "Extract all text from this document."
    
    try:
        start = time.time()
        markdown, pairs, metadata = await parse_document(
            test_pdf, doc_type, prompt, None, config
        )
        elapsed = time.time() - start
        print(f"❌ Document parsed successfully in {elapsed:.1f}s (expected timeout)")
    except TimeoutError as e:
        elapsed = time.time() - start
        print(f"✅ Timeout error caught as expected after {elapsed:.1f}s: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")

async def test_cli_timeout_params():
    """Test CLI timeout parameters."""
    print("\n=== Testing CLI Timeout Parameters ===")
    
    # Simulate CLI arguments
    class Args:
        timeout = 600  # 10 minutes total
        timeout_per_page = 45  # 45 seconds per page
    
    args = Args()
    config = PipelineConfig()
    
    print(f"Before CLI override:")
    print(f"  - timeout_seconds: {config.pipeline.timeout_seconds}s")
    print(f"  - timeout_per_page: {config.openai.timeout_per_page}s")
    
    # Apply CLI overrides
    if args.timeout:
        config.pipeline.timeout_seconds = args.timeout
    if args.timeout_per_page:
        config.openai.timeout_per_page = args.timeout_per_page
    
    print(f"\nAfter CLI override:")
    print(f"  - timeout_seconds: {config.pipeline.timeout_seconds}s")
    print(f"  - timeout_per_page: {config.openai.timeout_per_page}s")
    
    print("\n✅ CLI parameter test complete")

async def main():
    """Run all timeout tests."""
    print("Testing Issue #11: Configurable Timeout Handling")
    print("=" * 50)
    
    await test_timeout_calculation()
    await test_timeout_handling()
    await test_cli_timeout_params()
    
    print("\n" + "=" * 50)
    print("All tests complete!")

if __name__ == "__main__":
    asyncio.run(main())