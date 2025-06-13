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
                    else:
                        return await func(*args, **kwargs)
                except asyncio.TimeoutError:
                    if attempt == max_attempts - 1:
                        raise TimeoutError(f"API call timed out after {timeout}s on attempt {attempt + 1}")
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
        else:
            return sync_wrapper
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
