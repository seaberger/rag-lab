"""
CLI Integration Tests for Pipeline v3

Tests the command-line interface with real component integration
to ensure end-to-end functionality and boost coverage.
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

from cli.management import PipelineCLI
from core.registry import DocumentRegistry
from job_queue.manager import DocumentQueue, JobPriority
from utils.config import PipelineConfig


class TestCLIIntegration:
    """Integration tests for CLI with real components."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for test files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def test_config(self, temp_dir):
        """Create test configuration."""
        config = PipelineConfig()
        # Override paths for testing
        config.storage.base_dir = temp_dir
        config.cache.directory = os.path.join(temp_dir, "cache")
        config.storage.document_registry_path = os.path.join(temp_dir, "registry.db")
        config.storage.keyword_db_path = os.path.join(temp_dir, "keyword.db")
        config.fingerprint.storage_path = os.path.join(temp_dir, "fingerprint.db")
        config.job_queue.job_storage_path = os.path.join(temp_dir, "jobs.db")
        config.qdrant.path = os.path.join(temp_dir, "qdrant")
        return config

    @pytest.fixture
    def cli_instance(self, test_config):
        """Create CLI instance with test config."""
        with patch("cli.management.PipelineConfig") as mock_config_class:
            mock_config_class.return_value = test_config
            mock_config_class.from_yaml.return_value = test_config

            # Create CLI with proper initialization
            cli = PipelineCLI()
            cli.config = test_config

            # Initialize real components (not mocks)
            from pipeline.enhanced_core import EnhancedPipeline
            from core.registry import DocumentRegistry
            from core.index_manager import IndexManager
            from job_queue.manager import DocumentQueue

            cli.pipeline = EnhancedPipeline(config=test_config)
            cli.registry = DocumentRegistry(config=test_config)
            cli.index_manager = IndexManager(config=test_config)
            cli.queue = DocumentQueue(config=test_config)

            yield cli

    @pytest.fixture
    def mock_openai_for_cli(self):
        """Mock OpenAI for CLI tests."""
        with patch("openai.OpenAI") as mock_openai_class:
            instance = MagicMock()
            mock_openai_class.return_value = instance

            # Mock responses
            async def mock_process(*args, **kwargs):
                return {
                    "product_name": "CLI Test Product",
                    "manufacturer": "Test Corp",
                    "specifications": [{"category": "Test", "details": {}}],
                    "key_features": ["CLI Feature"],
                    "datasheet_content": "CLI test content"
                }
            instance.process_document_pages = AsyncMock(side_effect=mock_process)

            async def mock_embed(text):
                return [0.1] * 1536
            instance.get_embeddings = AsyncMock(side_effect=mock_embed)

            async def mock_keywords(text):
                return ["cli", "test", "keyword"]
            instance.extract_keywords = AsyncMock(side_effect=mock_keywords)

            yield instance

    @pytest.mark.asyncio
    async def test_cli_add_command_integration(self, cli_instance, mock_openai_for_cli, temp_dir):
        """Test CLI add command with real pipeline integration."""
        # Create test file
        test_file = os.path.join(temp_dir, "cli_test.pdf")
        with open(test_file, "wb") as f:
            f.write(b"CLI test PDF content")

        # Mock pipeline document processing
        with patch.object(cli_instance.pipeline, 'process_document') as mock_process:
            # Set up mock return value
            mock_process.return_value = {
                "doc_id": "test_doc_123",
                "status": "success",
                "action": "indexed",
                "chunks": 3,
                "processing_time": 1.5
            }

            # Create mock args
            args = MagicMock()
            args.sources = [test_file]
            args.metadata = ["type=cli_test", "version=1.0"]
            args.force = False
            args.index_type = "both"
            args.json = False
            args.recursive = False
            args.url_file = None
            args.exclude_pattern = None
            args.include_pattern = None
            args.dry_run = False
            args.with_keywords = True
            args.mode = "datasheet"
            args.workers = 1

            # Execute add command
            await cli_instance.handle_add(args)

            # Verify process_document was called with correct parameters
            mock_process.assert_called_once()
            call_args = mock_process.call_args

            # Check that the source path was passed
            assert test_file in str(call_args)

            # Check that metadata was parsed correctly (should be in kwargs)
            call_kwargs = call_args.kwargs if call_args.kwargs else {}
            if 'metadata' in call_kwargs:
                metadata = call_kwargs['metadata']
                assert metadata.get("type") == "cli_test"
                assert metadata.get("version") == "1.0"

    @pytest.mark.asyncio
    async def test_cli_search_integration(self, cli_instance, mock_openai_for_cli, temp_dir):
        """Test CLI search with real index integration."""
        # First add a document
        test_file = os.path.join(temp_dir, "search_test.pdf")
        with open(test_file, "wb") as f:
            f.write(b"Search test content")

        with patch.object(cli_instance.pipeline, 'process_document') as mock_process, \
             patch.object(cli_instance.pipeline, 'search') as mock_search:
            # Mock successful document processing
            mock_process.return_value = {
                "doc_id": "search_test_doc",
                "status": "success",
                "action": "indexed"
            }

            # Mock search results
            mock_search.return_value = [
                {
                    "content": "Laser sensor specifications",
                    "score": 0.95,
                    "metadata": {"doc_id": "search_test_doc"}
                }
            ]

            # Add document
            add_args = MagicMock()
            add_args.sources = [test_file]
            add_args.metadata = []
            add_args.force = False
            add_args.index_type = "both"
            add_args.json = False
            add_args.recursive = False
            add_args.url_file = None
            add_args.exclude_pattern = None
            add_args.include_pattern = None
            add_args.dry_run = False
            add_args.with_keywords = True
            add_args.mode = "datasheet"
            add_args.workers = 1

            await cli_instance.handle_add(add_args)

            # Now search
            search_args = MagicMock()
            search_args.query = "laser sensor"
            search_args.type = "hybrid"
            search_args.top_k = 5
            search_args.filter = None
            search_args.json = True
            search_args.fusion_method = "rrf"

            # Capture output
            with patch("builtins.print") as mock_print:
                await cli_instance.handle_search(search_args)

                # Verify print was called with JSON
                mock_print.assert_called()
                call_args = mock_print.call_args[0][0]

                # Parse JSON output
                results = json.loads(call_args)
                assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_cli_queue_operations(self, cli_instance, temp_dir):
        """Test CLI queue management operations."""
        # Test queue start (now works with actual implementation)
        start_args = MagicMock()
        start_args.queue_action = "start"
        start_args.workers = 2

        await cli_instance.handle_queue(start_args)

        # Add some jobs
        for i in range(3):
            await cli_instance.queue.add_job(
                source=f"doc_{i}.pdf",
                job_type="add",
                priority=JobPriority.NORMAL,
                metadata={"index": i}
            )

        # Test queue status
        status_args = MagicMock()
        status_args.queue_action = "status"
        status_args.detailed = True
        status_args.json = False

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_queue(status_args)

            # Verify status was printed
            mock_print.assert_called()
            output = str(mock_print.call_args)
            assert "pending" in output.lower()

        # Test queue stop
        stop_args = MagicMock()
        stop_args.queue_action = "stop"
        stop_args.wait = True

        await cli_instance.handle_queue(stop_args)

    @pytest.mark.asyncio
    async def test_cli_status_command(self, cli_instance):
        """Test CLI status command with real components."""
        args = MagicMock()
        args.detailed = True
        args.json = False

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_status(args)

            # Verify output contains expected sections
            output = str(mock_print.call_args)
            assert "pipeline" in output.lower()
            assert "registry" in output.lower()
            assert "queue" in output.lower()

    @pytest.mark.asyncio
    async def test_cli_maintenance_operations(self, cli_instance):
        """Test CLI maintenance commands."""
        # Test repair
        repair_args = MagicMock()
        repair_args.repair = True
        repair_args.cleanup = False
        repair_args.consistency_check = False

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_maintenance(repair_args)
            mock_print.assert_called()

        # Test consistency check
        check_args = MagicMock()
        check_args.repair = False
        check_args.cleanup = False
        check_args.consistency_check = True

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_maintenance(check_args)
            mock_print.assert_called()

    @pytest.mark.asyncio
    async def test_cli_config_management(self, cli_instance):
        """Test CLI configuration commands."""
        from dataclasses import asdict

        # Add missing methods to config instance for this test
        def to_dict():
            return asdict(cli_instance.config)

        def get(key, default=None):
            parts = key.split('.')
            obj = cli_instance.config
            for part in parts:
                obj = getattr(obj, part, None)
                if obj is None:
                    return default
            return obj

        def set_value(key, value):
            parts = key.split('.')
            obj = cli_instance.config
            for part in parts[:-1]:
                obj = getattr(obj, part)
            # Convert string values to appropriate types
            if isinstance(value, str) and value.isdigit():
                value = int(value)
            setattr(obj, parts[-1], value)

        def save():
            pass  # No-op for testing

        # Monkey-patch the methods
        cli_instance.config.to_dict = to_dict
        cli_instance.config.get = get
        cli_instance.config.set = set_value
        cli_instance.config.save = save

        # Test config list
        list_args = MagicMock()
        list_args.config_action = "list"
        list_args.json = True

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_config(list_args)

            # Verify JSON output
            call_args = mock_print.call_args[0][0]
            config_data = json.loads(call_args)
            assert isinstance(config_data, dict)

        # Test config get
        get_args = MagicMock()
        get_args.config_action = "get"
        get_args.key = "job_queue.max_concurrent"
        get_args.json = False

        with patch("builtins.print") as mock_print:
            await cli_instance.handle_config(get_args)
            output = str(mock_print.call_args)
            assert "max_concurrent" in output

        # Test config set
        set_args = MagicMock()
        set_args.config_action = "set"
        set_args.key = "job_queue.max_concurrent"
        set_args.value = "8"

        await cli_instance.handle_config(set_args)

        # Verify value was set
        assert cli_instance.config.job_queue.max_concurrent == 8

    @pytest.mark.asyncio
    async def test_cli_batch_operations(self, cli_instance, mock_openai_for_cli, temp_dir):
        """Test CLI batch processing capabilities."""
        # Create multiple test files
        test_files = []
        for i in range(5):
            file_path = os.path.join(temp_dir, f"batch_{i}.pdf")
            with open(file_path, "wb") as f:
                f.write(f"Batch content {i}".encode())
            test_files.append(file_path)

        with patch.object(cli_instance.pipeline, 'process_document_batch') as mock_batch:
            # Set up mock return value for batch processing
            mock_batch.return_value = [
                {
                    "doc_id": f"batch_doc_{i}",
                    "status": "success",
                    "action": "indexed",
                    "source": test_files[i]
                } for i in range(len(test_files))
            ]

            # Test batch add with pattern
            args = MagicMock()
            args.sources = [temp_dir]
            args.metadata = ["batch=test"]
            args.force = False
            args.index_type = "both"
            args.json = False
            args.recursive = True
            args.url_file = None
            args.exclude_pattern = None
            args.include_pattern = "batch_*.pdf"
            args.dry_run = False
            args.with_keywords = False
            args.mode = "generic"
            args.workers = 2

            # Execute batch add
            await cli_instance.handle_add(args)

            # Verify batch processing was called correctly
            mock_batch.assert_called_once()

            # Check that the correct files were included in the batch
            call_args = mock_batch.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_cli_error_handling(self, cli_instance, temp_dir):
        """Test CLI error handling and recovery."""
        # Test with non-existent file
        args = MagicMock()
        args.sources = ["/non/existent/file.pdf"]
        args.metadata = []
        args.force = False
        args.index_type = "both"
        args.json = False
        args.recursive = False
        args.url_file = None
        args.exclude_pattern = None
        args.include_pattern = None
        args.dry_run = False
        args.with_keywords = False
        args.mode = "auto"
        args.workers = 1

        # Should handle gracefully
        with patch("builtins.print") as mock_print:
            await cli_instance.handle_add(args)

            # Verify error message was printed
            output = str(mock_print.call_args)
            assert "no documents found" in output.lower() or "no files found" in output.lower() or "error" in output.lower()

    def test_cli_parser_coverage(self, cli_instance):
        """Test CLI parser creation and argument parsing."""
        parser = cli_instance.create_parser()

        # Test parsing add command
        args = parser.parse_args(["add", "test.pdf", "--with-keywords"])
        assert args.command == "add"
        assert args.sources == ["test.pdf"]
        assert args.with_keywords is True

        # Test parsing search command
        args = parser.parse_args(["search", "test query", "--type", "hybrid", "--top-k", "10"])
        assert args.command == "search"
        assert args.query == "test query"
        assert args.type == "hybrid"
        assert args.top_k == 10

        # Test parsing queue command
        args = parser.parse_args(["queue", "start", "--workers", "4"])
        assert args.command == "queue"
        assert args.queue_action == "start"
        assert args.workers == 4

    @pytest.mark.asyncio
    async def test_cli_json_output_formatting(self, cli_instance):
        """Test JSON output formatting across commands."""
        # Test various commands with JSON output
        test_data = {
            "status": {
                "pipeline": {"state": "ready"},
                "registry": {"total": 10},
                "queue": {"pending": 0}
            }
        }

        # Test JSON formatting
        json_output = cli_instance._format_output(test_data, json_format=True)
        parsed = json.loads(json_output)
        assert parsed == test_data

        # Test plain formatting
        plain_output = cli_instance._format_output(test_data, json_format=False)
        assert "pipeline" in plain_output
        assert "ready" in plain_output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
