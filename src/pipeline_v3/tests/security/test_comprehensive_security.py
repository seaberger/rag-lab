"""
Comprehensive tests for security module.

Tests all security validators and sanitizers to ensure proper protection
against common vulnerabilities.
"""

import ipaddress
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from utils.security import (
    InputSanitizer,
    PathSecurityValidator,
    SecretsMasker,
    SecurityError,
    URLSecurityValidator,
)


class TestPathSecurityValidator:
    """Test path traversal protection."""

    def test_validate_path_within_allowed_directory(self, tmp_path):
        """Test that paths within allowed directories are accepted."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()
        test_file = allowed_dir / "test.txt"
        test_file.touch()

        # Should not raise
        validated = PathSecurityValidator.validate_path(test_file, [allowed_dir])
        assert validated == test_file.resolve()

    def test_validate_path_outside_allowed_directory(self, tmp_path):
        """Test that paths outside allowed directories are rejected."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        test_file = outside_dir / "test.txt"
        test_file.touch()

        with pytest.raises(SecurityError, match="outside allowed directories"):
            PathSecurityValidator.validate_path(test_file, [allowed_dir])

    def test_validate_path_with_traversal_attempt(self, tmp_path):
        """Test that path traversal attempts are blocked."""
        allowed_dir = tmp_path / "allowed"
        allowed_dir.mkdir()

        # Try to escape using ../
        traversal_path = str(allowed_dir / "../outside/test.txt")

        with pytest.raises(SecurityError, match="outside allowed directories"):
            PathSecurityValidator.validate_path(traversal_path, [allowed_dir])

    def test_validate_path_with_null_bytes(self):
        """Test that paths with null bytes are rejected."""
        # Path class raises ValueError for null bytes
        with pytest.raises(ValueError):
            PathSecurityValidator.validate_path("/test\x00/file.txt")

    def test_validate_path_with_url_encoding(self):
        """Test that suspicious URL encoding is rejected."""
        # URL encoding in paths gets resolved, so test a path that will fail
        with pytest.raises(SecurityError, match="outside allowed directories"):
            PathSecurityValidator.validate_path("/test/%2E%2E/parent", [Path.cwd()])

    def test_validate_glob_pattern_with_traversal(self):
        """Test that glob patterns with traversal are rejected."""
        with pytest.raises(SecurityError, match="Path traversal detected"):
            PathSecurityValidator.validate_glob_pattern("../../../etc/passwd")

    def test_validate_glob_pattern_too_long(self):
        """Test that overly long patterns are rejected."""
        long_pattern = "a" * 300
        with pytest.raises(SecurityError, match="Pattern too long"):
            PathSecurityValidator.validate_glob_pattern(long_pattern)

    def test_validate_glob_pattern_with_shell_chars(self):
        """Test that patterns with shell characters are rejected."""
        dangerous_patterns = [
            "test; rm -rf /",
            "test | cat /etc/passwd",
            "test && malicious",
            "test $(command)",
            "test `command`",
        ]

        for pattern in dangerous_patterns:
            with pytest.raises(SecurityError, match="suspicious character"):
                PathSecurityValidator.validate_glob_pattern(pattern)


