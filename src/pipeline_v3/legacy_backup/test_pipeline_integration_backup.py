"""
Comprehensive Integration Tests for Pipeline v3

These tests exercise the full pipeline functionality to ensure proper integration
between all components and significantly boost code coverage.
"""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.enhanced_core import EnhancedPipeline
from core.registry import DocumentRegistry
from core.index_manager import IndexManager
from storage.keyword_index import BM25Index
from core.fingerprint import FingerprintManager
from job_queue.manager import DocumentQueue
from job_queue.job import JobManager
from utils.config import PipelineConfig
from storage.cache import CacheManager
# Vector storage is handled by Qdrant directly through IndexManager


class TestPipelineIntegration:
    """Integration tests for the complete pipeline."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def test_config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        # Update paths to use temp directory
        config.storage.base_dir = temp_dir
        config.cache.directory = os.path.join(temp_dir, "cache")
        config.storage.document_registry_path = os.path.join(temp_dir, "registry.db")
        config.storage.keyword_db_path = os.path.join(temp_dir, "keyword.db")
        config.fingerprint.storage_path = os.path.join(temp_dir, "fingerprint.db")
        config.job_queue.job_storage_path = os.path.join(temp_dir, "jobs.db")
        config.qdrant.path = os.path.join(temp_dir, "qdrant")
        return config

    @pytest.fixture
    def mock_openai(self):
        """Mock OpenAI API calls."""
        with patch("openai.OpenAI") as mock_openai_class:
            # Mock the OpenAI client instance
            instance = MagicMock()
            mock_openai_class.return_value = instance

            # Mock process_document_pages
            async def mock_process_pages(*args, **kwargs):
                return {
                    "model": "test",
                    "product_name": "Test Product",
                    "manufacturer": "Test Corp",
                    "specifications": [
                        {"category": "General", "details": {"Type": "Test"}}
                    ],
                    "key_features": ["Feature 1", "Feature 2"],
                    "applications": ["App 1"],
                    "technical_details": "Test details",
                    "datasheet_content": "Full test content",
                    "datasheet_type": "datasheet"
                }
            instance.process_document_pages = AsyncMock(side_effect=mock_process_pages)

            # Mock get_embeddings
            async def mock_embeddings(text):
                # Return a 1536-dimensional vector (matching OpenAI embeddings)
                return [0.1] * 1536
            instance.get_embeddings = AsyncMock(side_effect=mock_embeddings)

            # Mock extract_keywords
            async def mock_keywords(text):
                return ["keyword1", "keyword2", "test", "product"]
            instance.extract_keywords = AsyncMock(side_effect=mock_keywords)

            yield instance

    @pytest.fixture
    def mock_document_processor(self):
        """Mock document processor."""
        with patch("core.parsers.DocumentProcessor") as mock_proc:
            instance = MagicMock()
            mock_proc.return_value = instance

            # Mock extract_pages
            async def mock_extract(path):
                return [b"Page 1 content", b"Page 2 content"]
            instance.extract_pages = AsyncMock(side_effect=mock_extract)

            yield instance

    @pytest.mark.asyncio
    async def test_full_pipeline_document_processing(self, test_config, mock_openai, mock_document_processor, temp_dir):
        """Test complete document processing through the pipeline."""
        # Initialize pipeline with test config
        pipeline = EnhancedPipeline(config=test_config)

        # Create a test PDF file
        test_pdf = os.path.join(temp_dir, "test_document.pdf")
        with open(test_pdf, "wb") as f:
            f.write(b"Mock PDF content")

        # Process the document
        result = await pipeline.process_document(
            file_path=test_pdf,
            metadata={"source": "test"},
            force_reprocess=False,
            with_keywords=True
        )

        # Verify result structure
        assert result["status"] == "success"
        assert "doc_id" in result
        assert result["source"] == test_pdf

        # Verify document was registered
        registry = DocumentRegistry(config=test_config)
        doc_info = registry.get_document_by_source(test_pdf)
        assert doc_info is not None
        assert doc_info["status"] == "completed"

        # Vector index creation is verified by the search functionality below

        # Search for the document
        search_results = await pipeline.search(
            query="test product",
            search_type="hybrid",
            top_k=5
        )

        assert len(search_results) > 0
        assert search_results[0]["source"] == test_pdf

    @pytest.mark.asyncio
    async def test_pipeline_with_queue_processing(self, test_config, mock_openai, mock_document_processor, temp_dir):
        """Test pipeline with queue-based processing."""
        # Initialize components
        pipeline = EnhancedPipeline(config=test_config)
        queue = DocumentQueue(config=test_config)

        # Create test documents
        test_docs = []
        for i in range(3):
            doc_path = os.path.join(temp_dir, f"doc_{i}.pdf")
            with open(doc_path, "wb") as f:
                f.write(f"Mock PDF {i}".encode())
            test_docs.append(doc_path)

        # Add documents to queue
        job_ids = []
        for doc in test_docs:
            job_id = await queue.add_job(
                source=doc,
                job_type="add",
                metadata={"batch": "test"}
            )
            job_ids.append(job_id)

        # Verify jobs were queued
        status = queue.get_status()
        assert status["queue_status"]["pending"] == 3

        # Process one job manually (simulating worker)
        job = queue.pending.get()
        assert job.source in test_docs

        # Mark job as completed
        queue.complete_job(job.job_id, {"status": "success"})
        assert job.job_id in queue.completed

    @pytest.mark.asyncio
    async def test_index_manager_operations(self, test_config, mock_openai, temp_dir):
        """Test index manager functionality."""
        # Initialize index manager
        index_manager = IndexManager(config=test_config)

        # Create test document data
        doc_id = "test-doc-123"
        content = "This is test content for index manager testing"
        metadata = {
            "source": "test.pdf",
            "title": "Test Document",
            "page_count": 2
        }

        # Add to vector index
        embedding = await mock_openai.get_embeddings(content)
        await index_manager.add_to_vector_index(
            doc_id=doc_id,
            content=content,
            embedding=embedding,
            metadata=metadata
        )

        # Add to keyword index
        keywords = await mock_openai.extract_keywords(content)
        await index_manager.add_to_keyword_index(
            doc_id=doc_id,
            content=content,
            metadata=metadata,
            keywords=keywords
        )

        # Test vector search
        query_embedding = await mock_openai.get_embeddings("test query")
        vector_results = await index_manager.vector_search(
            query_embedding=query_embedding,
            top_k=5
        )

        assert len(vector_results) > 0
        assert vector_results[0]["doc_id"] == doc_id

        # Test keyword search
        keyword_results = await index_manager.keyword_search(
            query="test content",
            top_k=5
        )

        assert len(keyword_results) > 0
        assert keyword_results[0]["doc_id"] == doc_id

        # Test hybrid search
        hybrid_results = await index_manager.hybrid_search(
            query="test",
            query_embedding=query_embedding,
            top_k=5
        )

        assert len(hybrid_results) > 0

        # Test deletion
        await index_manager.remove_document(doc_id)

        # Verify deletion
        vector_results = await index_manager.vector_search(
            query_embedding=query_embedding,
            top_k=5
        )
        assert len(vector_results) == 0

    @pytest.mark.asyncio
    async def test_storage_cache_operations(self, test_config, temp_dir):
        """Test storage cache functionality."""
        cache = CacheManager(config=test_config)

        # Test data
        test_key = "test_doc_123"
        test_data = {
            "content": "Test content",
            "metadata": {"type": "test"},
            "embedding": [0.1] * 1536
        }

        # Save to cache - CacheManager uses doc_hash and prompt_hash
        doc_hash = "test_doc_hash"
        prompt_hash = "test_prompt_hash"
        success = cache.put(doc_hash, prompt_hash, test_data)
        assert success

        # Load from cache
        loaded_data = cache.get(doc_hash, prompt_hash)
        assert loaded_data is not None
        assert loaded_data["content"] == test_data["content"]
        assert loaded_data["metadata"] == test_data["metadata"]

        # Test cache hit
        assert cache.get(doc_hash, prompt_hash) is not None

        # Clear cache
        cleared = cache.clear()
        assert cleared > 0
        assert cache.get(doc_hash, prompt_hash) is None

        # Test compression
        large_data = {
            "content": "x" * 10000,
            "chunks": ["chunk" * 100 for _ in range(10)]
        }
        success = cache.put("large_doc_hash", "large_prompt_hash", large_data)
        assert success

        # Verify data can be retrieved
        loaded_large = cache.get("large_doc_hash", "large_prompt_hash")
        assert loaded_large is not None
        assert loaded_large["content"] == large_data["content"]

    @pytest.mark.asyncio
    async def test_document_registry_lifecycle(self, test_config):
        """Test document registry lifecycle management."""
        registry = DocumentRegistry(config=test_config)

        # Register new document
        import time
        doc_id = registry.register_document(
            source="test.pdf",
            content_hash="test_hash_123",
            size=1024,
            modified_time=time.time(),
            metadata={"version": "1.0", "doc_type": "datasheet"}
        )

        assert doc_id is not None

        # Update status through lifecycle
        registry.update_status(doc_id, "processing")
        doc = registry.get_document(doc_id)
        assert doc["status"] == "processing"

        # Add vector index
        registry.update_indexes(doc_id, has_vector=True, vector_ids=["vec1", "vec2"])
        doc = registry.get_document(doc_id)
        assert doc["has_vector_index"] == 1
        assert doc["vector_ids"] == ["vec1", "vec2"]

        # Add keyword index
        registry.update_indexes(doc_id, has_keyword=True)
        doc = registry.get_document(doc_id)
        assert doc["has_keyword_index"] == 1

        # Complete processing
        registry.update_document(
            doc_id,
            status="completed",
            page_count=10,
            file_size=1024000,
            processing_time=45.5
        )

        doc = registry.get_document(doc_id)
        assert doc["status"] == "completed"
        assert doc["page_count"] == 10
        assert doc["processing_time"] == 45.5

        # Test statistics
        stats = registry.get_statistics()
        assert stats["total_documents"] == 1
        assert stats["completed_documents"] == 1

        # Test change detection
        is_changed = registry.has_changed(
            source="test.pdf",
            size=1024000,
            modified_time="2024-01-01T00:00:00"
        )
        assert not is_changed  # Same size, so no change

    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self, test_config, temp_dir):
        """Test error handling and recovery mechanisms."""
        pipeline = EnhancedPipeline(config=test_config)

        # Test with non-existent file
        result = await pipeline.process_document(
            file_path="/non/existent/file.pdf",
            metadata={}
        )

        assert result["status"] == "error"
        assert "error" in result

        # Test with invalid OpenAI response
        with patch("openai.OpenAI") as mock_openai_class:
            instance = MagicMock()
            mock_openai_class.return_value = instance

            # Mock to raise exception
            instance.process_document_pages = AsyncMock(
                side_effect=Exception("API Error")
            )

            test_file = os.path.join(temp_dir, "error_test.pdf")
            with open(test_file, "wb") as f:
                f.write(b"Mock content")

            result = await pipeline.process_document(
                file_path=test_file,
                metadata={}
            )

            assert result["status"] == "error"
            assert "API Error" in str(result["error"])

    @pytest.mark.asyncio
    async def test_concurrent_processing(self, test_config, mock_openai, mock_document_processor, temp_dir):
        """Test concurrent document processing."""
        pipeline = EnhancedPipeline(config=test_config)

        # Create multiple test documents
        test_docs = []
        for i in range(5):
            doc_path = os.path.join(temp_dir, f"concurrent_{i}.pdf")
            with open(doc_path, "wb") as f:
                f.write(f"Concurrent test {i}".encode())
            test_docs.append(doc_path)

        # Process documents concurrently
        tasks = []
        for doc in test_docs:
            task = pipeline.process_document(
                file_path=doc,
                metadata={"batch": "concurrent"},
                with_keywords=True
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        # Verify all succeeded
        assert len(results) == 5
        assert all(r["status"] == "success" for r in results)

        # Verify all documents are in registry
        registry = DocumentRegistry(config=test_config)
        for doc in test_docs:
            doc_info = registry.get_document_by_source(doc)
            assert doc_info is not None
            assert doc_info["status"] == "completed"

    def test_configuration_management(self, temp_dir):
        """Test configuration loading and management."""
        # Test default configuration
        config = PipelineConfig()
        assert config.openai.vision_model == "gpt-4.1"
        assert config.storage.base_dir == "./storage_data_v3"

        # Test configuration override
        config_dict = {
            "openai": {"vision_model": "gpt-4.1"},
            "storage": {"base_dir": temp_dir},
            "job_queue": {"max_concurrent": 10}
        }

        config_file = os.path.join(temp_dir, "test_config.yaml")
        import yaml
        with open(config_file, "w") as f:
            yaml.dump(config_dict, f)

        custom_config = PipelineConfig.from_yaml(config_file)
        assert custom_config.openai.vision_model == "gpt-4.1"
        assert custom_config.storage.base_dir == temp_dir
        assert custom_config.job_queue.max_concurrent == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
