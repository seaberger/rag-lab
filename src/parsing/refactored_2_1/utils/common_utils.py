"""
Common utilities for the pipeline.
"""

import logging
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential

# Custom exceptions
class PipelineError(Exception):
    """Base exception for pipeline errors."""
    pass

class ParseError(PipelineError):
    """Document parsing failed."""
    pass

class NetworkError(PipelineError):
    """Network operation failed."""
    pass

# Retry decorator for API calls
def retry_api_call(max_attempts=3):
    """Retry decorator for OpenAI API calls."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True,
    )

# Structured logging setup
# FIXME: Consider using PipelineConfig for logging level and file path
# from .config import PipelineConfig # Assuming config.py is in the same directory (utils)

def setup_logging(level="INFO", log_file="pipeline.log"):
    """Configure structured logging."""
    # FIXME: level and log_file should be sourced from config
    # config = PipelineConfig.from_yaml()
    # level = config.logging.level
    # log_file = config.logging.file

    logging.basicConfig(
        level=level.upper(), # Ensure level is uppercase string
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(log_file)],
    )
    return logging.getLogger(__name__)

# Initialize logger with default values; can be reconfigured by calling setup_logging() again with config values
logger = setup_logging()
