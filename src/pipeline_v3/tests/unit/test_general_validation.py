"""
Unit tests for general validation utilities.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ...utils.validation import ValidationError, DocumentValidator, PipelineError
from ...utils.config import PipelineConfig


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_pipeline_error_base(self):
        """Test base PipelineError exception."""
        error = PipelineError("Base error")
        assert str(error) == "Base error"
        assert isinstance(error, Exception)

    def test_validation_error_inheritance(self):
        """Test ValidationError inherits from PipelineError."""
        error = ValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert isinstance(error, PipelineError)
        assert isinstance(error, Exception)


class TestDocumentValidator:
    """Test the DocumentValidator class."""

    def test_init_default_config(self):
        """Test validator initialization with default config."""
        validator = DocumentValidator()
        
        assert validator.config is not None
        assert isinstance(validator.config, PipelineConfig)
        assert isinstance(validator.ALLOWED_EXTENSIONS, set)
        assert isinstance(validator.MAX_URL_LENGTH, int)

    def test_init_custom_config(self):
        """Test validator initialization with custom config."""
        config = MagicMock()
        config.validation.allowed_extensions = [".pdf", ".txt"]
        config.validation.max_url_length = 1000
        
        validator = DocumentValidator(config)
        
        assert validator.config == config
        assert validator.ALLOWED_EXTENSIONS == {".pdf", ".txt"}
        assert validator.MAX_URL_LENGTH == 1000

    def test_validate_url_valid_http(self):
        """Test URL validation with valid HTTP URL."""
        validator = DocumentValidator()
        
        result = validator.validate_url("http://example.com/document.pdf")
        assert result is True

    def test_validate_url_valid_https(self):
        """Test URL validation with valid HTTPS URL."""
        validator = DocumentValidator()
        
        result = validator.validate_url("https://example.com/document.pdf")
        assert result is True

    def test_validate_url_invalid_scheme(self):
        """Test URL validation with invalid scheme."""
        validator = DocumentValidator()
        
        with pytest.raises(ValidationError, match="Invalid URL scheme"):
            validator.validate_url("ftp://example.com/document.pdf")

    def test_validate_url_no_scheme(self):
        """Test URL validation with no scheme."""
        validator = DocumentValidator()
        
        with pytest.raises(ValidationError, match="Invalid URL scheme"):
            validator.validate_url("example.com/document.pdf")

    def test_validate_url_too_long(self):
        """Test URL validation with URL that's too long."""
        config = MagicMock()
        config.validation.allowed_extensions = [".pdf"]
        config.validation.max_url_length = 50
        
        validator = DocumentValidator(config)
        
        long_url = "https://example.com/" + "a" * 100
        with pytest.raises(ValidationError, match="URL too long"):
            validator.validate_url(long_url)

    def test_validate_url_at_max_length(self):
        """Test URL validation at maximum allowed length."""
        config = MagicMock()
        config.validation.allowed_extensions = [".pdf"]
        config.validation.max_url_length = 28  # Set to actual length
        
        validator = DocumentValidator(config)
        
        # Create URL exactly at max length
        url = "https://example.com/file.pdf"  # 28 characters
        assert len(url) == 28
        
        result = validator.validate_url(url)
        assert result is True

    def test_validate_file_valid(self):
        """Test file validation with valid file."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"Test PDF content")
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]
            config.limits.max_file_size_mb = 100
            
            validator = DocumentValidator(config)
            result = validator.validate_file(temp_path)
            assert result is True
        finally:
            temp_path.unlink()

    def test_validate_file_not_exists(self):
        """Test file validation with non-existent file."""
        validator = DocumentValidator()
        non_existent_path = Path("/nonexistent/file.pdf")
        
        with pytest.raises(ValidationError, match="File not found"):
            validator.validate_file(non_existent_path)

    def test_validate_file_unsupported_extension(self):
        """Test file validation with unsupported file extension."""
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"Test content")
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]
            config.limits.max_file_size_mb = 100
            
            validator = DocumentValidator(config)
            
            with pytest.raises(ValidationError, match="Unsupported file type"):
                validator.validate_file(temp_path)
        finally:
            temp_path.unlink()

    def test_validate_file_too_large(self):
        """Test file validation with file that's too large."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Write content larger than limit
            f.write(b"a" * 1000)  # 1000 bytes
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]
            config.limits.max_file_size_mb = 100  # This gets converted to bytes
            
            validator = DocumentValidator(config)
            
            # Override with small max_size_bytes for testing
            with pytest.raises(ValidationError, match="File too large"):
                validator.validate_file(temp_path, max_size_bytes=500)
        finally:
            temp_path.unlink()

    def test_validate_file_custom_max_size(self):
        """Test file validation with custom max size parameter."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"test content")  # Small file
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]
            config.limits.max_file_size_mb = 1  # Config says 1MB
            
            validator = DocumentValidator(config)
            
            # Use custom max_size_bytes (should override config)
            result = validator.validate_file(temp_path, max_size_bytes=1000000)
            assert result is True
        finally:
            temp_path.unlink()

    def test_validate_file_config_max_size_conversion(self):
        """Test that config max_file_size_mb is properly converted to bytes."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"small content")
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]
            config.limits.max_file_size_mb = 2  # 2 MB
            
            validator = DocumentValidator(config)
            
            # File is small, should pass validation
            result = validator.validate_file(temp_path)
            assert result is True
        finally:
            temp_path.unlink()

    def test_validate_file_case_insensitive_extension(self):
        """Test file validation is case-insensitive for extensions."""
        with tempfile.NamedTemporaryFile(suffix=".PDF", delete=False) as f:
            f.write(b"Test content")
            temp_path = Path(f.name)
        
        try:
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt"]  # lowercase
            config.limits.max_file_size_mb = 100
            
            validator = DocumentValidator(config)
            
            # Should pass despite uppercase extension
            result = validator.validate_file(temp_path)
            assert result is True
        finally:
            temp_path.unlink()

    def test_allowed_extensions_set_conversion(self):
        """Test that allowed_extensions is converted to a set."""
        config = MagicMock()
        config.validation.allowed_extensions = [".pdf", ".txt", ".pdf"]  # Duplicate
        config.validation.max_url_length = 2048
        
        validator = DocumentValidator(config)
        
        # Should be a set with unique values
        assert isinstance(validator.ALLOWED_EXTENSIONS, set)
        assert validator.ALLOWED_EXTENSIONS == {".pdf", ".txt"}
        assert len(validator.ALLOWED_EXTENSIONS) == 2


