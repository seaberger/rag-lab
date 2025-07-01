#!/usr/bin/env python3
"""
Comprehensive test suite for Microsoft Office document support in Pipeline v3.

Tests Word (.docx) and PowerPoint (.pptx) document parsing, indexing, and search functionality.
"""

import asyncio
import sys
import os
from pathlib import Path
import time
import json
from typing import Dict, List, Any

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from src.pipeline_v3.core.parsers import (
    DocumentType, DocumentClassifier, 
    parse_word_document, parse_powerpoint_document
)
from src.pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from src.pipeline_v3.core.index_manager import IndexManager, IndexType
from src.pipeline_v3.utils.config import PipelineConfig

# Test configuration
TEST_WORD_DOC = "data/sample_docs/Understanding-ISO-17025-Test-Document.docx"
TEST_PPT_DOC = "data/sample_docs/ISO-17025-Calibration-Standards-Presentation.pptx"


class TestOfficeDocuments:
    """Test suite for office document functionality."""
    
    def __init__(self):
        self.config = PipelineConfig()
        self.passed_tests = 0
        self.failed_tests = 0
        self.test_results = []
    
    def log_test(self, test_name: str, passed: bool, details: str = ""):
        """Log test results."""
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {test_name}")
        if details:
            print(f"   Details: {details}")
        
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        
        if passed:
            self.passed_tests += 1
        else:
            self.failed_tests += 1
    
    def test_document_classification(self):
        """Test document type classification."""
        print("\n🔍 Testing Document Classification...")
        
        # Test Word document
        word_type = DocumentClassifier.classify(TEST_WORD_DOC)
        self.log_test(
            "Word document classification",
            word_type == DocumentType.WORD_DOCUMENT,
            f"Got: {word_type}"
        )
        
        # Test PowerPoint document
        ppt_type = DocumentClassifier.classify(TEST_PPT_DOC)
        self.log_test(
            "PowerPoint document classification",
            ppt_type == DocumentType.POWERPOINT_PRESENTATION,
            f"Got: {ppt_type}"
        )
        
        # Test file extensions
        test_extensions = {
            "test.docx": DocumentType.WORD_DOCUMENT,
            "test.doc": DocumentType.WORD_DOCUMENT,
            "test.pptx": DocumentType.POWERPOINT_PRESENTATION,
            "test.ppt": DocumentType.POWERPOINT_PRESENTATION,
            "test.pdf": DocumentType.GENERIC_PDF,
            "test.md": DocumentType.MARKDOWN
        }
        
        for filename, expected_type in test_extensions.items():
            doc_type = DocumentClassifier.classify(filename)
            self.log_test(
                f"Extension classification: {filename}",
                doc_type == expected_type,
                f"Expected: {expected_type}, Got: {doc_type}"
            )
    
    async def test_word_parsing(self):
        """Test Word document parsing."""
        print("\n📄 Testing Word Document Parsing...")
        
        try:
            markdown, pairs, metadata = await parse_word_document(Path(TEST_WORD_DOC), self.config)
            
            # Test basic parsing
            self.log_test(
                "Word document parsing",
                len(markdown) > 0,
                f"Markdown length: {len(markdown)}"
            )
            
            # Test metadata extraction
            self.log_test(
                "Word metadata extraction",
                metadata.get("doc_type") == "word_document",
                f"Metadata keys: {list(metadata.keys())}"
            )
            
            # Test content structure
            has_headings = "#" in markdown
            self.log_test(
                "Word content has headings",
                has_headings,
                f"Found headings: {has_headings}"
            )
            
            # Test table extraction
            has_tables = "|" in markdown
            self.log_test(
                "Word table extraction",
                has_tables,
                f"Found tables: {has_tables}"
            )
            
            # Test pair extraction
            self.log_test(
                "Word pair extraction",
                len(pairs) > 0,
                f"Found {len(pairs)} pairs"
            )
            
        except Exception as e:
            self.log_test("Word document parsing", False, str(e))
    
    async def test_powerpoint_parsing(self):
        """Test PowerPoint document parsing."""
        print("\n📊 Testing PowerPoint Document Parsing...")
        
        try:
            markdown, pairs, metadata = await parse_powerpoint_document(Path(TEST_PPT_DOC), self.config)
            
            # Test basic parsing
            self.log_test(
                "PowerPoint document parsing",
                len(markdown) > 0,
                f"Markdown length: {len(markdown)}"
            )
            
            # Test metadata extraction
            self.log_test(
                "PowerPoint metadata extraction",
                metadata.get("doc_type") == "powerpoint_presentation",
                f"Slide count: {metadata.get('slide_count', 0)}"
            )
            
            # Test slide structure
            slide_count = markdown.count("# Slide")
            self.log_test(
                "PowerPoint slide extraction",
                slide_count == metadata.get("slide_count", 0),
                f"Found {slide_count} slides"
            )
            
            # Test speaker notes
            has_speaker_notes = "Speaker Notes:" in markdown
            self.log_test(
                "PowerPoint speaker notes",
                has_speaker_notes == metadata.get("has_speaker_notes", False),
                f"Speaker notes: {has_speaker_notes}"
            )
            
        except Exception as e:
            self.log_test("PowerPoint document parsing", False, str(e))
    
    async def test_pipeline_processing(self):
        """Test end-to-end pipeline processing."""
        print("\n🔄 Testing Pipeline Processing...")
        
        # Initialize pipeline
        pipeline = EnhancedPipeline(self.config)
        
        try:
            # Process Word document
            word_result = await pipeline.process_document(
                TEST_WORD_DOC,
                mode="auto",
                with_keywords=True
            )
            
            self.log_test(
                "Word document pipeline processing",
                word_result.get("status") == "success",
                f"Doc ID: {word_result.get('doc_id', 'none')[:8]}"
            )
            
            # Process PowerPoint document
            ppt_result = await pipeline.process_document(
                TEST_PPT_DOC,
                mode="auto",
                with_keywords=True
            )
            
            self.log_test(
                "PowerPoint pipeline processing",
                ppt_result.get("status") == "success",
                f"Doc ID: {ppt_result.get('doc_id', 'none')[:8]}"
            )
            
            # Check storage artifacts
            storage_dir = Path(self.config.storage.base_dir)
            word_artifact = storage_dir / f"{word_result.get('doc_id', '')}.jsonl"
            ppt_artifact = storage_dir / f"{ppt_result.get('doc_id', '')}.jsonl"
            
            self.log_test(
                "Word storage artifact created",
                word_artifact.exists(),
                f"Size: {word_artifact.stat().st_size if word_artifact.exists() else 0} bytes"
            )
            
            self.log_test(
                "PowerPoint storage artifact created",
                ppt_artifact.exists(),
                f"Size: {ppt_artifact.stat().st_size if ppt_artifact.exists() else 0} bytes"
            )
            
        except Exception as e:
            self.log_test("Pipeline processing", False, str(e))
        finally:
            await pipeline.shutdown()
    
    async def test_search_functionality(self):
        """Test search functionality for office documents."""
        print("\n🔍 Testing Search Functionality...")
        
        # Initialize pipeline
        pipeline = EnhancedPipeline(self.config)
        
        try:
            # Test keyword search
            keyword_results = pipeline.search(
                "FieldMaxII-TOP",
                search_type="keyword",
                top_k=5
            )
            
            self.log_test(
                "Keyword search with special characters",
                len(keyword_results) > 0,
                f"Found {len(keyword_results)} results"
            )
            
            # Test vector search
            vector_results = pipeline.search(
                "calibration uncertainty specifications",
                search_type="vector",
                top_k=5
            )
            
            self.log_test(
                "Vector search for office documents",
                len(vector_results) > 0,
                f"Found {len(vector_results)} results"
            )
            
            # Test hybrid search
            hybrid_results = pipeline.search(
                "ISO 17025 accreditation",
                search_type="hybrid",
                top_k=5
            )
            
            self.log_test(
                "Hybrid search for office documents",
                len(hybrid_results) > 0,
                f"Found {len(hybrid_results)} results"
            )
            
            # Verify source display
            if hybrid_results:
                has_source = all('source' in r and r['source'] != 'unknown' for r in hybrid_results)
                sources = list(set(r.get('source', 'unknown') for r in hybrid_results))
                self.log_test(
                    "Search results show document sources",
                    has_source,
                    f"Sources: {sources}"
                )
            
        except Exception as e:
            self.log_test("Search functionality", False, str(e))
        finally:
            await pipeline.shutdown()
    
    async def test_chunking_and_indexing(self):
        """Test document chunking and indexing."""
        print("\n📦 Testing Chunking and Indexing...")
        
        # Initialize components
        pipeline = EnhancedPipeline(self.config)
        index_manager = pipeline.index_manager
        
        try:
            # Get document IDs from registry
            word_doc = pipeline.registry.get_document_by_source(TEST_WORD_DOC)
            ppt_doc = pipeline.registry.get_document_by_source(TEST_PPT_DOC)
            
            if word_doc:
                # Check Word document chunks
                word_chunks = index_manager.get_document_chunks(
                    word_doc.doc_id, 
                    IndexType.KEYWORD
                )
                
                self.log_test(
                    "Word document chunking",
                    len(word_chunks) > 1,
                    f"Created {len(word_chunks)} chunks"
                )
                
                # Verify chunk content
                if word_chunks:
                    has_keywords = any("Keywords:" in chunk.get("content", "") for chunk in word_chunks)
                    self.log_test(
                        "Word chunks have keywords",
                        has_keywords,
                        "Keywords found in chunks"
                    )
            
            if ppt_doc:
                # Check PowerPoint document chunks
                ppt_chunks = index_manager.get_document_chunks(
                    ppt_doc.doc_id,
                    IndexType.KEYWORD
                )
                
                self.log_test(
                    "PowerPoint document chunking",
                    len(ppt_chunks) > 1,
                    f"Created {len(ppt_chunks)} chunks"
                )
                
                # Verify slide-based chunking
                if ppt_chunks:
                    slide_chunks = sum(1 for chunk in ppt_chunks 
                                     if "Slide" in chunk.get("content", ""))
                    self.log_test(
                        "PowerPoint slide-based chunking",
                        slide_chunks > 0,
                        f"Found {slide_chunks} slide chunks"
                    )
            
        except Exception as e:
            self.log_test("Chunking and indexing", False, str(e))
        finally:
            await pipeline.shutdown()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*50)
        print("📋 TEST SUMMARY")
        print("="*50)
        print(f"Total tests: {self.passed_tests + self.failed_tests}")
        print(f"✅ Passed: {self.passed_tests}")
        print(f"❌ Failed: {self.failed_tests}")
        print(f"Success rate: {self.passed_tests / (self.passed_tests + self.failed_tests) * 100:.1f}%")
        
        if self.failed_tests > 0:
            print("\nFailed tests:")
            for result in self.test_results:
                if not result["passed"]:
                    print(f"  - {result['test']}: {result['details']}")
        
        return self.failed_tests == 0
    
    async def run_all_tests(self):
        """Run all tests."""
        print("🚀 Starting Office Document Test Suite")
        print("="*50)
        
        # Run synchronous tests
        self.test_document_classification()
        
        # Run async tests
        await self.test_word_parsing()
        await self.test_powerpoint_parsing()
        await self.test_pipeline_processing()
        await self.test_chunking_and_indexing()
        await self.test_search_functionality()
        
        # Print summary
        return self.print_summary()


async def main():
    """Main test runner."""
    # Set up environment
    os.environ.setdefault("OPENAI_API_KEY", "test-key")
    
    # Create and run tests
    tester = TestOfficeDocuments()
    success = await tester.run_all_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())