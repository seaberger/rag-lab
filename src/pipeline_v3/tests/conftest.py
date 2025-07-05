"""
Pytest configuration for Pipeline v3 tests.
Provides fixtures for test isolation, database management, and pre-populated test data.
"""

import asyncio
import contextlib
import os
import shutil

# Add parent directory for imports
import sys
import uuid
from pathlib import Path

import pytest
import pytest_asyncio

# Import cleanup fixtures

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.enhanced_core import EnhancedPipeline
from qdrant_client import QdrantClient
from qdrant_client.http import exceptions as qdrant_exceptions

from utils.config import PipelineConfig

# Test environment name
TEST_ENVIRONMENT = "test_env"


@contextlib.contextmanager
def qdrant_client_context(config):
    """Context manager for Qdrant client with proper cleanup."""
    client = None
    try:
        client = QdrantClient(
            host=config.qdrant.server.host,
            port=config.qdrant.server.port,
            timeout=10,
        )
        yield client
    finally:
        if client:
            try:
                client.close()
            except Exception as e:
                print(f"Warning: Error closing Qdrant client: {e}")


def ensure_database_connections_closed():
    """Force close any lingering database connections."""
    import gc
    import sqlite3

    # Force garbage collection to close any lingering connections
    gc.collect()

    # Try to close any open SQLite connections
    try:
        # This is a bit of a hack, but helps with SQLite connection cleanup
        for obj in gc.get_objects():
            if isinstance(obj, sqlite3.Connection):
                with contextlib.suppress(Exception):
                    obj.close()
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture(scope="session")
def ensure_qdrant_server():
    """Ensure Qdrant server is running for tests that require it.

    This fixture should be explicitly requested by tests that need Qdrant.
    Tests that don't need Qdrant won't be affected.
    """
    try:
        # Try to connect to the Qdrant server
        client = QdrantClient(host="localhost", port=6333, timeout=5)
        client.get_collections()
        client.close()
        print("✓ Qdrant server is running")
    except (qdrant_exceptions.UnexpectedResponse, ConnectionError, Exception) as e:
        # In CI/CD, the service should be running for main test job
        # Compatibility tests will skip these tests with the marker
        if os.getenv("CI"):
            pytest.fail(f"Qdrant server is not running in CI environment: {e}")
        else:
            pytest.skip(
                f"Qdrant server is not running. Start it with: ./scripts/qdrant_server.sh start\nError: {e}"
            )


@pytest.fixture
def qdrant_required(ensure_qdrant_server):
    """Fixture to explicitly require Qdrant for a test.

    Use this fixture in tests that need Qdrant connectivity.
    """
    return True


def create_test_config(
    base_path: Path, environment: str = TEST_ENVIRONMENT, unique_id: str | None = None
) -> PipelineConfig:
    """Create a test configuration with isolated databases and unique collection names."""
    config = PipelineConfig()

    # Generate unique identifier for this test instance (use UUID for better uniqueness)
    if unique_id is None:
        unique_id = str(uuid.uuid4()).replace("-", "")[:12]  # 12 char unique ID

    # Create environment-specific paths with unique ID
    env_path = base_path / f"{environment}_{unique_id}"
    env_path.mkdir(exist_ok=True)

    # Override all database and storage paths
    config.storage.base_dir = str(env_path / "storage_data")
    config.storage.keyword_db_path = str(env_path / "keyword_index.db")
    config.storage.document_registry_path = str(env_path / "document_registry.db")

    config.cache.directory = str(env_path / "cache")
    # Configure Qdrant for server mode (baseline for all tests)
    config.qdrant.mode = "server"
    # Create unique collection name per test to avoid conflicts
    config.qdrant.collection_name = f"datasheets_{environment}_{unique_id}"

    config.job_queue.job_storage_path = str(env_path / "jobs.db")
    config.fingerprint.storage_path = str(env_path / "fingerprints.db")

    # Faster settings for tests
    config.pipeline.timeout_per_page = 10
    config.chunking.chunk_size = 512
    config.chunking.chunk_overlap = 50

    return config