class TestIntegrationScenarios:
    """Integration tests for realistic validation scenarios."""

    def test_real_pdf_file_validation(self):
        """Test validation with a real PDF-like file."""
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            # Write PDF-like header
            f.write(b"%PDF-1.4\n")
            f.write(b"This is a test PDF file content.")
            temp_path = Path(f.name)
        
        try:
            validator = DocumentValidator()
            result = validator.validate_file(temp_path)
            assert result is True
        finally:
            temp_path.unlink()

    def test_comprehensive_url_validation_scenarios(self):
        """Test various URL validation scenarios."""
        validator = DocumentValidator()
        
        # Valid URLs
        valid_urls = [
            "https://example.com/doc.pdf",
            "http://subdomain.example.org/path/to/file.pdf",
            "https://example.com:8080/secure/document.pdf",
            "http://192.168.1.1/file.pdf",
        ]
        
        for url in valid_urls:
            result = validator.validate_url(url)
            assert result is True
        
        # Invalid URLs
        invalid_urls = [
            "ftp://example.com/file.pdf",
            "file:///local/file.pdf",
            "example.com/file.pdf",
            "//example.com/file.pdf",
        ]
        
        for url in invalid_urls:
            with pytest.raises(ValidationError):
                validator.validate_url(url)

    def test_mixed_file_types_validation(self):
        """Test validation with various file types."""
        # Create temp files with different extensions
        test_files = {}
        file_extensions = [".pdf", ".txt", ".md", ".docx", ".xyz"]
        
        try:
            for ext in file_extensions:
                f = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
                f.write(b"Test content")
                f.close()
                test_files[ext] = Path(f.name)
            
            config = MagicMock()
            config.validation.allowed_extensions = [".pdf", ".txt", ".md", ".docx"]
            config.limits.max_file_size_mb = 100
            
            validator = DocumentValidator(config)
            
            # Should pass for allowed extensions
            for ext in [".pdf", ".txt", ".md", ".docx"]:
                result = validator.validate_file(test_files[ext])
                assert result is True
            
            # Should fail for disallowed extension
            with pytest.raises(ValidationError, match="Unsupported file type"):
                validator.validate_file(test_files[".xyz"])
                
        finally:
            # Cleanup
            for path in test_files.values():
                path.unlink()

    def test_edge_case_file_sizes(self):
        """Test file size validation edge cases."""
        config = MagicMock()
        config.validation.allowed_extensions = [".txt"]
        config.limits.max_file_size_mb = 1  # 1 MB = 1048576 bytes
        
        validator = DocumentValidator(config)
        
        # Test file exactly at limit
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            # Write exactly 1MB
            f.write(b"a" * 1048576)
            temp_path = Path(f.name)
        
        try:
            result = validator.validate_file(temp_path)
            assert result is True
        finally:
            temp_path.unlink()
        
        # Test file just over limit
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            # Write 1MB + 1 byte
            f.write(b"a" * 1048577)
            temp_path = Path(f.name)
        
        try:
            with pytest.raises(ValidationError, match="File too large"):
                validator.validate_file(temp_path)
        finally:
            temp_path.unlink()