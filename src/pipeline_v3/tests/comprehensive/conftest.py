"""
Configuration and fixtures for comprehensive tests.

This conftest.py imports necessary fixtures from the parent conftest.py
to make them available for comprehensive tests.
"""

# Import all fixtures from parent conftest
import sys
from pathlib import Path

# Add parent directory to path to import from parent conftest
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Import fixtures from parent conftest

# Create temp_dirs fixture for comprehensive tests
import shutil
import tempfile

import pytest


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    temp_dir = tempfile.mkdtemp(prefix="comprehensive_test_")
    dirs = {
        "storage": Path(temp_dir) / "storage",
        "cache": Path(temp_dir) / "cache",
        "qdrant": Path(temp_dir) / "qdrant",
    }

    # Create all directories
    for dir_path in dirs.values():
        dir_path.mkdir(parents=True, exist_ok=True)

    yield dirs

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)
