"""
Unit tests for common utilities.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from ...utils.common_utils import (
    PipelineError,
    ParseError,
    NetworkError,
    CLIArgumentError,
    DependencyError,
    ConfigLoadError,
    retry_api_call,
    setup_logging,
    init_cli_logging,
)


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_pipeline_error_base(self):
        """Test base PipelineError exception."""
        error = PipelineError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_parse_error_inheritance(self):
        """Test ParseError inherits from PipelineError."""
        error = ParseError("Parse failed")
        assert str(error) == "Parse failed"
        assert isinstance(error, PipelineError)
        assert isinstance(error, Exception)

    def test_network_error_inheritance(self):
        """Test NetworkError inherits from PipelineError."""
        error = NetworkError("Network failed")
        assert str(error) == "Network failed"
        assert isinstance(error, PipelineError)

    def test_cli_argument_error_basic(self):
        """Test CLIArgumentError basic functionality."""
        error = CLIArgumentError("Invalid argument")
        assert str(error) == "Invalid argument"
        assert error.command_string is None
        assert isinstance(error, PipelineError)

    def test_cli_argument_error_with_command(self):
        """Test CLIArgumentError with command string."""
        error = CLIArgumentError("Invalid argument", "command --flag")
        assert str(error) == "Invalid argument"
        assert error.command_string == "command --flag"

    def test_dependency_error_basic(self):
        """Test DependencyError basic functionality."""
        error = DependencyError("Missing dependency")
        assert str(error) == "Missing dependency"
        assert error.command_string is None
        assert isinstance(error, PipelineError)

    def test_dependency_error_with_command(self):
        """Test DependencyError with command string."""
        error = DependencyError("Missing dependency", "install numpy")
        assert str(error) == "Missing dependency"
        assert error.command_string == "install numpy"

    def test_config_load_error_basic(self):
        """Test ConfigLoadError basic functionality."""
        error = ConfigLoadError("Config not found")
        assert str(error) == "Config not found"
        assert error.command_string is None
        assert isinstance(error, PipelineError)

    def test_config_load_error_with_command(self):
        """Test ConfigLoadError with command string."""
        error = ConfigLoadError("Config not found", "load config.yaml")
        assert str(error) == "Config not found"
        assert error.command_string == "load config.yaml"


class TestRetryDecorator:
    """Test the retry_api_call decorator."""

    def test_retry_sync_function_success(self):
        """Test retry decorator with successful sync function."""
        call_count = 0

        @retry_api_call(max_attempts=3)
        def test_func():
            nonlocal call_count
            call_count += 1
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 1

    def test_retry_sync_function_eventual_success(self):
        """Test retry decorator with sync function that succeeds on second try."""
        call_count = 0

        @retry_api_call(max_attempts=3)
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Temporary failure")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 2

    def test_retry_sync_function_max_attempts_exceeded(self):
        """Test retry decorator when max attempts are exceeded."""
        call_count = 0

        @retry_api_call(max_attempts=2)
        def test_func():
            nonlocal call_count
            call_count += 1
            raise Exception(f"Failure {call_count}")

        with pytest.raises(Exception, match="Failure 2"):
            test_func()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_async_function_success(self):
        """Test retry decorator with successful async function."""
        call_count = 0

        @retry_api_call(max_attempts=3)
        async def test_func():
            nonlocal call_count
            call_count += 1
            return "async_success"

        result = await test_func()
        assert result == "async_success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_async_function_eventual_success(self):
        """Test retry decorator with async function that succeeds on third try."""
        call_count = 0

        @retry_api_call(max_attempts=3)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary async failure")
            return "async_success"

        result = await test_func()
        assert result == "async_success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_async_function_timeout(self):
        """Test retry decorator with async function timeout."""
        call_count = 0

        @retry_api_call(max_attempts=2, timeout=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.2)  # Sleep longer than timeout
            return "should_not_reach"

        with pytest.raises(TimeoutError, match="API call timed out"):
            await test_func()
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_retry_async_function_timeout_success_on_retry(self):
        """Test retry decorator with timeout that succeeds on retry."""
        call_count = 0

        @retry_api_call(max_attempts=3, timeout=0.1)
        async def test_func():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                await asyncio.sleep(0.2)  # First call times out
            return "success_on_retry"

        result = await test_func()
        assert result == "success_on_retry"
        assert call_count == 2

    def test_retry_decorator_preserves_function_metadata(self):
        """Test that retry decorator preserves function metadata."""
        @retry_api_call(max_attempts=2)
        def test_func():
            """Test function docstring."""
            return "test"

        assert test_func.__name__ == "test_func"
        assert test_func.__doc__ == "Test function docstring."

    @pytest.mark.asyncio
    async def test_retry_async_preserves_function_metadata(self):
        """Test that retry decorator preserves async function metadata."""
        @retry_api_call(max_attempts=2)
        async def async_test_func():
            """Async test function docstring."""
            return "async_test"

        assert async_test_func.__name__ == "async_test_func"
        assert async_test_func.__doc__ == "Async test function docstring."

    def test_retry_default_parameters(self):
        """Test retry decorator with default parameters."""
        call_count = 0

        @retry_api_call()  # Default max_attempts=3, timeout=None
        def test_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "success"

        result = test_func()
        assert result == "success"
        assert call_count == 3


class TestLoggingSetup:
    """Test logging setup functions."""

    @patch('src.pipeline_v3.utils.common_utils.PipelineConfig')
    def test_setup_logging_with_parameters(self, mock_config_class):
        """Test setup_logging with explicit parameters."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "test.log"
            
            # Clear existing handlers to avoid conflicts
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            assert isinstance(logger, logging.Logger)
            
            # Test that logging works - need to get a fresh logger
            test_logger = logging.getLogger("test_logger")
            test_logger.info("Test message")
            
            # Force flush handlers
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # File should exist and contain message
            assert log_file.exists()
            log_content = log_file.read_text()
            assert "Test message" in log_content

    @patch('src.pipeline_v3.utils.common_utils.PipelineConfig')
    def test_setup_logging_with_config(self, mock_config_class):
        """Test setup_logging using configuration."""
        # Mock config object
        mock_config = MagicMock()
        mock_config.logging.level = "INFO"
        mock_config.logging.file = "config_test.log"
        mock_config_class.from_yaml.return_value = mock_config
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # Change to temp directory so log file is created there
            original_cwd = Path.cwd()
            try:
                os.chdir(temp_dir)
                
                logger = setup_logging()
                
                assert isinstance(logger, logging.Logger)
                
                # Verify config was used
                mock_config_class.from_yaml.assert_called_once()
                
            finally:
                os.chdir(original_cwd)

    @patch('src.pipeline_v3.utils.common_utils.PipelineConfig')
    def test_setup_logging_level_override(self, mock_config_class):
        """Test setup_logging with level override."""
        # Mock config object
        mock_config = MagicMock()
        mock_config.logging.level = "ERROR"  # Config says ERROR
        mock_config.logging.file = "override_test.log"
        mock_config_class.from_yaml.return_value = mock_config
        
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "override_test.log"
            
            # Override level to DEBUG
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            assert isinstance(logger, logging.Logger)
            
            # Function should work (config call is mocked)
            assert isinstance(logger, logging.Logger)

    @patch('src.pipeline_v3.utils.common_utils.setup_logging')
    def test_init_cli_logging(self, mock_setup_logging):
        """Test init_cli_logging function."""
        init_cli_logging()
        
        # Should call setup_logging with no parameters
        mock_setup_logging.assert_called_once_with()

    def test_logging_handlers_configuration(self):
        """Test that logging setup creates proper handlers."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "handlers_test.log"
            
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            # Get the root logger to check handlers
            root_logger = logging.getLogger()
            
            # Should have at least 2 handlers (console and file)
            assert len(root_logger.handlers) >= 2
            
            # Check handler types
            handler_types = [type(h).__name__ for h in root_logger.handlers]
            assert "StreamHandler" in handler_types
            assert "FileHandler" in handler_types

    def test_logging_format_consistency(self):
        """Test that log messages are formatted consistently."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "format_test.log"
            
            # Clear existing handlers
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            # Log a test message with a fresh logger
            test_message = "Test format consistency"
            test_logger = logging.getLogger("format_test")
            test_logger.info(test_message)
            
            # Force flush
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Read log file content
            log_content = log_file.read_text()
            
            # Should contain timestamp, logger name, level, and message
            assert test_message in log_content
            assert "INFO" in log_content
            # Should have timestamp format (basic check)
            assert "-" in log_content  # Date separators
            assert ":" in log_content  # Time separators


