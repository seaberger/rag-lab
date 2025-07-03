"""
Unit tests for the Cache component.

Tests cover cache operations, compression, and TTL management.
"""

import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from storage.cache import CacheManager

from utils.config import PipelineConfig


class TestCacheManager:
    """Test suite for CacheManager functionality."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for cache."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    @pytest.fixture
    def cache(self, temp_dir):
        """Create a test cache instance."""
        config = PipelineConfig()
        config.cache.directory = temp_dir
        config.cache.ttl_days = 7
        config.cache.compress = True
        return CacheManager(config=config)

    def _get_hash(self, content: str) -> str:
        """Generate hash for testing."""
        return hashlib.sha256(content.encode()).hexdigest()

    def test_basic_cache_operations(self, cache):
        """Test basic get/put operations."""
        # Test data
        doc_hash = self._get_hash("document content")
        prompt_hash = self._get_hash("prompt content")
        test_data = {"key": "value", "number": 42}

        # Test putting data
        success = cache.put(doc_hash, prompt_hash, test_data)
        assert success

        # Test getting the data
        retrieved = cache.get(doc_hash, prompt_hash)
        assert retrieved == test_data

        # Test cache hit statistics
        assert cache.stats["hits"] == 1

        # Test non-existent key
        assert cache.get("non_existent", "non_existent") is None
        assert cache.stats["misses"] == 1

    def test_cache_with_large_data(self, cache):
        """Test caching large data with compression."""
        # Create large data
        doc_hash = self._get_hash("large document")
        prompt_hash = self._get_hash("large prompt")
        large_data = {
            "items": [f"item_{i}" * 100 for i in range(1000)]
        }

        # Cache it
        success = cache.put(doc_hash, prompt_hash, large_data)
        assert success

        # Retrieve and verify
        retrieved = cache.get(doc_hash, prompt_hash)
        assert retrieved == large_data
        assert len(retrieved["items"]) == 1000

    def test_cache_ttl(self, cache):
        """Test cache TTL functionality."""
        # Create cache with short TTL
        config = PipelineConfig()
        config.cache.directory = cache.cache_dir
        config.cache.ttl_days = 0.00001  # Very short TTL (about 1 second)
        config.cache.compress = True
        short_cache = CacheManager(config=config)

        # Put value
        doc_hash = self._get_hash("ttl test")
        prompt_hash = self._get_hash("ttl prompt")
        short_cache.put(doc_hash, prompt_hash, {"data": "test"})

        # Verify it exists
        assert short_cache.get(doc_hash, prompt_hash) is not None

        # Wait for TTL to expire
        time.sleep(2)

        # Should be expired now
        assert short_cache.get(doc_hash, prompt_hash) is None

    def test_cache_clear(self, cache):
        """Test cache clearing functionality."""
        # Put multiple values
        for i in range(5):
            doc_hash = self._get_hash(f"doc{i}")
            prompt_hash = self._get_hash(f"prompt{i}")
            cache.put(doc_hash, prompt_hash, {"data": i})

        # Verify files exist
        cache_files = list(cache.cache_dir.glob("*.json*"))
        assert len(cache_files) == 5

        # Clear cache
        cleared = cache.clear()
        assert cleared == 5

        # Verify files are gone
        cache_files = list(cache.cache_dir.glob("*.json*"))
        assert len(cache_files) == 0

    def test_cache_clear_with_age_filter(self, cache):
        """Test clearing only old cache entries."""
        # Put a value
        doc_hash = self._get_hash("old doc")
        prompt_hash = self._get_hash("old prompt")
        cache.put(doc_hash, prompt_hash, {"data": "old"})

        # Manually modify the file's modification time to make it old
        cache_file = next(iter(cache.cache_dir.glob("*.json*")))
        old_time = time.time() - (10 * 24 * 60 * 60)  # 10 days ago
        os.utime(cache_file, (old_time, old_time))

        # Put a new value
        new_doc_hash = self._get_hash("new doc")
        new_prompt_hash = self._get_hash("new prompt")
        cache.put(new_doc_hash, new_prompt_hash, {"data": "new"})

        # Clear only items older than 5 days
        cleared = cache.clear(older_than_days=5)
        assert cleared == 1

        # New item should still exist
        assert cache.get(new_doc_hash, new_prompt_hash) is not None
        # Old item should be gone
        assert cache.get(doc_hash, prompt_hash) is None

    def test_cache_stats(self, cache):
        """Test cache statistics functionality."""
        # Put some values
        for i in range(3):
            doc_hash = self._get_hash(f"doc{i}")
            prompt_hash = self._get_hash(f"prompt{i}")
            cache.put(doc_hash, prompt_hash, {"data": i})

        # Get some values (hits and misses)
        cache.get(self._get_hash("doc0"), self._get_hash("prompt0"))  # Hit
        cache.get(self._get_hash("doc1"), self._get_hash("prompt1"))  # Hit
        cache.get("non_existent", "non_existent")  # Miss

        # Get stats
        stats = cache.get_stats()

        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["errors"] == 0
        assert stats["hit_rate"] == 2/3
        assert stats["cache_files"] == 3
        assert stats["cache_size_mb"] > 0

    def test_cache_without_compression(self, cache):
        """Test cache operations without compression."""
        # Create cache without compression
        config = PipelineConfig()
        config.cache.directory = cache.cache_dir
        config.cache.compress = False
        no_compress_cache = CacheManager(config=config)

        # Test data
        doc_hash = self._get_hash("no compress doc")
        prompt_hash = self._get_hash("no compress prompt")
        test_data = {"key": "value", "list": [1, 2, 3, 4, 5]}

        # Put and get
        no_compress_cache.put(doc_hash, prompt_hash, test_data)
        retrieved = no_compress_cache.get(doc_hash, prompt_hash)
        assert retrieved == test_data

        # Verify it's stored as plain JSON
        cache_files = list(no_compress_cache.cache_dir.glob("*.json"))
        assert len(cache_files) == 1
        with open(cache_files[0]) as f:
            stored_data = json.load(f)
        assert stored_data == test_data

    def test_cache_error_handling(self, cache):
        """Test cache error handling."""
        # Test with invalid data that can't be JSON serialized
        doc_hash = self._get_hash("error doc")
        prompt_hash = self._get_hash("error prompt")

        # This should handle the error gracefully
        class NonSerializable:
            pass

        invalid_data = {"obj": NonSerializable()}
        success = cache.put(doc_hash, prompt_hash, invalid_data)
        assert not success  # Should fail gracefully

        # Stats should reflect the error
        assert cache.stats["errors"] == 1

    def test_cache_key_generation(self, cache):
        """Test cache key generation."""
        # Same content should generate same key
        doc_hash1 = self._get_hash("same content")
        prompt_hash1 = self._get_hash("same prompt")

        doc_hash2 = self._get_hash("same content")
        prompt_hash2 = self._get_hash("same prompt")

        assert doc_hash1 == doc_hash2
        assert prompt_hash1 == prompt_hash2

        # Different content should generate different keys
        doc_hash3 = self._get_hash("different content")
        prompt_hash3 = self._get_hash("different prompt")

        assert doc_hash1 != doc_hash3
        assert prompt_hash1 != prompt_hash3

    def test_cache_file_structure(self, cache):
        """Test the cache file structure."""
        # Put a value
        doc_hash = self._get_hash("structure test")
        prompt_hash = self._get_hash("structure prompt")
        test_data = {"content": "test"}
        cache.put(doc_hash, prompt_hash, test_data)

        # Check that file exists with expected pattern
        cache_files = list(cache.cache_dir.glob("*.json.lz4"))
        assert len(cache_files) == 1

        # Verify the cache key format
        cache_key = cache._get_cache_key(doc_hash, prompt_hash)
        expected_filename = f"{cache_key}.json.lz4"
        assert cache_files[0].name == expected_filename


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
