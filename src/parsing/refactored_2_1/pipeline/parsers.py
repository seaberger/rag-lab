# In the refactored datasheet_ingest_pipeline.py
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from openai import OpenAI

from ..storage.cache import CacheManager # Assuming CacheManager is the correct class name
from ..utils.common_utils import logger, retry_api_call

# FIXME: Where should OPENAI_MODEL come from? e.g. config.openai.vision_model
# from ..utils.config import PipelineConfig # Example if it's from config
# OPENAI_MODEL = PipelineConfig().openai.vision_model

# FIXME: _pdf_to_data_uris is not defined. It was likely a helper in the original file.
# Placeholder for _pdf_to_data_uris
def _pdf_to_data_uris(pdf_path: Path) -> List[str]:
    # This function needs to be implemented or imported correctly.
    # Example: Convert PDF pages to base64 data URIs.
    logger.warning(f"_pdf_to_data_uris is not implemented for {pdf_path}")
    return []

# FIXME: OPENAI_MODEL is not defined. This should come from config.
OPENAI_MODEL = "gpt-4o"  # Placeholder, replace with config access


class DocumentType(Enum):
    MARKDOWN = "markdown"
    DATASHEET_PDF = "datasheet_pdf"
    GENERIC_PDF = "generic_pdf"


class DocumentClassifier:
    """Classify documents to determine parsing strategy."""

    @staticmethod
    def classify(
        source: Union[str, Path], is_datasheet_mode: bool = True
    ) -> DocumentType:
        path = Path(source) if isinstance(source, Path) else Path(str(source))

        # Markdown files - no model call needed
        if path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return DocumentType.MARKDOWN

        # PDF files - check if datasheet mode
        if path.suffix.lower() == ".pdf":
            if is_datasheet_mode:
                return DocumentType.DATASHEET_PDF
            else:
                return DocumentType.GENERIC_PDF

        raise ValueError(f"Unsupported file type: {path.suffix}")


async def parse_document(
    pdf_path: Path,
    doc_type: DocumentType,
    prompt_text: str,
    cache: Optional[CacheManager] = None,
) -> Tuple[str, List[Tuple[str, str]], Dict[str, Any]]:
    """Parse document based on type."""

    # Check cache first
    if cache:
        # FIXME: doc_hash was undefined. Assuming it's derived from pdf_path.
        # Consider a more robust way to generate this, e.g., hash of file content or path + mtime
        doc_hash_str = hashlib.sha256(str(pdf_path).encode()).hexdigest()
        cache_key = (
            f"{doc_type.value}_{hashlib.sha256(prompt_text.encode()).hexdigest()[:8]}"
        )
        cached = cache.get(doc_hash_str, cache_key) # Use doc_hash_str
        if cached:
            return cached["markdown"], cached["pairs"], cached["metadata"]

    if doc_type == DocumentType.MARKDOWN:
        # Direct read - no API call
        markdown = pdf_path.read_text(encoding="utf-8", errors="ignore")
        pairs = []  # No model/part pairs in markdown
        metadata = {"source_type": "markdown"}

    elif doc_type == DocumentType.DATASHEET_PDF:
        # Use special datasheet prompt with pair extraction
        markdown, pairs = await vision_parse_datasheet(pdf_path, prompt_text)
        metadata = {"source_type": "datasheet_pdf", "extracted_pairs": len(pairs)}

    elif doc_type == DocumentType.GENERIC_PDF:
        # Use generic prompt without pair extraction
        markdown, _ = await vision_parse_generic(pdf_path, prompt_text)
        pairs = []
        metadata = {"source_type": "generic_pdf"}

    # Cache result
    if cache:
        # FIXME: doc_hash was undefined (see above). Using doc_hash_str.
        doc_hash_str = hashlib.sha256(str(pdf_path).encode()).hexdigest()
        cache.put(
            doc_hash_str, # Use doc_hash_str
            cache_key,
            {"markdown": markdown, "pairs": pairs, "metadata": metadata},
        )

    return markdown, pairs, metadata


async def vision_parse_datasheet(
    pdf: Path, parsing_prompt: str
) -> Tuple[str, List[Tuple[str, str]]]:
    """Parse datasheet PDF with model/part number extraction."""
    client = OpenAI()

    # The special datasheet prompt that asks for pairs
    parts = [
        {
            "type": "text",
            "text": f"""{parsing_prompt}

Return one Markdown document that begins with a line:
Metadata: {{ 'pairs': [["model name", "part number"], ...] }}
followed by the full datasheet body. Use GitHub-flavoured tables.""",
        }
    ]

    # Add PDF pages as images
    parts += [{"type": "image_url", "image_url": uri} for uri in _pdf_to_data_uris(pdf)]

    # Make API call with retry
    @retry_api_call(max_attempts=3)
    async def call_api():
        return client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": parts}],
            temperature=0.0,
        )

    response = await call_api()
    md = response.choices[0].message.content

    # Extract pairs from metadata line
    first_line, *rest = md.split("\n", 1)
    try:
        if first_line.startswith("Metadata:"):
            meta = json.loads(first_line.replace("Metadata:", "").strip())
            pairs = [tuple(p) for p in meta.get("pairs", [])]
            # Remove metadata line from markdown
            md = "\n".join(rest) if rest else md
        else:
            pairs = []
    except Exception as e:
        logger.warning(f"Failed to extract pairs: {e}")
        pairs = []

    return md, pairs


async def vision_parse_generic(
    pdf: Path, parsing_prompt: str
) -> Tuple[str, List[Tuple[str, str]]]:
    """Parse generic PDF without pair extraction."""
    client = OpenAI()

    # Simple prompt without metadata request
    parts = [
        {
            "type": "text",
            "text": parsing_prompt or "Extract all text as GitHub-flavoured Markdown.",
        }
    ]

    parts += [{"type": "image_url", "image_url": uri} for uri in _pdf_to_data_uris(pdf)]

    @retry_api_call(max_attempts=3)
    async def call_api():
        return client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": parts}],
            temperature=0.0,
        )

    response = await call_api()
    return response.choices[0].message.content, []