def cleanup_qdrant_resources(pipeline_or_index_manager, config=None):
    """Properly cleanup Qdrant connections and resources with retry logic."""
    import time

    max_retries = 3
    retry_delay = 1.0

    try:
        # Handle both pipeline and index_manager objects
        if hasattr(pipeline_or_index_manager, "index_manager"):
            index_manager = pipeline_or_index_manager.index_manager
            if not config and hasattr(pipeline_or_index_manager, "config"):
                config = pipeline_or_index_manager.config
        else:
            index_manager = pipeline_or_index_manager

        # In server mode, delete the test collection with retries
        if config and config.qdrant.mode == "server" and hasattr(index_manager, "qdrant_client"):
            for attempt in range(max_retries):
                try:
                    if index_manager.qdrant_client:
                        # Check if collection exists before trying to delete
                        collections = index_manager.qdrant_client.get_collections().collections
                        collection_names = [c.name for c in collections]
                        if config.qdrant.collection_name in collection_names:
                            index_manager.qdrant_client.delete_collection(
                                config.qdrant.collection_name
                            )
                            print(
                                f"Successfully deleted test collection: {config.qdrant.collection_name}"
                            )
                        break
                except Exception as e:
                    if attempt < max_retries - 1:
                        print(f"Retry {attempt + 1}/{max_retries} collection deletion: {e}")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        print(
                            f"Warning: Failed to delete test collection after {max_retries} attempts: {e}"
                        )

        # Close Qdrant client connection if it exists
        if hasattr(index_manager, "qdrant_client") and index_manager.qdrant_client:
            try:
                index_manager.qdrant_client.close()
            except Exception as e:
                print(f"Warning: Error closing Qdrant client: {e}")

        # Clear vector store reference
        if hasattr(index_manager, "vector_store"):
            index_manager.vector_store = None

        # Clear client reference
        if hasattr(index_manager, "qdrant_client"):
            index_manager.qdrant_client = None

    except Exception as e:
        print(f"Warning: Error during Qdrant cleanup: {e}")


def clear_test_databases(config: PipelineConfig):
    """Clear all test databases and storage with improved error handling."""
    import time

    max_retries = 3
    retry_delay = 0.5

    # Remove entire storage directory with retries
    storage_dir = Path(config.storage.base_dir)
    if storage_dir.exists():
        for attempt in range(max_retries):
            try:
                shutil.rmtree(storage_dir)
                break
            except OSError as e:
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} storage cleanup: {e}")
                    time.sleep(retry_delay)
                else:
                    print(f"Warning: Could not remove storage directory: {e}")

    # Remove cache with retries
    cache_dir = Path(config.cache.directory)
    if cache_dir.exists():
        for attempt in range(max_retries):
            try:
                shutil.rmtree(cache_dir)
                break
            except OSError as e:
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} cache cleanup: {e}")
                    time.sleep(retry_delay)
                else:
                    print(f"Warning: Could not remove cache directory: {e}")

    # Handle Qdrant cleanup based on mode
    if config.qdrant.mode == "server":
        # For server mode, delete the test collection if it exists
        for attempt in range(max_retries):
            try:
                with qdrant_client_context(config) as client:
                    # Check if collection exists and delete it
                    collections = client.get_collections()
                    collection_names = [col.name for col in collections.collections]
                    if config.qdrant.collection_name in collection_names:
                        client.delete_collection(config.qdrant.collection_name)
                        print(f"Deleted test collection: {config.qdrant.collection_name}")
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"Retry {attempt + 1}/{max_retries} Qdrant cleanup: {e}")
                    time.sleep(retry_delay * (attempt + 1))  # Increasing delay
                else:
                    print(f"Warning: Could not clean up Qdrant collection: {e}")
    else:
        # For local mode, remove Qdrant data directory
        qdrant_dir = Path(config.qdrant.path)
        if qdrant_dir.exists():
            try:
                shutil.rmtree(qdrant_dir)
            except OSError as e:
                print(f"Warning: Could not remove Qdrant directory: {e}")

    # Remove individual database files with retries
    db_paths = [
        config.storage.keyword_db_path,
        config.storage.document_registry_path,
        config.job_queue.job_storage_path,
        config.fingerprint.storage_path,
    ]

    for db_path in db_paths:
        db_file = Path(db_path)
        if db_file.exists():
            for attempt in range(max_retries):
                try:
                    db_file.unlink()
                    break
                except OSError as e:
                    if attempt < max_retries - 1:
                        print(f"Retry {attempt + 1}/{max_retries} removing {db_file.name}: {e}")
                        time.sleep(retry_delay)
                    else:
                        print(f"Warning: Could not remove {db_file.name}: {e}")


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
    paths_to_create = [
        config.storage.base_dir,
        config.cache.directory,
        Path(config.job_queue.job_storage_path).parent,
        Path(config.fingerprint.storage_path).parent,
    ]

    # Only create qdrant path for local mode
    if config.qdrant.mode == "local":
        paths_to_create.append(config.qdrant.path)

    for path in paths_to_create:
        Path(path).mkdir(parents=True, exist_ok=True)

    yield config

    # Ensure all database connections are closed
    ensure_database_connections_closed()

    # Optionally clear after test (comment out for debugging)
    # clear_test_databases(config)


