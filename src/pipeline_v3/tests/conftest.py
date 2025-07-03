"""
Pytest configuration for Pipeline v3 tests.
Provides fixtures for test isolation, database management, and pre-populated test data.
"""

import asyncio
import os
import shutil

# Add parent directory for imports
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from pipeline_v3.pipeline.enhanced_core import EnhancedPipeline
from pipeline_v3.utils.config import PipelineConfig

# Test environment name
TEST_ENVIRONMENT = "test_env"


def create_test_config(base_path: Path, environment: str = TEST_ENVIRONMENT) -> PipelineConfig:
    """Create a test configuration with isolated databases."""
    config = PipelineConfig()

    # Create environment-specific paths
    env_path = base_path / environment
    env_path.mkdir(exist_ok=True)

    # Override all database and storage paths
    config.storage.base_dir = str(env_path / "storage_data")
    config.storage.keyword_db_path = str(env_path / "keyword_index.db")
    config.storage.document_registry_path = str(env_path / "document_registry.db")

    config.cache.directory = str(env_path / "cache")
    config.qdrant.path = str(env_path / "qdrant_data")
    config.qdrant.collection_name = f"datasheets_{environment}"

    config.job_queue.job_storage_path = str(env_path / "jobs.db")
    config.fingerprint.storage_path = str(env_path / "fingerprints.db")

    # Faster settings for tests
    config.pipeline.timeout_per_page = 10
    config.chunking.chunk_size = 512
    config.chunking.chunk_overlap = 50

    return config


def clear_test_databases(config: PipelineConfig):
    """Clear all test databases and storage."""
    # Remove entire storage directory
    storage_dir = Path(config.storage.base_dir)
    if storage_dir.exists():
        shutil.rmtree(storage_dir)

    # Remove cache
    cache_dir = Path(config.cache.directory)
    if cache_dir.exists():
        shutil.rmtree(cache_dir)

    # Remove Qdrant data
    qdrant_dir = Path(config.qdrant.path)
    if qdrant_dir.exists():
        shutil.rmtree(qdrant_dir)

    # Remove individual database files
    for db_path in [
        config.storage.keyword_db_path,
        config.storage.document_registry_path,
        config.job_queue.job_storage_path,
        config.fingerprint.storage_path,
    ]:
        db_file = Path(db_path)
        if db_file.exists():
            db_file.unlink()


@pytest.fixture(scope="session")
def test_base_dir():
    """Provide a base directory for all test data."""
    # Use a known location instead of temp for easier debugging
    base_dir = Path("./test_data")
    base_dir.mkdir(exist_ok=True)
    yield base_dir
    # Don't remove after tests for debugging
    # shutil.rmtree(base_dir)


@pytest.fixture(scope="function")
def test_config(test_base_dir):
    """Provide a test configuration with clean databases."""
    config = create_test_config(test_base_dir)

    # Clear any existing test data
    clear_test_databases(config)

    # Ensure directories exist
    for path in [
        config.storage.base_dir,
        config.cache.directory,
        config.qdrant.path,
        Path(config.job_queue.job_storage_path).parent,
        Path(config.fingerprint.storage_path).parent,
    ]:
        Path(path).mkdir(parents=True, exist_ok=True)

    yield config

    # Optionally clear after test (comment out for debugging)
    # clear_test_databases(config)


@pytest_asyncio.fixture
async def test_pipeline(test_config):
    """Provide an initialized test pipeline."""
    pipeline = EnhancedPipeline(test_config)
    yield pipeline
    # No cleanup needed - databases cleared by test_config fixture


@pytest_asyncio.fixture
async def populated_pipeline(test_pipeline, test_config):
    """Provide a pipeline with pre-populated test data."""
    pipeline = test_pipeline

    # Add a small test document
    test_doc_path = Path("data/sample_docs/FieldMaxII-Meter-Family-Data-Sheet_FORMFIRST.pdf")

    if test_doc_path.exists():
        # Process document without keywords for speed
        result = await pipeline.process_document(
            str(test_doc_path),
            metadata={
                "source": "test_fixture",
                "document_type": "datasheet",
                "test_doc": "fieldmax",
            },
            with_keywords=False,
        )

        # Store the doc_id for tests to use
        pipeline.test_doc_id = result.get("doc_id") if result else None

    yield pipeline


@pytest.fixture
def sample_documents():
    """Provide paths to sample documents for testing."""
    sample_dir = Path("data/sample_docs")

    return {
        "small_datasheet": sample_dir / "FieldMaxII-Meter-Family-Data-Sheet_FORMFIRST.pdf",
        "medium_datasheet": sample_dir / "labmax-touch-ds.pdf",
        "large_datasheet": sample_dir / "COHR_PowerMax-USB_UV-VIS_DS_0920_2.pdf",
        "non_datasheet": sample_dir / "Laser Measurement Product Selection.pdf",
        "word_doc": sample_dir / "Understanding-ISO-17025-Test-Document.docx",
        "powerpoint": sample_dir / "ISO-17025-Calibration-Standards-Presentation.pptx",
    }


@pytest.fixture
def expected_content():
    """Provide expected content for assertions."""
    return {
        "fieldmax": {
            "part_numbers": ["1098580", "1098579", "1098581"],
            "keywords": ["FieldMaxII", "laser", "power", "meter", "thermopile", "optical"],
            "model_names": ["FieldMaxII-TOP", "FieldMaxII-TO", "FieldMaxII-P"],
        },
        "labmax": {
            "keywords": ["LabMax", "Touch", "laser", "power", "measurement", "sensor"],
            "features": ["touchscreen", "USB", "real-time"],
        },
    }


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Mark slow tests
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line("markers", "integration: marks tests as integration tests")
    config.addinivalue_line("markers", "requires_api: marks tests that require API keys")


# Skip tests if no API key
def pytest_collection_modifyitems(config, items):
    """Skip tests that require API keys if not available."""
    if not os.getenv("OPENAI_API_KEY"):
        skip_api = pytest.mark.skip(reason="OPENAI_API_KEY not set")
        for item in items:
            if "requires_api" in item.keywords:
                item.add_marker(skip_api)
