"""
Validation utilities for the pipeline.
"""

from pathlib import Path

# Custom exceptions
class PipelineError(Exception):
    """Base exception for pipeline errors."""
    pass

class ValidationError(PipelineError):
    """Input validation failed."""
    pass

# Validation utilities
# FIXME: Consider using PipelineConfig for validation parameters
# from .config import PipelineConfig

class DocumentValidator:
    """Simple validation for documents and URLs."""

    # FIXME: These could be sourced from config
    # config = PipelineConfig.from_yaml()
    # ALLOWED_EXTENSIONS = set(config.validation.allowed_extensions)
    # MAX_URL_LENGTH = config.validation.max_url_length
    ALLOWED_EXTENSIONS = {".pdf", ".md", ".txt", ".markdown"}
    MAX_URL_LENGTH = 2048

    def validate_url(self, url: str) -> bool:
        """Basic URL validation."""
        if len(url) > self.MAX_URL_LENGTH:
            raise ValidationError(f"URL too long: {len(url)} > {self.MAX_URL_LENGTH}")
        if not url.startswith(("http://", "https://")):
            raise ValidationError(f"Invalid URL scheme: {url}")
        return True

    def validate_file(self, path: Path, max_size_bytes: int) -> bool: # Renamed max_size to max_size_bytes for clarity
        """Validate file exists and size is reasonable."""
        # FIXME: max_size_bytes could default to a value from config.limits.max_file_size_mb * 1024 * 1024
        if not path.exists():
            raise ValidationError(f"File not found: {path}")
        if path.suffix.lower() not in self.ALLOWED_EXTENSIONS: # Uses class attribute
            raise ValidationError(f"Unsupported file type: {path.suffix}")
        if path.stat().st_size > max_size_bytes:
            raise ValidationError(f"File too large: {path.stat().st_size} > {max_size_bytes}")
        return True
