"""
Security utilities for input validation and sanitization.

This module provides centralized security functions to prevent common vulnerabilities:
- Path traversal attacks
- SSRF (Server-Side Request Forgery)
- SQL injection
- API key exposure
"""

import ipaddress
import re
from pathlib import Path
from urllib.parse import urlparse

from .common_utils import logger


class SecurityError(Exception):
    """Raised when a security validation fails."""


class PathSecurityValidator:
    """Validates file paths to prevent path traversal attacks."""

    @staticmethod
    def validate_path(path: str | Path, allowed_base_dirs: list[Path] | None = None) -> Path:
        """
        Validate a path to ensure it's safe from traversal attacks.

        Args:
            path: The path to validate
            allowed_base_dirs: List of allowed base directories. If None, uses current working directory.

        Returns:
            Resolved, validated Path object

        Raises:
            SecurityError: If path validation fails
        """
        # Convert to Path and resolve to absolute path
        path_obj = Path(path).expanduser().resolve()

        # Default to current working directory if no base dirs specified
        if allowed_base_dirs is None:
            allowed_base_dirs = [Path.cwd()]
            # Also allow temp directories for testing
            import tempfile

            temp_dir = Path(tempfile.gettempdir())
            allowed_base_dirs.append(temp_dir)

        # Ensure all base dirs are absolute
        allowed_base_dirs = [Path(d).resolve() for d in allowed_base_dirs]

        # Check if the resolved path is within any allowed base directory
        is_allowed = False
        for base_dir in allowed_base_dirs:
            try:
                # This will raise ValueError if path is not relative to base_dir
                path_obj.relative_to(base_dir)
                is_allowed = True
                break
            except ValueError:
                continue

        if not is_allowed:
            raise SecurityError(
                f"Path '{path}' is outside allowed directories. Resolved to: {path_obj}"
            )

        # Additional checks for suspicious patterns
        path_str = str(path_obj)

        # Check for null bytes
        if "\x00" in path_str:
            raise SecurityError(f"Path contains null bytes: {path}")

        # Check for URL encoding that might bypass checks
        if "%" in str(path) and any(x in str(path).upper() for x in ["%2E%2E", "%252E", "%00"]):
            raise SecurityError(f"Path contains suspicious URL encoding: {path}")

        return path_obj

    @staticmethod
    def validate_glob_pattern(pattern: str, allowed_base_dirs: list[Path] | None = None) -> str:
        """
        Validate a glob pattern to ensure it doesn't escape allowed directories.

        Args:
            pattern: Glob pattern to validate
            allowed_base_dirs: List of allowed base directories

        Returns:
            Validated pattern

        Raises:
            SecurityError: If pattern validation fails
        """
        # Check for obvious traversal attempts
        if ".." in pattern:
            raise SecurityError(f"Path traversal detected in pattern: {pattern}")

        # Check for absolute paths (unless they're in allowed dirs)
        if Path(pattern).is_absolute():
            try:
                PathSecurityValidator.validate_path(pattern, allowed_base_dirs)
            except SecurityError:
                raise SecurityError(f"Absolute path not allowed in pattern: {pattern}")

        # Check pattern length
        if len(pattern) > 255:
            raise SecurityError(f"Pattern too long (max 255 chars): {pattern[:50]}...")

        # Check for suspicious characters that might be used for injection
        suspicious_chars = ["\x00", "\n", "\r", ";", "|", "&", "$", "`", "$(", "${"]
        for char in suspicious_chars:
            if char in pattern:
                raise SecurityError(f"Pattern contains suspicious character '{char!r}': {pattern}")

        return pattern


