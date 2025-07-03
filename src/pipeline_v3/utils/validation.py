"""
Validation utilities for the pipeline.
"""

from pathlib import Path


# Custom exceptions
class PipelineError(Exception):
    """Base exception for pipeline errors."""


class ValidationError(PipelineError):
    """Input validation failed."""


# Validation utilities
from .config import PipelineConfig


class DocumentValidator:
    """Simple validation for documents and URLs."""

    def __init__(self, config: PipelineConfig = None):
        """Initialize validator with optional config."""
        if config is None:
            config = PipelineConfig()

        self.config = config
        self.ALLOWED_EXTENSIONS = set(config.validation.allowed_extensions)
        self.MAX_URL_LENGTH = config.validation.max_url_length

    def validate_url(self, url: str) -> bool:
        """Basic URL validation."""
        if len(url) > self.MAX_URL_LENGTH:
            raise ValidationError(f"URL too long: {len(url)} > {self.MAX_URL_LENGTH}")
        if not url.startswith(("http://", "https://")):
            raise ValidationError(f"Invalid URL scheme: {url}")
        return True

    def validate_file(self, path: Path, max_size_bytes: int | None = None) -> bool:
        """Validate file exists and size is reasonable."""
        # Use provided max_size_bytes or get from config
        if max_size_bytes is None:
            max_size_bytes = self.config.limits.max_file_size_mb * 1024 * 1024
        if not path.exists():
            raise ValidationError(f"File not found: {path}")
        if path.suffix.lower() not in self.ALLOWED_EXTENSIONS:  # Uses class attribute
            raise ValidationError(f"Unsupported file type: {path.suffix}")
        if path.stat().st_size > max_size_bytes:
            raise ValidationError(f"File too large: {path.stat().st_size} > {max_size_bytes}")
        return True
