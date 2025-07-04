"""
Common utilities for the pipeline.
"""

import logging
from functools import wraps


# Custom exceptions
class PipelineError(Exception):
    """Base exception for pipeline errors."""


class ParseError(PipelineError):
    """Document parsing failed."""


class NetworkError(PipelineError):
    """Network operation failed."""


class CLIArgumentError(PipelineError):
    """CLI argument parsing error."""

    def __init__(self, message, command_string=None):
        super().__init__(message)
        self.command_string = command_string


class DependencyError(PipelineError):
    """Dependency loading or initialization error."""

    def __init__(self, message, command_string=None):
        super().__init__(message)
        self.command_string = command_string


class ConfigLoadError(PipelineError):
    """Configuration loading error."""

    def __init__(self, message, command_string=None):
        super().__init__(message)
        self.command_string = command_string


# Retry decorator for API calls (simplified without tenacity)
def retry_api_call(max_attempts=3, timeout=None):
    """Simple retry decorator for API calls with timeout support.

    Args:
        max_attempts: Maximum number of retry attempts
        timeout: Optional timeout in seconds for each attempt
    """

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio

            for attempt in range(max_attempts):
                try:
                    if timeout:
                        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                    return await func(*args, **kwargs)
                except TimeoutError:
                    if attempt == max_attempts - 1:
                        raise TimeoutError(
                            f"API call timed out after {timeout}s on attempt {attempt + 1}"
                        )
                    logger.warning(f"Attempt {attempt + 1} timed out after {timeout}s")
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
            return None

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
            return None

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# Structured logging setup
# FIXME: Consider using PipelineConfig for logging level and file path
# from .config import PipelineConfig # Assuming config.py is in the same directory (utils)

from .config import PipelineConfig


def setup_logging(level=None, log_file=None):
    """Configure structured logging with dual handlers."""
    if level is None or log_file is None:
        config = PipelineConfig.from_yaml()
        level = level or config.logging.level
        log_file = log_file or config.logging.file

    # Console handler for human-friendly logging
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # File handler for detailed logging
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)

    # Basic logging configuration
    logging.basicConfig(
        level=level.upper(),
        handlers=[console_handler, file_handler],
    )
    return logging.getLogger(__name__)


def init_cli_logging():
    """Initialize logging immediately for CLI to capture early failures."""
    setup_logging()


# Initialize logger with default values; can be reconfigured by calling setup_logging() again with config values
logger = setup_logging()
