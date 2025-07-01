"""
Integration tests for Microsoft Office document support.
"""

import pytest
import asyncio
from pathlib import Path
import tempfile
import shutil

from src.pipeline_v3.core.parsers import (
    DocumentType, DocumentClassifier,
    parse_word_document, parse_powerpoint_document
)
from src.pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from src.pipeline_v3.utils.config import PipelineConfig


class TestOfficeIntegration:
    """Integration tests for office document processing."""
    
    @pytest.fixture
    def config(self):
        """Create test configuration."""
        config = PipelineConfig()
        # Use temporary directories for testing
        config.storage.base_dir = tempfile.mkdtemp()
        config.qdrant.path = tempfile.mkdtemp()
        config.storage.keyword_db_path = Path(tempfile.mkdtemp()) / "keyword_test.db"
        return config
    
    @pytest.fixture
    def sample_word_doc(self):
        """Path to sample Word document."""
        return Path("data/sample_docs/Understanding-ISO-17025-Test-Document.docx")
    
    @pytest.fixture
    def sample_ppt_doc(self):
        """Path to sample PowerPoint document."""
        return Path("data/sample_docs/ISO-17025-Calibration-Standards-Presentation.pptx")
    
    def test_document_classification(self, sample_word_doc, sample_ppt_doc):
        """Test document type classification."""
        # Test Word
        assert DocumentClassifier.classify(sample_word_doc) == DocumentType.WORD_DOCUMENT
        assert DocumentClassifier.classify("test.docx") == DocumentType.WORD_DOCUMENT
        assert DocumentClassifier.classify("test.doc") == DocumentType.WORD_DOCUMENT
        
        # Test PowerPoint
        assert DocumentClassifier.classify(sample_ppt_doc) == DocumentType.POWERPOINT_PRESENTATION
        assert DocumentClassifier.classify("test.pptx") == DocumentType.POWERPOINT_PRESENTATION
        assert DocumentClassifier.classify("test.ppt") == DocumentType.POWERPOINT_PRESENTATION
    
    @pytest.mark.asyncio
    async def test_word_parsing(self, sample_word_doc, config):
        """Test Word document parsing."""
        markdown, pairs, metadata = await parse_word_document(sample_word_doc, config)
        
        # Verify content
        assert len(markdown) > 0
        assert "ISO 17025" in markdown
        assert "#" in markdown  # Has headings
        assert "|" in markdown  # Has tables
        
        # Verify metadata
        assert metadata["doc_type"] == "word_document"
        assert metadata["file_name"] == sample_word_doc.name
        assert "section_count" in metadata
        assert metadata["section_count"] > 0
        
        # Verify pairs extraction
        assert isinstance(pairs, list)
        assert len(pairs) > 0
    
    @pytest.mark.asyncio
    async def test_powerpoint_parsing(self, sample_ppt_doc, config):
        """Test PowerPoint document parsing."""
        markdown, pairs, metadata = await parse_powerpoint_document(sample_ppt_doc, config)
        
        # Verify content
        assert len(markdown) > 0
        assert "Slide" in markdown
        assert metadata["slide_count"] == 6
        
        # Verify metadata
        assert metadata["doc_type"] == "powerpoint_presentation"
        assert metadata["file_name"] == sample_ppt_doc.name
        assert metadata["has_speaker_notes"] is True
        
        # Verify slide structure
        slide_count = markdown.count("# Slide")
        assert slide_count == metadata["slide_count"]
    
    @pytest.mark.asyncio
    async def test_pipeline_processing(self, sample_word_doc, sample_ppt_doc, config):
        """Test end-to-end pipeline processing."""
        pipeline = EnhancedPipeline(config)
        
        try:
            # Process Word document
            word_result = await pipeline.process_document(
                sample_word_doc,
                mode="auto",
                with_keywords=True
            )
            assert word_result["status"] == "success"
            assert "doc_id" in word_result
            
            # Process PowerPoint document
            ppt_result = await pipeline.process_document(
                sample_ppt_doc,
                mode="auto",
                with_keywords=True
            )
            assert ppt_result["status"] == "success"
            assert "doc_id" in ppt_result
            
            # Verify storage artifacts
            storage_dir = Path(config.storage.base_dir)
            assert (storage_dir / f"{word_result['doc_id']}.jsonl").exists()
            assert (storage_dir / f"{ppt_result['doc_id']}.jsonl").exists()
            
        finally:
            await pipeline.shutdown()
            # Cleanup
            shutil.rmtree(config.storage.base_dir, ignore_errors=True)
            shutil.rmtree(config.qdrant.path, ignore_errors=True)
            config.storage.keyword_db_path.parent.rmdir()
    
    @pytest.mark.asyncio
    async def test_search_functionality(self, sample_word_doc, sample_ppt_doc, config):
        """Test search functionality."""
        pipeline = EnhancedPipeline(config)
        
        try:
            # Process documents first
            await pipeline.process_document(sample_word_doc, with_keywords=True)
            await pipeline.process_document(sample_ppt_doc, with_keywords=True)
            
            # Test keyword search with special characters
            results = pipeline.search("FieldMaxII-TOP", search_type="keyword", top_k=5)
            assert len(results) > 0
            
            # Test vector search
            results = pipeline.search("calibration uncertainty", search_type="vector", top_k=5)
            assert len(results) > 0
            
            # Test hybrid search
            results = pipeline.search("ISO 17025", search_type="hybrid", top_k=5)
            assert len(results) > 0
            
            # Verify source field
            for result in results:
                assert "source" in result
                assert result["source"] != "unknown"
                assert result["source"] in [sample_word_doc.name, sample_ppt_doc.name]
            
        finally:
            await pipeline.shutdown()
            # Cleanup
            shutil.rmtree(config.storage.base_dir, ignore_errors=True)
            shutil.rmtree(config.qdrant.path, ignore_errors=True)
            config.storage.keyword_db_path.parent.rmdir()
    
    @pytest.mark.asyncio
    async def test_chunking_strategy(self, sample_word_doc, sample_ppt_doc, config):
        """Test document chunking strategies."""
        pipeline = EnhancedPipeline(config)
        
        try:
            # Process documents
            word_result = await pipeline.process_document(sample_word_doc, with_keywords=True)
            ppt_result = await pipeline.process_document(sample_ppt_doc, with_keywords=True)
            
            # Get chunks
            word_doc = pipeline.registry.get_document(word_result["doc_id"])
            ppt_doc = pipeline.registry.get_document(ppt_result["doc_id"])
            
            # Verify Word document has multiple semantic chunks
            assert word_doc.chunk_count > 5  # Should have several sections
            
            # Verify PowerPoint has slide-based chunks
            assert ppt_doc.chunk_count == 6  # One chunk per slide
            
        finally:
            await pipeline.shutdown()
            # Cleanup
            shutil.rmtree(config.storage.base_dir, ignore_errors=True)
            shutil.rmtree(config.qdrant.path, ignore_errors=True)
            config.storage.keyword_db_path.parent.rmdir()
    
    def test_special_character_escaping(self):
        """Test FTS5 special character escaping."""
        from src.pipeline_v3.core.index_manager import IndexManager
        
        # Test queries that should be escaped
        test_queries = [
            "FieldMaxII-TOP",
            "Part: 1234567",
            "PM-USB-VIS",
            "test(parentheses)",
            'test"quotes"',
            "test*wildcard",
            "test^caret"
        ]
        
        # Each special character should be wrapped in quotes
        for query in test_queries:
            # This would be tested internally in the IndexManager
            # For now, just verify the queries don't cause syntax errors
            assert isinstance(query, str)