"""
Cleanup fixtures for aggressive resource cleanup between tests.
"""

import contextlib
import gc
import time
from pathlib import Path

import pytest


@pytest.fixture(autouse=True, scope="function")
def cleanup_between_tests():
    """
    Aggressive cleanup between each test to prevent resource conflicts.

    This fixture runs automatically after each test to:
    1. Allow async operations to complete
    2. Force garbage collection
    3. Add a small delay for file system operations
    """
    yield

    # Allow async operations to complete
    time.sleep(0.1)

    # Force garbage collection to release file handles
    gc.collect()

    # Additional delay for file system operations
    time.sleep(0.05)


@pytest.fixture(autouse=True, scope="class")
def cleanup_between_test_classes():
    """
    More aggressive cleanup between test classes.

    Adds a longer delay between different test classes to ensure
    all resources are fully released.
    """
    yield

    # Longer delay between test classes
    time.sleep(0.5)
    gc.collect()
    time.sleep(0.1)


@pytest.fixture
def force_cleanup():
    """
    Manual cleanup fixture for tests that need extra cleanup.

    Usage:
        def test_something(force_cleanup):
            # test code
            force_cleanup()  # Force cleanup mid-test if needed
    """

    def cleanup():
        gc.collect()
        time.sleep(0.1)

    yield cleanup

    # Also cleanup after test
    cleanup()


def cleanup_qdrant_lock_files(base_path: Path):
    """
    Remove Qdrant lock files that might be left behind.

    Args:
        base_path: Path to Qdrant storage directory
    """
    if not base_path.exists():
        return

    # Look for lock files
    for lock_file in base_path.rglob("*.lock"):
        with contextlib.suppress(Exception):
            lock_file.unlink()


def close_all_database_connections():
    """
    Attempt to close any lingering database connections.
    """
    import sqlite3

    # Force SQLite to release all connections
    sqlite3.connect(":memory:").close()

    # Additional cleanup for any connection pools
    gc.collect()