class URLSecurityValidator:
    """Validates URLs to prevent SSRF attacks."""

    # Private IP ranges (RFC 1918, RFC 4193, etc.)
    PRIVATE_IP_RANGES = [
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),  # Loopback
        ipaddress.ip_network("169.254.0.0/16"),  # Link-local
        ipaddress.ip_network("fc00::/7"),  # IPv6 private
        ipaddress.ip_network("::1/128"),  # IPv6 loopback
        ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
    ]

    # Blocked schemes
    BLOCKED_SCHEMES = ["file", "ftp", "sftp", "data", "gopher", "dict", "jar", "ldap"]

    # Blocked ports (common internal services)
    BLOCKED_PORTS = [22, 23, 25, 135, 139, 445, 1433, 3306, 3389, 5432, 5900, 6379, 27017]

    @staticmethod
    def validate_url(
        url: str,
        allow_localhost: bool = False,
        allow_private_ips: bool = False,
        custom_whitelist: list[str] | None = None,
    ) -> str:
        """
        Validate a URL to prevent SSRF attacks.

        Args:
            url: URL to validate
            allow_localhost: Whether to allow localhost/127.0.0.1
            allow_private_ips: Whether to allow private IP ranges
            custom_whitelist: List of allowed domains/IPs

        Returns:
            Validated URL

        Raises:
            SecurityError: If URL validation fails
        """
        # Basic URL validation
        try:
            parsed = urlparse(url)
        except Exception as e:
            raise SecurityError(f"Invalid URL format: {url}. Error: {e}")

        # Check scheme
        if not parsed.scheme:
            raise SecurityError(f"URL missing scheme: {url}")

        if parsed.scheme not in ["http", "https"]:
            if parsed.scheme in URLSecurityValidator.BLOCKED_SCHEMES:
                raise SecurityError(f"Blocked URL scheme '{parsed.scheme}': {url}")
            raise SecurityError(f"Only HTTP(S) URLs allowed, got '{parsed.scheme}': {url}")

        # Check hostname
        if not parsed.hostname:
            raise SecurityError(f"URL missing hostname: {url}")

        hostname = parsed.hostname.lower()

        # Check against custom whitelist first
        if custom_whitelist:
            if hostname in custom_whitelist:
                return url
            # Check if it's a subdomain of a whitelisted domain
            for allowed in custom_whitelist:
                if hostname.endswith(f".{allowed}"):
                    return url

        # Check for localhost
        if hostname in ["localhost", "127.0.0.1", "::1", "0.0.0.0"]:  # noqa: S104
            if not allow_localhost:
                raise SecurityError(f"Localhost URLs not allowed: {url}")

        # Try to resolve to IP and check if it's private
        try:
            # Check if hostname is already an IP
            ip = ipaddress.ip_address(hostname)
        except ValueError:
            # It's a domain name, try to resolve it
            import socket

            try:
                # Get the IP address
                ip_str = socket.gethostbyname(hostname)
                ip = ipaddress.ip_address(ip_str)
            except (socket.gaierror, ValueError):
                # Can't resolve, but that's okay - let it fail naturally later
                ip = None

        if ip:
            # Check if it's a private IP
            is_private = any(ip in network for network in URLSecurityValidator.PRIVATE_IP_RANGES)
            if is_private and not allow_private_ips:
                raise SecurityError(f"Private IP addresses not allowed: {url} resolves to {ip}")

        # Check port
        port = parsed.port
        if port and port in URLSecurityValidator.BLOCKED_PORTS:
            raise SecurityError(f"Blocked port {port}: {url}")

        # Additional security checks

        # Check for CRLF injection
        if "\r" in url or "\n" in url:
            raise SecurityError(f"URL contains CRLF characters: {url}")

        # Check URL length (prevent DoS)
        if len(url) > 2048:
            raise SecurityError(f"URL too long (max 2048 chars): {url[:50]}...")

        return url


