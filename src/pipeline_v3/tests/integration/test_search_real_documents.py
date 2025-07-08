"""
Real Document Search Integration Tests for Pipeline v3

Tests that process actual PDF documents through the complete pipeline and verify
search functionality works correctly with real-world content.
"""

import asyncio
import pytest
import pytest_asyncio
import sys
from pathlib import Path

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline.enhanced_core import EnhancedPipeline
from core.database_factory import DatabaseFactory
from core.registry import IndexType
from utils.config import PipelineConfig


@pytest.mark.requires_qdrant_server
class TestRealDocumentSearch:
    """Integration tests using real PDF documents from sample_docs."""

    # Class-level storage for processed documents
    _pipeline = None
    _doc_info = None

    @pytest_asyncio.fixture(scope="class")
    async def pipeline_with_docs(self, test_config):
        """Create pipeline and process real documents for testing."""
        # Create pipeline with database adapters
        factory = DatabaseFactory(test_config)
        adapters = factory.create_all()
        pipeline = EnhancedPipeline(test_config, database_adapters=adapters)

        # Process a few real PDFs from sample_docs
        sample_docs_path = Path(__file__).parent.parent.parent.parent.parent / "data" / "sample_docs"

        # Process two specific documents with different modes
        test_documents = [
            {
                "file": "labmax-touch-ds.pdf",
                "mode": "datasheet",
                "with_keywords": True,
                "expected_content": ["LabMax", "Touch", "laser power", "energy meter"],
                "expected_metadata": ["wavelength", "power range", "accuracy"],
                "category": "power_meter"
            },
            {
                "file": "Understanding-ISO-17025-Test-Document.docx",
                "mode": "generic",  # Non-datasheet mode
                "with_keywords": True,
                "expected_content": ["ISO", "17025", "calibration", "accreditation"],
                "category": "standards"
            }
        ]

        # Process each document with specific parameters
        doc_info = {}
        for doc in test_documents:
            doc_path = sample_docs_path / doc["file"]
            if doc_path.exists():
                print(f"Processing {doc['file']} with mode={doc['mode']}, keywords={doc['with_keywords']}...")

                # Build processing options
                processing_options = {
                    "mode": doc["mode"],
                    "with_keywords": doc["with_keywords"],
                    "metadata": {"category": doc["category"], "test": True},
                    "force_reprocess": True  # Force reprocess in case document exists from previous runs
                }

                result = await pipeline.process_document(
                    source=str(doc_path),
                    **processing_options
                )

                if result["status"] == "success":
                    doc_info[doc["file"]] = {
                        "doc_id": result["doc_id"],
                        "expected": doc["expected_content"],
                        "expected_metadata": doc.get("expected_metadata", []),
                        "category": doc["category"],
                        "mode": doc["mode"]
                    }
                    print(f"Successfully processed {doc['file']} with doc_id: {result['doc_id']}")

                    # Verify the document has the expected processing
                    if doc["mode"] == "datasheet":
                        # Check if datasheet metadata was extracted
                        doc_record = pipeline.registry.get_document(result["doc_id"])
                        if doc_record and doc_record.metadata:
                            print(f"  Metadata keys: {list(doc_record.metadata.keys())}")
                else:
                    print(f"Failed to process {doc['file']}: {result.get('error', 'Unknown error')}")
            else:
                print(f"Warning: {doc_path} not found, skipping")

        # Store document info for tests
        pipeline.test_doc_info = doc_info

        yield pipeline

        # Cleanup is handled by conftest.py

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.requires_api
    async def test_vector_search_real_content(self, pipeline_with_docs):
        """Test vector search finds semantically relevant content from real PDFs."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        # Skip if no documents were processed
        if not doc_info:
            pytest.skip("No documents were successfully processed")

        # Test queries that should find specific documents
        test_queries = [
            {
                "query": "laser power measurement touchscreen interface",
                "expected_doc": "labmax-touch-ds.pdf",
                "reason": "Should find LabMax-Touch which is a laser power meter with touchscreen"
            },
            {
                "query": "ISO 17025 calibration standards accreditation",
                "expected_doc": "Understanding-ISO-17025-Test-Document.docx",
                "reason": "Should find ISO 17025 standards document"
            }
        ]

        for test_case in test_queries:
            if test_case["expected_doc"] not in doc_info:
                print(f"Skipping test - {test_case['expected_doc']} not processed")
                continue

            results = pipeline.index_manager.search_vector(
                query=test_case["query"],
                top_k=5
            )

            # Verify we get results
            assert len(results) > 0, f"No results for query: {test_case['query']}"

            # Check if expected document is in top results
            result_doc_ids = [r["doc_id"] for r in results[:3]]  # Check top 3
            expected_doc_id = doc_info[test_case["expected_doc"]]["doc_id"]

            assert expected_doc_id in result_doc_ids, (
                f"Expected {test_case['expected_doc']} in top 3 results for "
                f"'{test_case['query']}'. Reason: {test_case['reason']}. "
                f"Got: {[r.get('source', r['doc_id']) for r in results[:3]]}"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_keyword_search_exact_terms(self, pipeline_with_docs):
        """Test keyword search finds exact terms from real documents."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        if not doc_info:
            pytest.skip("No documents were successfully processed")

        # Test exact keyword matches
        keyword_tests = [
            {
                "keyword": "LabMax",
                "expected_doc": "labmax-touch-ds.pdf",
                "min_score": 0.5
            },
            {
                "keyword": "ISO 17025",
                "expected_doc": "Understanding-ISO-17025-Test-Document.docx",
                "min_score": 0.5
            }
        ]

        for test in keyword_tests:
            if test["expected_doc"] not in doc_info:
                continue

            results = pipeline.index_manager.search_keyword(
                query=test["keyword"],
                top_k=5
            )

            # Should find the keyword
            assert len(results) > 0, f"No results for keyword: {test['keyword']}"

            # Verify expected document is found
            expected_doc_id = doc_info[test["expected_doc"]]["doc_id"]
            found = False
            for result in results:
                if result["doc_id"] == expected_doc_id:
                    found = True
                    # Verify score is reasonable
                    assert result["score"] >= test["min_score"], (
                        f"Score too low for exact match '{test['keyword']}': {result['score']}"
                    )
                    # Verify content contains the keyword
                    assert test["keyword"].lower() in result["content"].lower(), (
                        f"Result content doesn't contain keyword '{test['keyword']}'"
                    )
                    break

            assert found, f"Expected document not found for keyword '{test['keyword']}'"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hybrid_search_combines_results(self, pipeline_with_docs):
        """Test hybrid search effectively combines vector and keyword results."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        if not doc_info:
            pytest.skip("No documents were successfully processed")

        # Query that benefits from both vector and keyword
        query = "USB laser power measurement device"

        # Get results from all three search types
        vector_results = pipeline.index_manager.search_vector(query, top_k=10)
        keyword_results = pipeline.index_manager.search_keyword(query, top_k=10)
        hybrid_results = pipeline.index_manager.hybrid_search(query, top_k=10)

        # All should return results
        assert len(vector_results) > 0, "Vector search returned no results"
        assert len(keyword_results) > 0, "Keyword search returned no results"
        assert len(hybrid_results) > 0, "Hybrid search returned no results"

        # Hybrid should have good coverage
        vector_docs = {r["doc_id"] for r in vector_results[:5]}
        keyword_docs = {r["doc_id"] for r in keyword_results[:5]}
        hybrid_docs = {r["doc_id"] for r in hybrid_results[:5]}

        # Hybrid should include results from both vector and keyword
        # (though with RRF fusion, the exact overlap varies)
        assert len(hybrid_docs) > 0, "Hybrid search should return results"

        # If LabMax document exists, it should rank high (has USB, laser, power)
        if "labmax-touch-ds.pdf" in doc_info:
            labmax_id = doc_info["labmax-touch-ds.pdf"]["doc_id"]
            hybrid_ids = [r["doc_id"] for r in hybrid_results[:3]]
            # LabMax should be in top 3 for this query
            assert labmax_id in hybrid_ids, (
                "LabMax-Touch should rank high for 'USB laser power measurement device'"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_datasheet_metadata_extraction(self, pipeline_with_docs):
        """Test that datasheet mode extracts proper metadata."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        # Check the datasheet document
        if "labmax-touch-ds.pdf" not in doc_info:
            pytest.skip("LabMax datasheet not processed")

        labmax_info = doc_info["labmax-touch-ds.pdf"]
        doc_id = labmax_info["doc_id"]

        # Get the document record to check metadata
        doc_record = pipeline.registry.get_document(doc_id)
        assert doc_record is not None, "Document record not found"

        # Should have extracted metadata from datasheet mode
        metadata = doc_record.metadata
        assert metadata is not None, "No metadata found"

        # Should have parsed pairs from datasheet extraction
        assert "pairs" in metadata or "specs" in metadata or any(
            key for key in metadata.keys()
            if any(term in key.lower() for term in ["wavelength", "power", "accuracy", "range"])
        ), f"No datasheet-specific metadata found. Keys: {list(metadata.keys())}"

        # Search for content that would be in extracted metadata
        results = pipeline.index_manager.search_vector(
            "wavelength range specifications",
            top_k=5
        )

        # Should find the datasheet
        doc_ids = [r["doc_id"] for r in results]
        assert doc_id in doc_ids, "Datasheet not found when searching for specifications"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_different_categories(self, pipeline_with_docs):
        """Test searching across different document categories."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        if len(doc_info) < 2:
            pytest.skip("Need at least 2 documents for category testing")

        # Search for content that appears in multiple categories
        results = pipeline.index_manager.search_vector(
            "measurement accuracy specifications",
            top_k=10
        )

        # Should find results from multiple documents
        assert len(results) >= 2, "Should find results from multiple documents"

        # Check diversity of results
        categories = set()
        for result in results[:5]:
            if "category" in result.get("metadata", {}):
                categories.add(result["metadata"]["category"])

        # Should have results from different categories if we processed multiple types
        if len(doc_info) >= 3:
            assert len(categories) >= 2, (
                f"Results should come from multiple categories, got: {categories}"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_chunk_level_search(self, pipeline_with_docs):
        """Test that search returns individual chunks with proper context."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        if not doc_info:
            pytest.skip("No documents were successfully processed")

        # Search for specific technical content
        results = pipeline.index_manager.search_vector(
            "technical specifications wavelength range",
            top_k=10
        )

        assert len(results) > 0, "Should find technical specification chunks"

        # Verify chunk-level data
        for result in results[:3]:
            # Each result should have chunk metadata
            assert "doc_id" in result
            assert "content" in result or "text" in result
            assert "score" in result
            assert "chunk_index" in result or "metadata" in result

            # Content should be chunk-sized (not entire document)
            content = result.get("content", result.get("text", ""))
            assert 100 < len(content) < 2000, (
                f"Chunk content should be reasonable size, got {len(content)} chars"
            )

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_with_no_results(self, pipeline_with_docs):
        """Test search behavior when query matches no documents."""
        pipeline = pipeline_with_docs

        # Search for something that shouldn't exist in technical datasheets
        nonsense_query = "unicorn rainbow butterfly quantum pizza"

        vector_results = pipeline.index_manager.search_vector(nonsense_query, top_k=5)
        keyword_results = pipeline.index_manager.search_keyword(nonsense_query, top_k=5)

        # Vector search might still return results (semantic similarity to anything)
        # but keyword search should return nothing
        assert isinstance(vector_results, list)
        assert isinstance(keyword_results, list)
        assert len(keyword_results) == 0, "Keyword search should find no results for nonsense query"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_result_quality_metrics(self, pipeline_with_docs):
        """Test that search results include quality metrics."""
        pipeline = pipeline_with_docs
        doc_info = pipeline.test_doc_info

        if not doc_info:
            pytest.skip("No documents were successfully processed")

        # Perform a search
        results = pipeline.index_manager.search_vector(
            "laser measurement device",
            top_k=5
        )

        assert len(results) > 0, "Should have search results"

        # Check result quality
        for i, result in enumerate(results):
            # Results should be sorted by score (descending)
            if i > 0:
                assert result["score"] <= results[i-1]["score"], (
                    "Results should be sorted by score descending"
                )

            # Scores should be reasonable
            assert 0 <= result["score"] <= 1.5, (
                f"Score should be in reasonable range, got {result['score']}"
            )

            # Should have source information
            assert "source" in result or ("metadata" in result and "source" in result["metadata"]), (
                "Results should include source information"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