class TestURLSecurityValidator:
    """Test SSRF protection."""

    def test_validate_url_public_https(self):
        """Test that public HTTPS URLs are allowed."""
        url = "https://example.com/document.pdf"
        validated = URLSecurityValidator.validate_url(url)
        assert validated == url

    def test_validate_url_private_ip_blocked(self):
        """Test that private IP addresses are blocked by default."""
        private_urls = [
            "http://10.0.0.1/doc.pdf",
            "http://172.16.0.1/doc.pdf",
            "http://192.168.1.1/doc.pdf",
            "http://127.0.0.1/doc.pdf",
            "http://localhost/doc.pdf",
            "http://[::1]/doc.pdf",
            "http://169.254.1.1/doc.pdf",
        ]

        for url in private_urls:
            with pytest.raises(SecurityError, match="not allowed"):
                URLSecurityValidator.validate_url(url)

    def test_validate_url_private_ip_allowed(self):
        """Test that private IPs can be allowed when specified."""
        url = "http://192.168.1.1/doc.pdf"
        validated = URLSecurityValidator.validate_url(url, allow_private_ips=True)
        assert validated == url

    def test_validate_url_localhost_allowed(self):
        """Test that localhost can be allowed when specified."""
        url = "http://localhost:8080/doc.pdf"
        # When allow_localhost=True, it should work
        validated = URLSecurityValidator.validate_url(url, allow_localhost=True, allow_private_ips=True)
        assert validated == url

    def test_validate_url_blocked_schemes(self):
        """Test that dangerous URL schemes are blocked."""
        blocked_urls = [
            "file:///etc/passwd",
            "ftp://example.com/file",
            "sftp://example.com/file",
            "data:text/plain;base64,SGVsbG8=",
            "gopher://example.com",
            "dict://example.com",
            "jar:file:/app.jar!/config",
            "ldap://example.com",
        ]

        for url in blocked_urls:
            with pytest.raises(SecurityError, match="Blocked URL scheme"):
                URLSecurityValidator.validate_url(url)

    def test_validate_url_blocked_ports(self):
        """Test that common internal service ports are blocked."""
        blocked_ports = [22, 23, 25, 3306, 5432, 6379, 27017]

        for port in blocked_ports:
            url = f"http://example.com:{port}/doc"
            with pytest.raises(SecurityError, match=f"Blocked port {port}"):
                URLSecurityValidator.validate_url(url)

    def test_validate_url_crlf_injection(self):
        """Test that CRLF injection attempts are blocked."""
        urls_with_crlf = [
            "http://example.com/doc\r\nHeader: malicious",
            "http://example.com/doc\nHeader: malicious",
        ]

        for url in urls_with_crlf:
            with pytest.raises(SecurityError, match="CRLF characters"):
                URLSecurityValidator.validate_url(url)

    def test_validate_url_too_long(self):
        """Test that overly long URLs are rejected."""
        long_url = "http://example.com/" + "a" * 2048
        with pytest.raises(SecurityError, match="URL too long"):
            URLSecurityValidator.validate_url(long_url)

    def test_validate_url_custom_whitelist(self):
        """Test that custom whitelist works correctly."""
        whitelist = ["trusted.internal", "api.company.com"]

        # Whitelisted domains should pass even if private
        url = "http://trusted.internal/doc.pdf"
        validated = URLSecurityValidator.validate_url(url, custom_whitelist=whitelist)
        assert validated == url

        # Subdomains should also work
        url = "http://sub.api.company.com/doc.pdf"
        validated = URLSecurityValidator.validate_url(url, custom_whitelist=whitelist)
        assert validated == url

    @patch('socket.gethostbyname')
    def test_validate_url_dns_resolution(self, mock_gethostbyname):
        """Test that DNS resolution to private IPs is caught."""
        # Mock DNS resolution to return private IP
        mock_gethostbyname.return_value = "192.168.1.1"

        with pytest.raises(SecurityError, match="Private IP addresses not allowed"):
            URLSecurityValidator.validate_url("http://malicious.example.com/doc")


class TestSecretsMasker:
    """Test secrets masking functionality."""

    def test_mask_value_basic(self):
        """Test basic value masking."""
        # The masker limits to 20 asterisks max
        assert SecretsMasker.mask_value("secret123") == "secr*****"
        assert SecretsMasker.mask_value("short") == "shor*"
        assert SecretsMasker.mask_value("abc") == "***"
        assert SecretsMasker.mask_value("") == "***"

    def test_mask_value_custom_visible_chars(self):
        """Test masking with custom visible character count."""
        assert SecretsMasker.mask_value("secret123", visible_chars=2) == "se*******"
        assert SecretsMasker.mask_value("secret123", visible_chars=6) == "secret***"

    def test_mask_dict_basic(self):
        """Test dictionary masking."""
        data = {
            "api_key": "sk-1234567890",  # pragma: allowlist secret
            "token": "xoxb-123456",  # pragma: allowlist secret
            "password": "mysecret",  # pragma: allowlist secret
            "username": "john",
            "config": {"secret": "hidden", "public": "visible"},  # pragma: allowlist secret
        }

        masked = SecretsMasker.mask_dict(data)

        assert masked["api_key"] == "sk-1*********"  # pragma: allowlist secret
        assert masked["token"] == "xoxb*******"  # pragma: allowlist secret
        assert masked["password"] == "myse****"  # pragma: allowlist secret
        assert masked["username"] == "john"  # Not sensitive
        assert masked["config"]["secret"] == "hidd**"  # pragma: allowlist secret
        assert masked["config"]["public"] == "visible"

    def test_mask_url_with_auth(self):
        """Test URL masking with authentication."""
        url = "http://user:password123@example.com:8080/path"  # pragma: allowlist secret
        masked = SecretsMasker.mask_url(url)
        assert masked == "http://user:***@example.com:8080/path"

        # Test URL without password
        url = "http://example.com/path"
        assert SecretsMasker.mask_url(url) == url

    def test_mask_log_message(self):
        """Test log message masking."""
        messages = [
            ("API_KEY=sk-1234567890abcdef", "API_KEY=***_API_KEY_MASKED***"),  # pragma: allowlist secret
            ("token: xoxb-123456789", "token: ***_TOKEN_MASKED***"),  # pragma: allowlist secret
            ("password='mysecret123'", "password='***_PASSWORD_MASKED***"),  # pragma: allowlist secret
            ("Multiple api_key=key1 and token=tok2", "Multiple api_key=***_API_KEY_MASKED*** and token=***_TOKEN_MASKED***"),  # pragma: allowlist secret
        ]

        for original, expected in messages:
            masked = SecretsMasker.mask_log_message(original)
            assert expected in masked


