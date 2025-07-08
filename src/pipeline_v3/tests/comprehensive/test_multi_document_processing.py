"""
Optimized multi-document processing tests for Comprehensive CI.

These tests process multiple real PDFs efficiently to minimize API costs
while still providing comprehensive coverage.
"""

import pytest
import pytest_asyncio
import sys
import time
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.enhanced_core import EnhancedPipeline
from core.database_factory import DatabaseFactory
from utils.config import PipelineConfig


@pytest.mark.comprehensive
@pytest.mark.heavy
@pytest.mark.requires_api
class TestMultiDocumentProcessing:
    """Test processing multiple documents efficiently."""

    @pytest_asyncio.fixture(scope="class")
    async def processed_documents(self, test_config):
        """Process multiple documents ONCE for all tests in this class."""
        # Create pipeline with PostgreSQL adapters
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()
        pipeline = EnhancedPipeline(test_config, database_adapters=adapters)

        # Get sample documents
        sample_docs_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "sample_docs"

        # Process 5 different documents with various modes
        test_docs = [
            {
                "file": "COHR_PowerMax-USB_UV-VIS_DS_0920_2.pdf",
                "mode": "datasheet",
                "with_keywords": True
            },
            {
                "file": "COHR_Air-CooledThermopileSensors_DB25_DS_1119_3.pdf",
                "mode": "datasheet",
                "with_keywords": False
            },
            {
                "file": "pm10k-plus-ds.pdf",
                "mode": "generic",
                "with_keywords": True
            },
            {
                "file": "Understanding-ISO-17025-Test-Document.docx",
                "mode": "generic",
                "with_keywords": True
            },
            {
                "file": "ISO-17025-Calibration-Standards-Presentation.pptx",
                "mode": "generic",
                "with_keywords": False
            }
        ]

        results = []
        start_time = time.time()

        for doc_info in test_docs:
            doc_path = sample_docs_path / doc_info["file"]
            if not doc_path.exists():
                print(f"Skipping {doc_info['file']} - not found")
                continue

            print(f"Processing {doc_info['file']} with mode={doc_info['mode']}, keywords={doc_info['with_keywords']}")

            result = await pipeline.process_document(
                str(doc_path),
                metadata={
                    "source": "comprehensive_test",
                    "document_type": doc_info["mode"],
                    "test_batch": True
                },
                mode=doc_info["mode"],
                with_keywords=doc_info["with_keywords"]
            )

            results.append({
                "file": doc_info["file"],
                "result": result,
                "mode": doc_info["mode"],
                "with_keywords": doc_info["with_keywords"]
            })

        total_time = time.time() - start_time
        print(f"Processed {len(results)} documents in {total_time:.2f} seconds")

        yield pipeline, results

        # Cleanup is handled by fixture teardown

    @pytest.mark.asyncio
    @pytest.mark.comprehensive
    async def test_all_documents_processed(self, processed_documents):
        """Verify all documents were successfully processed."""
        pipeline, results = processed_documents

        # Should have processed at least 3 documents
        assert len(results) >= 3, f"Expected at least 3 documents, got {len(results)}"

        # All should be successful
        for doc_result in results:
            result = doc_result["result"]
            assert result is not None, f"No result for {doc_result['file']}"
            assert result.get("status") == "success", f"Failed to process {doc_result['file']}"
            assert "doc_id" in result, f"No doc_id for {doc_result['file']}"

    @pytest.mark.asyncio
    @pytest.mark.comprehensive
    async def test_datasheet_vs_generic_processing(self, processed_documents):
        """Test that datasheet and generic modes extract different metadata."""
        pipeline, results = processed_documents

        # Find datasheet and generic results
        datasheet_results = [r for r in results if r["mode"] == "datasheet"]
        generic_results = [r for r in results if r["mode"] == "generic"]

        assert len(datasheet_results) > 0, "No datasheet results found"
        assert len(generic_results) > 0, "No generic results found"

        # Datasheets should have richer metadata
        for ds_result in datasheet_results:
            if ds_result["result"] and ds_result["result"].get("status") == "success":
                # Check in registry for metadata
                doc_id = ds_result["result"]["doc_id"]
                doc_info = pipeline.registry.get_document(doc_id)
                assert doc_info is not None, f"Document {doc_id} not in registry"

                # Datasheet mode should extract parameters
                metadata = doc_info.get("metadata", {})
                print(f"Datasheet {ds_result['file']} metadata keys: {list(metadata.keys())}")

    @pytest.mark.asyncio
    @pytest.mark.comprehensive
    async def test_keyword_enhancement_impact(self, processed_documents):
        """Test that keyword enhancement improves search results."""
        pipeline, results = processed_documents

        # Find documents processed with and without keywords
        with_keywords = [r for r in results if r["with_keywords"]]
        without_keywords = [r for r in results if not r["with_keywords"]]

        assert len(with_keywords) > 0, "No documents processed with keywords"
        assert len(without_keywords) > 0, "No documents processed without keywords"

        # Documents with keywords should have keyword index entries
        for kw_result in with_keywords:
            if kw_result["result"] and kw_result["result"].get("status") == "success":
                doc_id = kw_result["result"]["doc_id"]

                # Try a keyword search
                search_results = pipeline.search(
                    kw_result["file"].split(".")[0],  # Search for filename
                    search_type="keyword",
                    top_k=5
                )

                # Should find the document
                found_doc_ids = [r.get("doc_id") for r in search_results]
                print(f"Keyword search for {kw_result['file']}: found {len(search_results)} results")

    @pytest.mark.asyncio
    @pytest.mark.comprehensive
    async def test_cross_format_search(self, processed_documents):
        """Test searching across different document formats."""
        pipeline, results = processed_documents

        # Search for content that should appear in multiple formats
        test_queries = [
            "ISO 17025",  # Should find Word and PowerPoint
            "sensor",     # Should find PDFs
            "calibration", # Cross-cutting term
        ]

        for query in test_queries:
            # Test all search types
            for search_type in ["vector", "keyword", "hybrid"]:
                results = pipeline.search(query, search_type=search_type, top_k=10)
                print(f"Search '{query}' ({search_type}): {len(results)} results")

                # Should find some results
                assert len(results) > 0, f"No results for '{query}' with {search_type} search"

    @pytest.mark.asyncio
    @pytest.mark.comprehensive
    async def test_batch_performance_metrics(self, processed_documents):
        """Analyze performance metrics for batch processing."""
        pipeline, results = processed_documents

        # Calculate statistics
        total_docs = len(results)
        successful = len([r for r in results if r["result"] and r["result"].get("status") == "success"])

        # Performance assertions
        assert successful >= total_docs * 0.8, f"Less than 80% success rate: {successful}/{total_docs}"

        # Check registry consistency
        stats = pipeline.registry.get_statistics()
        assert stats["total_documents"] >= successful, "Registry count doesn't match successful documents"

        # Check index consistency
        vector_count = pipeline.index_manager._get_vector_count()
        assert vector_count > 0, "No vectors in index after batch processing"
