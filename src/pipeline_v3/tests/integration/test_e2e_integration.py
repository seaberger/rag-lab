"""
End-to-End Integration Tests for Pipeline v3

Comprehensive integration tests with real documents to validate
the complete pipeline functionality before production deployment.

Note: Tests are now designed to be independent using proper fixtures
instead of relying on alphabetical execution order.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio
import yaml

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.index_manager import IndexManager
from core.registry import DocumentRegistry
from job_queue.manager import DocumentQueue
from pipeline.enhanced_core import EnhancedPipeline
from utils.config import PipelineConfig
from utils.monitoring import ProgressMonitor


@pytest.mark.requires_qdrant_server
class TestE2EIntegration:
    """End-to-end integration tests with real documents.

    Tests are independent and use proper fixtures for data setup.
    """

    def get_test_documents(self, test_docs_path: Path, limit: int = 5) -> list[Path]:
        """Get list of test documents."""
        if not test_docs_path.exists():
            pytest.skip(f"Test docs path not found: {test_docs_path}")

        # Get PDF files
        pdf_files = list(test_docs_path.glob("*.pdf"))
        pdf_files = [f for f in pdf_files if not f.name.endswith("Zone.Identifier")]

        if not pdf_files:
            pytest.skip("No PDF files found for testing")

        # Limit to specified number of files for faster testing
        return pdf_files[:limit]

    @pytest.mark.asyncio
    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.heavy
    @pytest.mark.requires_api
    @pytest.mark.timeout(900)  # 15 minutes for heavy operations
    async def test_document_ingestion(
        self, test_pipeline, sample_documents, expected_content
    ):
        """Test document ingestion with real PDFs."""
        pipeline = test_pipeline

        # Use specific small datasheet for predictable testing
        doc_path = sample_documents["small_datasheet"]
        print(f"Looking for test document at: {doc_path}")
        print(f"Document exists: {doc_path.exists()}")
        if not doc_path.exists():
            # Try to list what's available in the parent directory
            parent = doc_path.parent
            if parent.exists():
                print(f"Files in {parent}: {list(parent.glob('*.pdf'))[:5]}")
            pytest.skip(f"Test document not found: {doc_path}")

        test_docs = [doc_path]

        ingestion_results = []

        for doc_path in test_docs:
            print(f"Processing document: {doc_path.name}")
            start_time = time.time()

            try:
                # Test document addition

                result = await pipeline.process_document(
                    str(doc_path),
                    metadata={
                        "source": "integration_test",
                        "document_type": "datasheet",
                        "test_timestamp": time.time(),
                    },
                )

                processing_time = time.time() - start_time

                ingestion_results.append(
                    {
                        "document": doc_path.name,
                        "success": True,
                        "processing_time": processing_time,
                        "result": result,
                    }
                )

                # Verify the document was processed
                assert result is not None, f"Result is None for {doc_path.name}"
                assert "doc_id" in result, f"No doc_id in result: {result}"
                assert result.get("status") == "success", f"Status is not success: {result}"
                assert result.get("action") == "indexed", f"Action is not indexed: {result}"

                # Check the enhanced markdown was extracted
                if "enhanced_markdown" in result:
                    markdown = result["enhanced_markdown"]
                    # Check for expected content from FieldMax datasheet
                    fieldmax_expected = expected_content["fieldmax"]

                    # Check part numbers
                    for part_num in fieldmax_expected["part_numbers"]:
                        assert (
                            part_num in markdown
                        ), f"Expected part number {part_num} not found"

                    # Check keywords
                    for keyword in fieldmax_expected["keywords"][:3]:  # Check first 3
                        assert (
                            keyword in markdown
                        ), f"Expected keyword {keyword} not found"

                    # Check model names
                    for model in fieldmax_expected["model_names"]:
                        assert model in markdown, f"Expected model {model} not found"

            except Exception as e:
                pytest.fail(f"Document ingestion failed for {doc_path.name}: {e}")

        # Verify all documents were processed
        assert len(ingestion_results) == len(test_docs)
        assert all(r["success"] for r in ingestion_results)

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.e2e
    @pytest.mark.requires_api
    @pytest.mark.timeout(600)  # 10 minutes for search tests
    async def test_search_functionality(self, populated_pipeline, expected_content):
        """Test different search types with pre-populated data."""
        pipeline = populated_pipeline

        # Pipeline already has FieldMax document from populated_pipeline fixture

        # Test specific searches for FieldMax content
        test_cases = [
            # (query, search_type, expected_in_content)
            ("FieldMaxII", "keyword", ["FieldMaxII-TOP", "1098580"]),
            ("laser power meter", "keyword", ["Laser Power", "Energy Meters"]),
            ("thermopile optical sensors", "vector", ["thermopile", "optical"]),
            ("1098580", "keyword", ["FieldMaxII-TOP", "1098580"]),  # Part number search
            ("measurement accuracy", "hybrid", ["Accuracy", "Measurement"]),
        ]

        for query, search_type, expected_terms in test_cases:
            print(f"\nTesting {search_type} search for: {query}")
            try:
                results = pipeline.search(query, search_type=search_type, top_k=3)

                # Verify search returns results
                assert isinstance(results, list)
                assert (
                    len(results) > 0
                ), f"No results found for '{query}' with {search_type}"

                # Check first result contains expected content
                first_result = results[0]
                assert "content" in first_result or "text" in first_result
                assert "score" in first_result

                content = first_result.get("content", first_result.get("text", ""))

                # Verify at least one expected term is found
                found_any = False
                for term in expected_terms:
                    if term in content:
                        found_any = True
                        break

                assert (
                    found_any
                ), f"Expected terms {expected_terms} not found in search results for '{query}'"

            except Exception as e:
                pytest.fail(f"Search failed for '{query}' with {search_type}: {e}")

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.smoke
    @pytest.mark.timeout(300)  # 5 minutes for quick tests
    async def test_queue_management(self, test_pipeline):
        """Test queue operations."""
        pipeline = test_pipeline
        queue = pipeline.document_queue

        # Test queue status
        status = queue.get_status()
        assert isinstance(status, dict)
        assert "queue_status" in status
        assert "performance" in status

        # Test adding a job
        from job_queue.manager import JobPriority

        job_id = await queue.add_job(
            source="test.pdf",
            job_type="add",
            priority=JobPriority.NORMAL,
            metadata={"test": True},
        )
        assert job_id is not None

        # Test job status
        job_status = queue.get_job_status(job_id)
        assert job_status is not None
        assert job_status["status"] in ["pending", "processing", "completed", "failed"]

    @pytest.mark.asyncio
    async def test_system_status(self, test_pipeline):
        """Test system status and monitoring."""
        pipeline = test_pipeline

        # Test pipeline status
        pipeline_status = pipeline.get_comprehensive_status()
        assert isinstance(pipeline_status, dict)

        # Test registry statistics
        registry_stats = pipeline.registry.get_statistics()
        assert isinstance(registry_stats, dict)
        assert "total_documents" in registry_stats

        # Test index status
        index_status = pipeline.index_manager.get_statistics()
        assert isinstance(index_status, dict)

    @pytest.mark.asyncio
    async def test_cli_integration(self, test_config, test_base_dir):
        """Test CLI commands with real pipeline."""
        config = test_config
        temp_dir = test_base_dir / "test_env"

        # Ensure the directory exists
        temp_dir.mkdir(exist_ok=True)

        # Create a test PDF file
        test_pdf = temp_dir / "test.pdf"
        test_pdf.write_bytes(b"Mock PDF content")

        cli_tests = [
            (["python", "-m", "src.pipeline_v3.cli_main", "status"], "status command"),
            (
                ["python", "-m", "src.pipeline_v3.cli_main", "queue", "status"],
                "queue status",
            ),
            (
                ["python", "-m", "src.pipeline_v3.cli_main", "config", "list"],
                "config list",
            ),
        ]

        for cmd, description in cli_tests:
            try:
                # Set environment to use test config
                env = os.environ.copy()
                env["PIPELINE_CONFIG_PATH"] = str(temp_dir / "config.yaml")

                # Save test config
                config_data = {
                    "storage": {"base_dir": str(config.storage.base_dir)},
                    "cache": {"directory": str(config.cache.directory)},
                    "qdrant": {"path": str(config.qdrant.path)},
                }

                with open(temp_dir / "config.yaml", "w") as f:
                    yaml.dump(config_data, f)

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    cwd=str(Path(__file__).parent.parent.parent.parent.parent),
                    env=env,
                )

                # CLI commands should at least not crash
                assert result.returncode in [
                    0,
                    1,
                ], f"{description} failed with code {result.returncode}"

            except Exception as e:
                pytest.fail(f"CLI test '{description}' failed: {e}")

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_complete_pipeline_flow(self, test_pipeline, sample_documents):
        """Test complete pipeline flow: ingest -> search -> status."""
        pipeline = test_pipeline

        # Step 1: Ingest a document
        doc_path = sample_documents["small_datasheet"]

        result = await pipeline.process_document(
            str(doc_path), metadata={"source": "e2e_test", "document_type": "datasheet"}
        )
        assert result is not None

        # Step 2: Search for content
        search_results = pipeline.search("measurement", search_type="hybrid", top_k=5)
        assert isinstance(search_results, list)

        # Step 3: Verify system status shows the document
        status = pipeline.get_comprehensive_status()
        assert status["registry"]["total_documents"] >= 1
        assert status["indexes"]["vector_index"]["points_count"] >= 0
        assert status["indexes"]["keyword_index"]["entry_count"] >= 0


@pytest.mark.requires_qdrant_server
class TestSmokeIntegration:
    """Quick smoke tests for CI/CD - focused on speed over comprehensiveness."""

    @pytest_asyncio.fixture
    async def smoke_test_environment(self, tmp_path):
        """Set up lightweight test environment for smoke tests."""
        # Use our improved config creation with unique ID for smoke tests
        from ..conftest import create_test_config

        config = create_test_config(tmp_path, environment="smoke", unique_id=None)

        # Smoke test settings - optimized for speed
        config.job_queue.max_concurrent = 1  # Single threaded
        config.fingerprint.storage_path = str(tmp_path / "smoke_fingerprints.db")

        # Smaller chunks for faster processing
        config.chunking.chunk_size = 256
        config.chunking.chunk_overlap = 25

        # Initialize pipeline
        pipeline = EnhancedPipeline(config)

        yield {"config": config, "pipeline": pipeline, "temp_dir": tmp_path}

    @pytest.mark.asyncio
    @pytest.mark.smoke
    @pytest.mark.integration
    @pytest.mark.requires_api
    @pytest.mark.timeout(600)  # 10 minutes for smoke tests with API
    async def test_smoke_document_ingestion(self, smoke_test_environment):
        """Quick smoke test for document ingestion."""
        pipeline = smoke_test_environment["pipeline"]

        # Get only 2 documents for speed
        test_docs_path = Path("/Users/seanbergman/Repositories/rag_lab/data/lmc_docs")
        if not test_docs_path.exists():
            pytest.skip("Test docs not found")

        pdfs = list(test_docs_path.glob("*.pdf"))
        pdfs = [f for f in pdfs if not f.name.endswith("Zone.Identifier")][:2]

        if not pdfs:
            pytest.skip("No PDFs found")

        # Process just first document as smoke test
        doc_path = pdfs[0]
        result = await pipeline.process_document(
            str(doc_path),
            metadata={"source": "smoke_test", "document_type": "datasheet"},
        )

        assert result is not None
        assert "doc_id" in result or "document_id" in result

    @pytest.mark.asyncio
    @pytest.mark.smoke
    @pytest.mark.integration
    @pytest.mark.timeout(300)  # 5 minutes for search only
    async def test_smoke_keyword_search(self, smoke_test_environment):
        """Quick smoke test for keyword search only."""
        pipeline = smoke_test_environment["pipeline"]

        # Quick keyword searches
        test_queries = ["laser", "sensor", "power"]

        for query in test_queries:
            try:
                results = pipeline.search(query, search_type="keyword", top_k=3)
                assert isinstance(results, list)
            except Exception as e:
                if "No documents found" not in str(e):
                    pytest.fail(f"Keyword search failed: {e}")

    @pytest.mark.asyncio
    async def test_smoke_system_status(self, smoke_test_environment):
        """Quick smoke test for system status."""
        pipeline = smoke_test_environment["pipeline"]

        # Test basic status retrieval
        status = pipeline.get_comprehensive_status()
        assert isinstance(status, dict)

        registry_stats = pipeline.registry.get_statistics()
        assert isinstance(registry_stats, dict)

        queue_status = pipeline.document_queue.get_status()
        assert isinstance(queue_status, dict)


@pytest.mark.requires_qdrant_server
class TestDatabaseIsolation:
    """Test database isolation and environment separation.

    Tests are independent and use proper cleanup fixtures.
    """

    @pytest.mark.asyncio
    async def test_environment_isolation(self, test_base_dir, sample_documents):
        """Test that different environments have isolated databases."""
        from ..conftest import clear_test_databases, create_test_config

        # Create two different environments
        config1 = create_test_config(test_base_dir, "env1")
        config2 = create_test_config(test_base_dir, "env2")

        # Clear both environments
        clear_test_databases(config1)
        clear_test_databases(config2)

        # Initialize pipelines for both environments
        pipeline1 = EnhancedPipeline(config1)
        pipeline2 = EnhancedPipeline(config2)

        # Add a document to env1
        test_doc = sample_documents["small_datasheet"]
        if test_doc.exists():
            result1 = await pipeline1.process_document(
                str(test_doc), metadata={"env": "env1"}
            )
            assert result1 is not None

        # Search in env1 should find the document
        results1 = pipeline1.search("FieldMax", search_type="keyword")
        assert len(results1) > 0

        # Search in env2 should find nothing
        results2 = pipeline2.search("FieldMax", search_type="keyword")
        assert len(results2) == 0

        # Verify registry isolation
        assert pipeline1.registry.get_statistics()["total_documents"] == 1
        assert pipeline2.registry.get_statistics()["total_documents"] == 0

        # Clean up
        clear_test_databases(config1)
        clear_test_databases(config2)

    @pytest.mark.asyncio
    async def test_database_cleanup(self, test_config, test_pipeline, sample_documents):
        """Test that database cleanup works properly."""
        from ..conftest import clear_test_databases

        pipeline = test_pipeline

        # Add a document
        test_doc = sample_documents["small_datasheet"]
        if test_doc.exists():
            await pipeline.process_document(str(test_doc))

        # Verify document exists
        assert pipeline.registry.get_statistics()["total_documents"] == 1

        # Clear databases
        clear_test_databases(test_config)

        # Reinitialize pipeline with same config
        new_pipeline = EnhancedPipeline(test_config)

        # Verify database is empty
        assert new_pipeline.registry.get_statistics()["total_documents"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