@pytest_asyncio.fixture
async def test_pipeline(test_config):
    """Provide an initialized test pipeline with proper cleanup."""
    pipeline = None
    try:
        pipeline = EnhancedPipeline(test_config)

        # Wait for Qdrant to be ready
        import time

        max_wait = 10
        wait_time = 0.5
        for _ in range(int(max_wait / wait_time)):
            try:
                if (
                    hasattr(pipeline.index_manager, "qdrant_client")
                    and pipeline.index_manager.qdrant_client
                ):
                    # Test connection
                    pipeline.index_manager.qdrant_client.get_collections()
                    break
            except Exception:
                time.sleep(wait_time)

        yield pipeline

    finally:
        # Proper cleanup of Qdrant resources
        if pipeline:
            cleanup_qdrant_resources(pipeline, test_config)

        # Optional: Clear databases if needed for this specific test
        # clear_test_databases(test_config)


@pytest_asyncio.fixture
async def populated_pipeline(test_pipeline, test_config):
    """Provide a pipeline with pre-populated test data."""
    pipeline = test_pipeline

    # Add a small test document
    test_doc_path = Path("data/sample_docs/FieldMaxII-Meter-Family-Data-Sheet_FORMFIRST.pdf")

    if test_doc_path.exists():
        # Process document WITH keywords to enable keyword search tests
        result = await pipeline.process_document(
            str(test_doc_path),
            metadata={
                "source": "test_fixture",
                "document_type": "datasheet",
                "test_doc": "fieldmax",
            },
            with_keywords=True,  # Enable keyword indexing for search tests
        )

        # Store the doc_id for tests to use
        pipeline.test_doc_id = result.get("doc_id") if result else None

    yield pipeline

    # Cleanup is handled by test_pipeline fixture


@pytest.fixture
def sample_documents():
    """Provide paths to sample documents for testing."""
    # Find the project root by looking for the data directory
    current_dir = Path(__file__).parent
    while current_dir != current_dir.parent:
        if (current_dir / "data" / "sample_docs").exists():
            sample_dir = current_dir / "data" / "sample_docs"
            break
        current_dir = current_dir.parent
    else:
        # Fallback to absolute path if needed
        sample_dir = Path("/Users/seanbergman/Repositories/rag_lab/data/sample_docs")

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
            "keywords": [
                "FieldMaxII",
                "laser",
                "power",
                "meter",
                "thermopile",
                "optical",
            ],
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
    config.addinivalue_line("markers", "security: marks security-focused tests")
    config.addinivalue_line("markers", "unit: marks unit tests (fast, isolated)")
    config.addinivalue_line(
        "markers", "requires_qdrant_server: marks tests that require Qdrant server"
    )


# Skip tests if no API key
def pytest_collection_modifyitems(config, items):
    """Skip tests that require API keys if not available."""
    if not os.getenv("OPENAI_API_KEY"):
        skip_api = pytest.mark.skip(reason="OPENAI_API_KEY not set")
        for item in items:
            if "requires_api" in item.keywords:
                item.add_marker(skip_api)