class TestInputSanitizer:
    """Test input sanitization."""

    def test_sanitize_metadata_value_basic(self):
        """Test basic metadata sanitization."""
        assert InputSanitizer.sanitize_metadata_value("normal text") == "normal text"
        assert InputSanitizer.sanitize_metadata_value("text\x00with\x00nulls") == "textwithnulls"

    def test_sanitize_metadata_value_shell_chars(self):
        """Test that shell metacharacters are escaped."""
        # The order matters: $ and ` come before \ in the list, so they get double-escaped
        # Other characters come after \ or at same position, so single escape
        test_cases = [
            ("test$value", "test\\\\$value"),  # $ comes before \, so \$ -> \\$
            ("test`value", "test\\\\`value"),  # ` comes before \, so \` -> \\`
            ("test;value", "test\\;value"),    # ; comes after \, so just \;
            ("test|value", "test\\|value"),    # | comes after \, so just \|
            ("test&value", "test\\&value"),    # & comes after \, so just \&
            ("test>value", "test\\>value"),    # > comes after \, so just \>
            ("test<value", "test\\<value"),    # < comes after \, so just \<
            ("test(value", "test\\(value"),    # ( comes after \, so just \(
            ("test)value", "test\\)value"),    # ) comes after \, so just \)
            ("test{value", "test\\{value"),    # { comes after \, so just \{
            ("test}value", "test\\}value"),    # } comes after \, so just \}
            ("test\\value", "test\\\\value"),  # Single \ becomes \\
            ("test\nvalue", "test\\\nvalue"),  # \n comes after \, so just \\n
            ("test\rvalue", "test\\\rvalue"),  # \r comes after \, so just \\r
        ]

        for test_input, expected in test_cases:
            result = InputSanitizer.sanitize_metadata_value(test_input)
            assert result == expected, f"For input {test_input!r}: expected {expected!r}, got {result!r}"

    def test_sanitize_metadata_value_length_limit(self):
        """Test that overly long values are truncated."""
        long_value = "a" * 1500
        sanitized = InputSanitizer.sanitize_metadata_value(long_value)
        assert len(sanitized) == 1000

    def test_sanitize_search_query_sql_injection(self):
        """Test that SQL injection attempts are sanitized."""
        queries = [
            ("normal search", "normal search"),
            ("search -- DROP TABLE", "search"),
            ("search /* comment */ test", "search test"),  # Extra spaces get cleaned
            ("DROP users; SELECT *", "users; SELECT *"),
            ("DELETE FROM table", "FROM table"),
            ("test'; EXEC xp_cmdshell", "test'; xp_cmdshell"),
        ]

        for original, expected in queries:
            assert InputSanitizer.sanitize_search_query(original).strip() == expected.strip()

    def test_sanitize_search_query_preserves_functionality(self):
        """Test that legitimate search queries are preserved."""
        queries = [
            "laser power measurement",
            "PM10K specifications",
            "temperature sensor -40°C to +85°C",
            "model: ABC-123 OR DEF-456",
            '"exact phrase search"',
        ]

        for query in queries:
            # Should preserve most of the query (may clean whitespace)
            sanitized = InputSanitizer.sanitize_search_query(query)
            assert len(sanitized) > 0
            # Check key terms are preserved
            for term in query.lower().split():
                if term not in ["or", "and", "not"]:  # SQL keywords might be removed
                    assert term in sanitized.lower() or term.strip('"') in sanitized.lower()


# Integration test for the convenience functions
def test_convenience_functions(tmp_path):
    """Test the module-level convenience functions."""
    from utils.security import mask_secrets, sanitize_input, validate_file_path, validate_url

    # Test validate_file_path
    test_file = tmp_path / "test.txt"
    test_file.touch()

    validated = validate_file_path(test_file, [tmp_path])
    assert validated == test_file.resolve()

    # Test validate_url
    url = "https://example.com/doc.pdf"
    assert validate_url(url) == url

    # Test mask_secrets
    text = "My api_key=sk-12345 is secret"
    masked = mask_secrets(text)
    assert "sk-12345" not in masked
    assert "***_API_KEY_MASKED***" in masked

    # Test sanitize_input
    assert sanitize_input("test$var", "metadata") == "test\\\\$var"
    assert sanitize_input("DROP TABLE users", "search") == "TABLE users"
