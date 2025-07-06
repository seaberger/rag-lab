"""
Production Pipeline v3 - Core Processing Engine

Enhanced pipeline with queue management, document lifecycle operations,
and enterprise-grade reliability features.
"""

from pathlib import Path
from typing import Any

# Third-party imports


# Project-specific imports - using absolute imports to avoid relative import issues
try:
    from utils.cleanup import get_resource_manager
    from utils.common_utils import logger
except ImportError:
    # Fallback for when running from different directory
    import sys

    sys.path.append(str(Path(__file__).parent.parent))

    from utils.cleanup import get_resource_manager
    from utils.common_utils import logger

# Note: Key components like fetch_document and DatasheetArtefact are defined in this module.
# Storage paths and constants are handled via PipelineConfig.


async def fetch_document(source: str | Path) -> tuple[Path, str, bytes]:
    """Fetch document from file path or URL.

    Returns:
        Tuple of (pdf_path, doc_id, raw_bytes)
    """
    import hashlib
    from urllib.parse import urlparse

    import aiohttp

    from utils.security import SecurityError, URLSecurityValidator

    # Handle URL sources
    if isinstance(source, str) and (source.startswith(("http://", "https://"))):
        # Validate URL for security
        try:
            validated_url = URLSecurityValidator.validate_url(
                source, allow_localhost=False, allow_private_ips=False
            )
        except SecurityError as e:
            logger.error(f"URL security validation failed: {e}")
            raise ValueError(f"URL validation failed: {e}")

        try:
            # Configure client with security settings
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            connector = aiohttp.TCPConnector(limit=10, limit_per_host=2)

            async with aiohttp.ClientSession(
                timeout=timeout, connector=connector, headers={"User-Agent": "RAGLab/1.0"}
            ) as session:
                # Add size limit and redirect limit
                async with session.get(
                    validated_url, max_redirects=3, allow_redirects=True
                ) as response:
                    response.raise_for_status()

                    # Check content length to prevent DoS
                    content_length = response.headers.get("Content-Length")
                    max_size = 100 * 1024 * 1024  # 100MB max

                    if content_length and int(content_length) > max_size:
                        raise ValueError(
                            f"File too large: {content_length} bytes (max: {max_size})"
                        )

                    # Read with size limit
                    raw_bytes = b""
                    async for chunk in response.content.iter_chunked(8192):
                        raw_bytes += chunk
                        if len(raw_bytes) > max_size:
                            raise ValueError(
                                f"File too large during download (max: {max_size} bytes)"
                            )

                    if not raw_bytes:
                        raise ValueError("Empty file downloaded")

                    # Create doc_id from URL
                    doc_id = hashlib.sha256(source.encode()).hexdigest()[:16]

                    # Save to temporary file - don't use context manager since we need file to persist
                    import tempfile

                    parsed_url = urlparse(source)
                    filename = Path(parsed_url.path).name or f"document_{doc_id}"
                    suffix = Path(filename).suffix or ".pdf"

                    # Create temporary file without context manager
                    with tempfile.NamedTemporaryFile(
                        mode="wb", suffix=suffix, prefix="download_", delete=False
                    ) as tf:
                        temp_path = Path(tf.name)

                    # Write content to the persistent temp file
                    temp_path.write_bytes(raw_bytes)
                    logger.info(f"Downloaded {len(raw_bytes)} bytes from {source}")

                    # Register with resource manager for cleanup
                    resource_manager = get_resource_manager()
                    resource_manager.register_temp_file(temp_path)

                    return temp_path, doc_id, raw_bytes

        except Exception as e:
            logger.error(f"Failed to fetch URL {source}: {e}")
            raise ValueError(f"URL fetch failed: {e}")

    # Handle local file paths
    else:
        file_path = Path(source) if isinstance(source, str) else source

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        # Read file content
        raw_bytes = file_path.read_bytes()

        # Create doc_id from file path and content
        content_hash = hashlib.sha256(raw_bytes).hexdigest()[:8]
        file_hash = hashlib.sha256(str(file_path).encode()).hexdigest()[:8]
        doc_id = f"{file_path.stem}_{content_hash}_{file_hash}"

        logger.info(f"Loaded {len(raw_bytes)} bytes from {file_path}")
        return file_path, doc_id, raw_bytes


class DatasheetArtefact:
    """Represents a processed document artifact with metadata."""

    def __init__(
        self,
        doc_id: str,
        source: str,
        pairs: list[tuple[str, str]],
        markdown: str,
        parse_version: int,
        metadata: dict[str, Any],
    ):
        self.doc_id = doc_id
        self.source = source
        self.pairs = pairs
        self.markdown = markdown
        self.parse_version = parse_version
        self.metadata = metadata
        self.created_at = None  # Will be set when serialized

    def to_jsonl(self) -> str:
        """Serialize to JSONL format for storage."""
        import json
        from datetime import datetime

        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()

        data = {
            "doc_id": self.doc_id,
            "source": self.source,
            "pairs": self.pairs,
            "markdown": self.markdown,
            "parse_version": self.parse_version,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "markdown_length": len(self.markdown),
            "pairs_count": len(self.pairs),
        }

        return json.dumps(data, ensure_ascii=False)

    @classmethod
    def from_jsonl(cls, jsonl_line: str) -> "DatasheetArtefact":
        """Create instance from JSONL line."""
        import json

        data = json.loads(jsonl_line)
        artifact = cls(
            doc_id=data["doc_id"],
            source=data["source"],
            pairs=data["pairs"],
            markdown=data["markdown"],
            parse_version=data["parse_version"],
            metadata=data["metadata"],
        )
        artifact.created_at = data.get("created_at")
        return artifact


# Removed placeholder for process_and_index_document as it's now imported


def _resolve_prompt(prompt_file: str | None) -> str:
    """Load prompt from file or return default prompt."""

    # If specific prompt file provided, load it
    if prompt_file:
        prompt_path = Path(prompt_file)
        if not prompt_path.exists():
            # Try relative to current directory
            prompt_path = Path.cwd() / prompt_file
        if not prompt_path.exists():
            logger.warning(f"Prompt file not found: {prompt_file}, using default")
        else:
            try:
                content = prompt_path.read_text(encoding="utf-8")
                logger.info(f"Loaded prompt from {prompt_path}")
                return content
            except Exception as e:
                logger.error(f"Failed to read prompt file {prompt_path}: {e}")

    # Try to load default datasheet prompt
    default_prompt_path = Path("datasheet_parsing_prompt.md")
    if default_prompt_path.exists():
        try:
            content = default_prompt_path.read_text(encoding="utf-8")
            logger.info(f"Loaded default prompt from {default_prompt_path}")
            return content
        except Exception as e:
            logger.warning(f"Failed to read default prompt: {e}")

    # Fallback to basic prompt
    default_prompt = """Extract all content from this document as GitHub-flavored Markdown.

For technical datasheets:
- Preserve table structure and formatting
- Include all model numbers and part numbers
- Maintain hierarchical organization

Format tables properly with all cells filled."""

    logger.info("Using built-in default prompt")
    return default_prompt
