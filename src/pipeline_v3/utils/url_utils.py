"""
URL processing utilities for batch URL handling.

Provides functions to extract URLs from various file formats including
markdown and JSON files for batch document processing.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def extract_urls_from_markdown(file_path: Path) -> list[str]:
    """
    Extract URLs from markdown file.

    Supports:
    - Markdown links: [text](url)
    - Bare URLs: http://example.com
    - List items with URLs

    Args:
        file_path: Path to markdown file

    Returns:
        List of extracted URLs
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        urls = []

        # Pattern for markdown links [text](url)
        markdown_link_pattern = r"\[([^\]]*)\]\(([^)]+)\)"
        markdown_matches = re.findall(markdown_link_pattern, content)
        for _, url in markdown_matches:
            if url.startswith(("http://", "https://")):
                urls.append(url.strip())

        # Pattern for bare URLs
        url_pattern = r'https?://[^\s<>"\[\]{}|\\^`]+'
        url_matches = re.findall(url_pattern, content)
        for url in url_matches:
            # Clean up URL (remove trailing punctuation)
            url = url.rstrip(".,;:!?)")
            urls.append(url)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        logger.info(f"Extracted {len(unique_urls)} URLs from markdown file: {file_path}")
        return unique_urls

    except Exception:
        logger.exception(f"Failed to extract URLs from markdown file {file_path}")
        return []


def extract_urls_from_json(file_path: Path) -> list[str]:
    """
    Extract URLs from JSON file.

    Supports various JSON structures:
    - Simple array: ["url1", "url2"]
    - Object with urls array: {"urls": ["url1", "url2"]}
    - Array of objects with url field: [{"url": "url1", "title": "..."}, ...]
    - Nested structures (searches recursively)

    Args:
        file_path: Path to JSON file

    Returns:
        List of extracted URLs
    """
    try:
        content = file_path.read_text(encoding="utf-8")
        data = json.loads(content)

        urls = []

        def extract_urls_recursive(obj):
            """Recursively extract URLs from JSON structure."""
            if isinstance(obj, str):
                if obj.startswith(("http://", "https://")):
                    urls.append(obj)
            elif isinstance(obj, list):
                for item in obj:
                    extract_urls_recursive(item)
            elif isinstance(obj, dict):
                # Check for common URL field names
                url_fields = ["url", "link", "href", "src", "uri"]
                for field in url_fields:
                    if (
                        field in obj
                        and isinstance(obj[field], str)
                        and obj[field].startswith(("http://", "https://"))
                    ):
                        urls.append(obj[field])

                # Recursively check all values
                for value in obj.values():
                    extract_urls_recursive(value)

        extract_urls_recursive(data)

        # Remove duplicates while preserving order
        seen = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)

        logger.info(f"Extracted {len(unique_urls)} URLs from JSON file: {file_path}")
        return unique_urls

    except json.JSONDecodeError:
        logger.exception(f"Invalid JSON in file {file_path}")
        return []
    except Exception:
        logger.exception(f"Failed to extract URLs from JSON file {file_path}")
        return []


def extract_urls_from_file(file_path: Path) -> list[str]:
    """
    Extract URLs from a file based on its extension.

    Args:
        file_path: Path to file containing URLs

    Returns:
        List of extracted URLs
    """
    if not file_path.exists():
        logger.error(f"File not found: {file_path}")
        return []

    if not file_path.is_file():
        logger.error(f"Path is not a file: {file_path}")
        return []

    suffix = file_path.suffix.lower()

    if suffix == ".md":
        return extract_urls_from_markdown(file_path)
    if suffix == ".json":
        return extract_urls_from_json(file_path)
    logger.error(f"Unsupported file type for URL extraction: {suffix}")
    return []


def create_url_batch_file(urls: list[str], output_path: Path, format_type: str = "json") -> bool:
    """
    Create a batch file containing URLs.

    Args:
        urls: List of URLs to include
        output_path: Path to save the batch file
        format_type: Format to use ('json' or 'markdown')

    Returns:
        True if file was created successfully, False otherwise
    """
    try:
        if format_type == "json":
            data = {
                "description": "Batch URL processing file",
                "urls": urls,
                "total_count": len(urls),
            }
            output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

        elif format_type == "markdown":
            content = [
                "# URL Batch Processing File",
                "",
                f"Total URLs: {len(urls)}",
                "",
            ]

            for i, url in enumerate(urls, 1):
                content.append(f"{i}. [{url}]({url})")

            output_path.write_text("\n".join(content), encoding="utf-8")

        else:
            logger.error(f"Unsupported format type: {format_type}")
            return False

        logger.info(f"Created {format_type} batch file with {len(urls)} URLs: {output_path}")
        return True

    except Exception:
        logger.exception(f"Failed to create batch file {output_path}")
        return False


def validate_url_list(urls: list[str]) -> dict[str, Any]:
    """
    Validate a list of URLs and provide statistics.

    Args:
        urls: List of URLs to validate

    Returns:
        Dictionary with validation results and statistics
    """
    results = {
        "total_urls": len(urls),
        "valid_urls": [],
        "invalid_urls": [],
        "duplicates": [],
        "statistics": {},
    }

    seen_urls = set()

    for url in urls:
        # Check for duplicates
        if url in seen_urls:
            results["duplicates"].append(url)
            continue

        seen_urls.add(url)

        # Basic URL validation
        if url.startswith(("http://", "https://")) and len(url) > 10:
            results["valid_urls"].append(url)
        else:
            results["invalid_urls"].append(url)

    # Generate statistics
    results["statistics"] = {
        "unique_valid_urls": len(results["valid_urls"]),
        "invalid_count": len(results["invalid_urls"]),
        "duplicate_count": len(results["duplicates"]),
        "domains": {},
    }

    # Count domains
    for url in results["valid_urls"]:
        try:
            from urllib.parse import urlparse

            domain = urlparse(url).netloc
            results["statistics"]["domains"][domain] = (
                results["statistics"]["domains"].get(domain, 0) + 1
            )
        except Exception:
            # Ignore URL parsing errors for statistics
            pass

    return results
