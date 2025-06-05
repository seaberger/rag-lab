"""
Common utilities for the pipeline.
"""

import logging
from functools import wraps

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

# Retry decorator for API calls (simplified without tenacity)
def retry_api_call(max_attempts=3):
    """Simple retry decorator for API calls."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(f"Attempt {attempt + 1} failed: {e}")
            return None
        return wrapper
    return decorator

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