class TestIntegrationScenarios:
    """Integration tests for realistic usage scenarios."""

    def test_exception_hierarchy_isinstance_checks(self):
        """Test that exception hierarchy works correctly for isinstance checks."""
        parse_error = ParseError("Parse failed")
        network_error = NetworkError("Network failed")
        cli_error = CLIArgumentError("CLI failed")
        
        # All should be instances of PipelineError
        assert isinstance(parse_error, PipelineError)
        assert isinstance(network_error, PipelineError)
        assert isinstance(cli_error, PipelineError)
        
        # Should be distinguishable by specific type
        assert not isinstance(parse_error, NetworkError)
        assert not isinstance(network_error, ParseError)
        assert not isinstance(cli_error, ParseError)

    @pytest.mark.asyncio
    async def test_retry_with_mixed_exceptions(self):
        """Test retry decorator handling different exception types."""
        call_count = 0
        
        @retry_api_call(max_attempts=4)
        async def test_func():
            nonlocal call_count
            call_count += 1
            
            if call_count == 1:
                raise NetworkError("Network timeout")
            elif call_count == 2:
                raise ParseError("Parse failed")
            elif call_count == 3:
                raise Exception("Generic error")
            else:
                return "finally_success"
        
        result = await test_func()
        assert result == "finally_success"
        assert call_count == 4

    def test_comprehensive_logging_workflow(self):
        """Test complete logging workflow from setup to output."""
        with tempfile.TemporaryDirectory() as temp_dir:
            log_file = Path(temp_dir) / "workflow_test.log"
            
            # Clear existing handlers
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
            
            # Setup logging
            logger = setup_logging(level="DEBUG", log_file=str(log_file))
            
            # Create a fresh test logger
            test_logger = logging.getLogger("workflow_test")
            
            # Log messages at different levels
            test_logger.debug("Debug message")
            test_logger.info("Info message")
            test_logger.warning("Warning message")
            test_logger.error("Error message")
            
            # Force flush all handlers
            for handler in logging.getLogger().handlers:
                handler.flush()
            
            # Verify all messages are in the file
            log_content = log_file.read_text()
            assert "Debug message" in log_content
            assert "Info message" in log_content
            assert "Warning message" in log_content
            assert "Error message" in log_content
            
            # Verify log levels are included
            assert "DEBUG" in log_content
            assert "INFO" in log_content
            assert "WARNING" in log_content
            assert "ERROR" in log_content