class SecretsMasker:
    """Handles masking of sensitive information in logs and outputs."""

    # Patterns for common secrets
    SECRET_PATTERNS = [
        (r'(api[_-]?key["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', "API_KEY"),
        (r'(token["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', "TOKEN"),
        (r'(password["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', "PASSWORD"),
        (r'(secret["\']?\s*[:=]\s*["\']?)([^"\'\s]+)', "SECRET"),
        (r"\b(sk-[a-zA-Z0-9]{48})\b", "OPENAI_KEY"),  # OpenAI API key pattern
        (r"\b(xoxb-[0-9]{10,13}-[0-9]{10,13}-[a-zA-Z0-9]{24})\b", "SLACK_TOKEN"),
        (r"\b([A-Za-z0-9+/]{40})\b", "POSSIBLE_KEY"),  # Generic base64 key
    ]

    @staticmethod
    def mask_value(value: str, visible_chars: int = 4) -> str:
        """
        Mask a sensitive value, showing only the first few characters.

        Args:
            value: Value to mask
            visible_chars: Number of characters to show at the beginning

        Returns:
            Masked value
        """
        if not value or len(value) <= visible_chars:
            return "***"

        return value[:visible_chars] + "*" * (min(len(value) - visible_chars, 20))

    @staticmethod
    def mask_dict(data: dict, sensitive_keys: list[str] | None = None) -> dict:
        """
        Mask sensitive values in a dictionary.

        Args:
            data: Dictionary to mask
            sensitive_keys: List of keys to mask. If None, uses common patterns.

        Returns:
            Dictionary with masked values
        """
        if sensitive_keys is None:
            sensitive_keys = [
                "api_key",
                "apikey",
                "token",
                "password",
                "secret",
                "auth",
                "authorization",
                "private_key",
                "privatekey",
            ]

        masked_data = {}
        for key, value in data.items():
            key_lower = key.lower()
            if any(sensitive in key_lower for sensitive in sensitive_keys):
                if isinstance(value, str):
                    masked_data[key] = SecretsMasker.mask_value(value)
                else:
                    masked_data[key] = "***"
            elif isinstance(value, dict):
                masked_data[key] = SecretsMasker.mask_dict(value, sensitive_keys)
            else:
                masked_data[key] = value

        return masked_data

    @staticmethod
    def mask_url(url: str) -> str:
        """
        Mask sensitive parts of a URL (like passwords in basic auth).

        Args:
            url: URL to mask

        Returns:
            Masked URL
        """
        try:
            parsed = urlparse(url)
            if parsed.password:
                # Mask password in URLs like http://user:pass@host  # pragma: allowlist secret
                masked_auth = f"{parsed.username}:***"
                masked_netloc = f"{masked_auth}@{parsed.hostname}"
                if parsed.port:
                    masked_netloc += f":{parsed.port}"

                return url.replace(parsed.netloc, masked_netloc)
        except Exception:
            # If parsing fails, return as is rather than exposing internals
            pass

        return url

    @staticmethod
    def mask_log_message(message: str) -> str:
        """
        Mask common secret patterns in a log message.

        Args:
            message: Log message to mask

        Returns:
            Masked message
        """
        masked_message = message

        for pattern, name in SecretsMasker.SECRET_PATTERNS:
            matches = re.finditer(pattern, masked_message, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    # Pattern with prefix and value
                    prefix = match.group(1)
                    replacement = f"{prefix}***_{name}_MASKED***"
                else:
                    # Pattern matching just the secret
                    replacement = f"***_{name}_MASKED***"

                masked_message = masked_message.replace(match.group(0), replacement)

        return masked_message


class InputSanitizer:
    """Sanitizes user inputs to prevent injection attacks."""

    @staticmethod
    def sanitize_metadata_value(value: str) -> str:
        """
        Sanitize a metadata value to prevent injection attacks while preserving JSON.

        Args:
            value: Value to sanitize

        Returns:
            Sanitized value
        """
        # Remove null bytes
        value = value.replace("\x00", "")

        # Check if this looks like JSON (starts with { or [ and ends with } or ])
        is_json = False
        trimmed = value.strip()
        if (trimmed.startswith("{") and trimmed.endswith("}")) or (
            trimmed.startswith("[") and trimmed.endswith("]")
        ):
            # Validate it's actually valid JSON
            try:
                import json

                json.loads(trimmed)
                is_json = True
            except (json.JSONDecodeError, ValueError):
                # Not valid JSON, treat as regular string
                is_json = False

        if is_json:
            # For valid JSON, we need to be careful not to break the JSON structure
            # The JSON itself provides a level of escaping/safety
            # We only need to prevent breaking out of the JSON context in shell
            # Since JSON is already quoted/escaped internally, we can leave it mostly intact
            # Just remove the most dangerous items that could break shell parsing
            value = value.replace("\x00", "")  # Null bytes
            value = value.replace("\n", "\\n")  # Newlines should be escaped in JSON anyway
            value = value.replace("\r", "\\r")  # Carriage returns too
        else:
            # For non-JSON values, be more aggressive with sanitization
            # Remove/escape potentially dangerous characters for shell commands
            dangerous_chars = [
                "$",
                "`",
                "\\",
                "\n",
                "\r",
                ";",
                "|",
                "&",
                ">",
                "<",
                "(",
                ")",
                "{",
                "}",
            ]
            for char in dangerous_chars:
                value = value.replace(char, f"\\{char}")

        # Limit length to prevent DoS
        max_length = 1000
        if len(value) > max_length:
            value = value[:max_length]
            logger.warning(f"Metadata value truncated to {max_length} characters")

        return value

    @staticmethod
    def sanitize_search_query(query: str) -> str:
        """
        Sanitize a search query to prevent injection while preserving search functionality.

        Args:
            query: Search query to sanitize

        Returns:
            Sanitized query
        """
        # Remove null bytes
        query = query.replace("\x00", "")

        # For search queries, we want to be more permissive but still safe
        # Remove SQL comment indicators
        query = re.sub(r"--.*$", "", query)  # SQL line comments
        query = re.sub(r"/\*.*?\*/", "", query, flags=re.DOTALL)  # SQL block comments

        # Remove obvious SQL injection attempts
        sql_keywords = ["DROP", "DELETE", "INSERT", "UPDATE", "CREATE", "ALTER", "EXEC", "EXECUTE"]
        for keyword in sql_keywords:
            # Case-insensitive replacement with space to preserve query flow
            query = re.sub(rf"\b{keyword}\b", " ", query, flags=re.IGNORECASE)

        # Clean up extra whitespace
        query = " ".join(query.split())

        # Limit length
        max_length = 500
        if len(query) > max_length:
            query = query[:max_length]

        return query.strip()


# Convenience functions for common use cases


def validate_file_path(path: str | Path, allowed_dirs: list[Path] | None = None) -> Path:
    """Validate a file path for security."""
    return PathSecurityValidator.validate_path(path, allowed_dirs)


def validate_url(url: str, **kwargs) -> str:
    """Validate a URL for security."""
    return URLSecurityValidator.validate_url(url, **kwargs)


def mask_secrets(text: str) -> str:
    """Mask secrets in text."""
    return SecretsMasker.mask_log_message(text)


def sanitize_input(value: str, input_type: str = "metadata") -> str:
    """Sanitize user input based on type."""
    if input_type == "metadata":
        return InputSanitizer.sanitize_metadata_value(value)
    elif input_type == "search":
        return InputSanitizer.sanitize_search_query(value)
    else:
        # Default to metadata sanitization for safety
        return InputSanitizer.sanitize_metadata_value(value)
