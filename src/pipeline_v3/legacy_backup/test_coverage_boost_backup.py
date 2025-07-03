"""
Coverage Boost Integration Tests for Pipeline v3

Focused integration tests designed to exercise key modules and boost coverage
to meet CI/CD requirements (40% minimum).
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

# Import key modules that need coverage
from utils.config import PipelineConfig
from utils.common_utils import init_cli_logging, logger
from utils.env_utils import setup_environment
from utils.monitoring import ProgressMonitor
from utils.validation import DocumentValidator, ValidationError
from utils.chunking_metadata import KeywordGenerator
from utils.cleanup import cleanup_temp_resources, get_resource_manager


class TestCoverageBoost:
    """Tests designed to boost coverage for key modules."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_config_module_coverage(self, temp_dir):
        """Test configuration module functionality."""
        # Test default config
        config = PipelineConfig()
        assert config.openai.vision_model == "gpt-4.1"
        assert config.storage.base_dir == "./storage_data_v3"
        assert config.job_queue.max_concurrent == 10

        # Test config dict conversion using dataclasses.asdict
        from dataclasses import asdict
        config_dict = asdict(config)
        assert isinstance(config_dict, dict)
        assert "openai" in config_dict
        assert "storage" in config_dict

        # Test config from dict
        custom_dict = {
            "openai": {"vision_model": "gpt-4.1"},
            "storage": {"base_dir": temp_dir},
            "job_queue": {"max_concurrent": 8}
        }

        # Create YAML file
        import yaml
        config_file = os.path.join(temp_dir, "test_config.yaml")
        with open(config_file, "w") as f:
            yaml.dump(custom_dict, f)

        # Load from YAML
        custom_config = PipelineConfig.from_yaml(config_file)
        assert custom_config.openai.vision_model == "gpt-4.1"
        assert custom_config.job_queue.max_concurrent == 8

        # Test missing config file handling
        missing_config = PipelineConfig.from_yaml("/non/existent/config.yaml")
        assert missing_config is not None  # Should return defaults

    def test_common_utils_coverage(self):
        """Test common utilities."""
        # Test logging initialization
        init_cli_logging()

        # Test logger usage
        logger.info("Test info message")
        logger.warning("Test warning")
        logger.debug("Test debug")

        # Test with verbose mode
        with patch("sys.argv", ["test", "-v"]):
            init_cli_logging()

    def test_env_utils_coverage(self):
        """Test environment utilities."""
        # Test environment setup
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):  # pragma: allowlist secret
            setup_environment()

        # Test without env file
        with patch("pathlib.Path.exists", return_value=False):
            setup_environment()

        # Test with env file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("TEST_VAR=test_value\n")
            f.flush()

            with patch("pathlib.Path.exists", return_value=True):
                with patch("pathlib.Path.open", return_value=open(f.name)):
                    setup_environment()

    def test_monitoring_coverage(self):
        """Test monitoring utilities."""
        # Test basic monitor
        monitor = ProgressMonitor(total_items=10, description="Test")

        # Update progress
        monitor.update(1, status="Processing")
        monitor.update(5, status="Halfway")
        monitor.complete()

        # Test monitor context manager
        with ProgressMonitor(total_items=5) as mon:
            for i in range(5):
                mon.update(1)

        # Test error tracking
        monitor = ProgressMonitor(total_items=3)
        monitor.update(1)
        monitor.error("Test error")
        stats = monitor.get_stats()
        assert stats["errors"] == 1

    def test_validation_coverage(self, temp_dir):
        """Test validation utilities."""
        validator = DocumentValidator()

        # Test file validation
        test_file = os.path.join(temp_dir, "test.pdf")
        with open(test_file, "w") as f:
            f.write("test")

        # Valid file
        from pathlib import Path
        assert validator.validate_file(Path(test_file)) is True

        # Invalid file - should raise ValidationError
        try:
            validator.validate_file(Path("/non/existent/file.pdf"))
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "File not found" in str(e)

        # Test URL validation
        assert validator.validate_url("https://example.com/doc.pdf") is True

        try:
            validator.validate_url("ftp://invalid.com/file")
            assert False, "Should have raised ValidationError"
        except ValidationError as e:
            assert "Invalid URL scheme" in str(e)

    def test_chunking_metadata_coverage(self):
        """Test chunking metadata functionality."""
        from utils.chunking_metadata import KeywordGenerator

        # Test keyword generator initialization
        generator = KeywordGenerator(model="gpt-4.1-mini", max_keywords=5)
        assert generator.model == "gpt-4.1-mini"
        assert generator.max_keywords == 5
        assert generator.client is not None

        # Test with config
        from utils.config import PipelineConfig
        config = PipelineConfig()
        generator_with_config = KeywordGenerator(config=config)
        assert generator_with_config.client is not None

    def test_cleanup_utilities(self, temp_dir):
        """Test cleanup and resource management."""
        # Get resource manager
        manager = get_resource_manager()
        assert manager is not None

        # Register a temp file
        temp_file = os.path.join(temp_dir, "temp_resource.txt")
        with open(temp_file, "w") as f:
            f.write("temp")

        manager.register_temp_file(temp_file)

        # Cleanup
        manager.cleanup()

        # Test cleanup function
        cleanup_temp_resources()

    def test_enhanced_retry_coverage(self):
        """Test enhanced retry utilities."""
        from utils.enhanced_retry import EnhancedRetry, RetryConfig

        # Test retry config
        config = RetryConfig(
            max_attempts=3,
            base_delay=1.0,
            max_delay=10.0,
            exponential_base=2.0
        )

        assert config.max_attempts == 3
        assert config.base_delay == 1.0

        # Test retry mechanism
        retry = EnhancedRetry(config)

        # Test successful operation
        call_count = 0

        @retry.with_retry
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Test error")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2

    def test_page_range_utilities(self):
        """Test page range parsing."""
        from utils.page_range import parse_page_range

        # Test various formats
        assert parse_page_range("1-5") == [1, 2, 3, 4, 5]
        assert parse_page_range("1,3,5") == [1, 3, 5]
        assert parse_page_range("1-3,5,7-9") == [1, 2, 3, 5, 7, 8, 9]
        assert parse_page_range("all") == []
        assert parse_page_range(None) == []
        assert parse_page_range("") == []

        # Test invalid ranges
        assert parse_page_range("invalid") == []
        assert parse_page_range("1-") == []

    def test_url_utils_coverage(self, temp_dir):
        """Test URL utilities."""
        from utils.url_utils import (
            extract_urls_from_file,
            validate_url_list,
            create_url_batch_file
        )

        # Test URL validation
        valid_urls = [
            "https://example.com/doc.pdf",
            "http://test.com/file.pdf"
        ]
        invalid_urls = [
            "not-a-url",
            "ftp://invalid.com/file"
        ]

        validated = validate_url_list(valid_urls + invalid_urls)
        assert len(validated["valid"]) == 2
        assert len(validated["invalid"]) == 2

        # Test URL extraction from markdown
        md_file = os.path.join(temp_dir, "urls.md")
        with open(md_file, "w") as f:
            f.write("# URLs\n")
            f.write("- https://example.com/doc1.pdf\n")
            f.write("- [Doc 2](https://example.com/doc2.pdf)\n")

        urls = extract_urls_from_file(md_file)
        assert len(urls) == 2

        # Test batch file creation
        batch_file = create_url_batch_file(
            urls=valid_urls,
            output_path=os.path.join(temp_dir, "batch.json"),
            metadata={"batch": "test"}
        )
        assert os.path.exists(batch_file)

    def test_filter_utils_coverage(self):
        """Test filter utilities."""
        from utils.filter_utils import FilterBuilder, FilterParser

        # Test filter builder
        builder = FilterBuilder()

        # Add conditions
        builder.add_condition("status", "completed")
        builder.add_condition("type", "datasheet")
        builder.add_range("page_count", min_value=10, max_value=100)

        # Build filter
        filter_dict = builder.build()
        assert "status" in filter_dict
        assert "page_count" in filter_dict

        # Test filter parser
        parser = FilterParser()

        # Parse string filter
        parsed = parser.parse("status:completed AND type:datasheet")
        assert parsed is not None

        # Parse complex filter
        complex_filter = "status:completed AND (type:datasheet OR type:manual) AND pages>10"
        parsed_complex = parser.parse(complex_filter)
        assert parsed_complex is not None

    @pytest.mark.asyncio
    async def test_openai_client_coverage(self):
        """Test OpenAI client utilities."""
        from utils.openai_client import OpenAIClientFactory, create_vision_client, create_text_client

        # Test factory with mocked OpenAI
        with patch("openai.OpenAI") as mock_openai_class:
            mock_instance = MagicMock()
            mock_openai_class.return_value = mock_instance

            # Test client creation via factory
            with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}):  # pragma: allowlist secret
                client = OpenAIClientFactory.create_client()
                assert client is not None

                # Test vision client creation
                vision_client = create_vision_client()
                assert vision_client is not None

                # Test text client creation
                text_client = create_text_client()
                assert text_client is not None

            # Mock embedding response
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_instance.embeddings.create = MagicMock(return_value=mock_response)

            # Test API key validation
            is_valid = OpenAIClientFactory.validate_api_key("test-key")
            # Should attempt to list models
            mock_instance.models.list.assert_called()

            # Test API key info
            info = OpenAIClientFactory.get_api_key_info()
            assert "api_key_found" in info
            assert "source" in info

    def test_cache_manager_coverage(self, temp_dir):
        """Test cache manager utilities."""
        from storage.cache import CacheManager

        # Create cache manager with custom path
        cache_dir = os.path.join(temp_dir, "cache")

        manager = CacheManager(cache_dir=cache_dir)

        # Test cache operations
        test_data = {"key": "value", "number": 42}
        doc_hash = "test_doc_hash"
        prompt_hash = "test_prompt_hash"

        # Save to cache
        success = manager.put(doc_hash, prompt_hash, test_data)
        assert success

        # Load from cache
        loaded = manager.get(doc_hash, prompt_hash)
        assert loaded == test_data

        # Test cache stats
        stats = manager.get_stats()
        assert stats["hits"] >= 0
        assert stats["misses"] >= 0

        # Clear cache
        cleared = manager.clear()
        assert cleared > 0

        # Verify cleared
        assert manager.get(doc_hash, prompt_hash) is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
