"""
Shared utilities for the pipeline.
"""

import asyncio
import hashlib
import logging
from typing import Optional, Dict, Any
from functools import wraps
import aiohttp
from tenacity import retry, stop_after_attempt, wait_exponential


# Custom exceptions
class PipelineError(Exception):
    """Base exception for pipeline errors."""

    pass


class ValidationError(PipelineError):
    """Input validation failed."""

    pass


class ParseError(PipelineError):
    """Document parsing failed."""

    pass


class NetworkError(PipelineError):
    """Network operation failed."""

    pass


# Validation utilities
class DocumentValidator:
    """Simple validation for documents and URLs."""

    ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown"}
    MAX_URL_LENGTH = 2048

    def validate_url(self, url: str) -> bool:
        """Basic URL validation."""
        if len(url) > self.MAX_URL_LENGTH:
            raise ValidationError(f"URL too long: {len(url)} > {self.MAX_URL_LENGTH}")
        if not url.startswith(("http://", "https://")):
            raise ValidationError(f"Invalid URL scheme: {url}")
        return True

    def validate_file(self, path: Path, max_size: int) -> bool:
        """Validate file exists and size is reasonable."""
        if not path.exists():
            raise ValidationError(f"File not found: {path}")
        if path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(f"Unsupported file type: {path.suffix}")
        if path.stat().st_size > max_size:
            raise ValidationError(f"File too large: {path.stat().st_size} > {max_size}")
        return True


# Retry decorator for API calls
def retry_api_call(max_attempts=3):
    """Retry decorator for OpenAI API calls."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=4, max=60),
        reraise=True,
    )


# Structured logging setup
def setup_logging(level="INFO"):
    """Configure structured logging."""
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("pipeline.log")],
    )
    return logging.getLogger(__name__)


logger = setup_logging()
