# In the refactored datasheet_ingest_pipeline.py
import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from openai import OpenAI

# Use absolute imports to avoid relative import issues
try:
    from storage.cache import CacheManager
    from utils.common_utils import logger, retry_api_call
    from utils.config import PipelineConfig
except ImportError:
    # Fallback for when running from different directory
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from storage.cache import CacheManager
    from utils.common_utils import logger, retry_api_call
    from utils.config import PipelineConfig

def _find_poppler() -> Optional[str]:
    """Return directory that contains pdfinfo/pdftoppm (Poppler) or None."""
    import shutil
    exe = shutil.which("pdfinfo")
    return None if exe is None else str(Path(exe).parent)

def _pdf_to_data_uris(pdf_path: Path, dpi: int = 150, poppler_path: Optional[str] = None) -> List[str]:
    """Convert PDF pages to base64 data URIs for OpenAI Vision API."""
    import base64
    import io
    from pdf2image import convert_from_path
    
    # Auto-discover Poppler if not provided
    if poppler_path is None:
        poppler_path = _find_poppler()
        if poppler_path is None:
            logger.warning("Poppler not found in PATH. PDF conversion may fail.")
    
    try:
        # Convert PDF pages to PIL Images
        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,  # Configurable DPI
            fmt='RGB',
            poppler_path=poppler_path
        )
        
        data_uris = []
        for i, image in enumerate(images):
            # Convert PIL Image to base64 data URI
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=85)
            img_bytes = buffer.getvalue()
            
            # Create data URI
            base64_string = base64.b64encode(img_bytes).decode('utf-8')
            data_uri = f"data:image/jpeg;base64,{base64_string}"
            data_uris.append(data_uri)
            
            logger.debug(f"Converted page {i+1}/{len(images)} of {pdf_path.name}")
        
        logger.info(f"Converted {len(data_uris)} pages from {pdf_path.name}")
        return data_uris
        
    except Exception as e:
        logger.error(f"Failed to convert PDF {pdf_path} to data URIs: {e}")
        raise ValueError(f"PDF conversion failed: {e}")

# Load model from config when needed


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
        """Classify document type based on file extension and heuristics."""
        path = Path(source) if isinstance(source, Path) else Path(str(source))

        # Markdown and text files - no model call needed
        if path.suffix.lower() in {".md", ".markdown", ".txt"}:
            return DocumentType.MARKDOWN

        # PDF files - check if datasheet mode with additional heuristics
        if path.suffix.lower() == ".pdf":
            return DocumentClassifier._classify_pdf(path, is_datasheet_mode)

        raise ValueError(f"Unsupported file type: {path.suffix}")

    @staticmethod
    def _classify_pdf(path: Path, is_datasheet_mode: bool) -> DocumentType:
        """Classify PDF based on filename patterns and mode."""
        filename_lower = path.name.lower()
        
        # Strong indicators for datasheets
        datasheet_indicators = [
            'datasheet', 'ds.pdf', 'spec', 'specification', 
            'product_brief', 'technical_data', 'sensor', 'laser',
            'manual', 'model', 'part_number'
        ]
        
        # Strong indicators for generic documents
        generic_indicators = [
            'report', 'paper', 'article', 'research', 'white_paper',
            'guide', 'tutorial', 'documentation', 'readme'
        ]
        
        # Check filename patterns
        has_datasheet_pattern = any(indicator in filename_lower for indicator in datasheet_indicators)
        has_generic_pattern = any(indicator in filename_lower for indicator in generic_indicators)
        
        # Decision logic
        if has_datasheet_pattern and not has_generic_pattern:
            logger.info(f"Detected datasheet pattern in filename: {path.name}")
            return DocumentType.DATASHEET_PDF
        elif has_generic_pattern and not has_datasheet_pattern:
            logger.info(f"Detected generic document pattern in filename: {path.name}")
            return DocumentType.GENERIC_PDF
        else:
            # Fall back to mode setting
            if is_datasheet_mode:
                logger.info(f"Using datasheet mode for PDF: {path.name}")
                return DocumentType.DATASHEET_PDF
            else:
                logger.info(f"Using generic mode for PDF: {path.name}")
                return DocumentType.GENERIC_PDF

    @staticmethod
    def get_confidence(source: Union[str, Path], doc_type: DocumentType) -> float:
        """Get confidence score for classification."""
        path = Path(source) if isinstance(source, Path) else Path(str(source))
        
        if doc_type == DocumentType.MARKDOWN:
            return 1.0  # Always confident about markdown files
        
        filename_lower = path.name.lower()
        
        if doc_type == DocumentType.DATASHEET_PDF:
            datasheet_indicators = [
                'datasheet', 'ds.pdf', 'spec', 'specification', 
                'product_brief', 'technical_data', 'sensor', 'laser'
            ]
            matches = sum(1 for indicator in datasheet_indicators if indicator in filename_lower)
            return min(0.9, 0.5 + (matches * 0.2))  # 0.5-0.9 based on matches
        
        elif doc_type == DocumentType.GENERIC_PDF:
            generic_indicators = [
                'report', 'paper', 'article', 'research', 'white_paper'
            ]
            matches = sum(1 for indicator in generic_indicators if indicator in filename_lower)
            return min(0.9, 0.5 + (matches * 0.2))  # 0.5-0.9 based on matches
        
        return 0.5  # Default medium confidence


async def parse_document(
    pdf_path: Path,
    doc_type: DocumentType,
    prompt_text: str,
    cache: Optional[CacheManager] = None,
    config: Optional[PipelineConfig] = None,
) -> Tuple[str, List[Tuple[str, str]], Dict[str, Any]]:
    """Parse document based on type."""

    # Check cache first
    if cache:
        # Generate robust content-based hash for cache key
        try:
            # Read file content for hashing
            file_content = pdf_path.read_bytes()
            content_hash = hashlib.sha256(file_content).hexdigest()
        except Exception:
            # Fallback to path-based hash if content read fails
            content_hash = hashlib.sha256(str(pdf_path).encode()).hexdigest()
        
        # Create cache key that includes content + prompt + doc_type
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
        cache_key = f"{doc_type.value}_{content_hash[:12]}_{prompt_hash}"
        
        cached = cache.get(content_hash, cache_key)
        if cached:
            return cached["markdown"], cached["pairs"], cached["metadata"]

    if doc_type == DocumentType.MARKDOWN:
        # Direct read - no API call
        markdown = pdf_path.read_text(encoding="utf-8", errors="ignore")
        pairs = []  # No model/part pairs in markdown
        metadata = {
            "source_type": "markdown",
            "file_name": pdf_path.name,
            "file_size": pdf_path.stat().st_size,
            "content_length": len(markdown),
            "parse_method": "direct_read"
        }

    elif doc_type == DocumentType.DATASHEET_PDF:
        # Use special datasheet prompt with pair extraction
        markdown, pairs = await vision_parse_datasheet(pdf_path, prompt_text, config)
        metadata = {
            "source_type": "datasheet_pdf", 
            "extracted_pairs": len(pairs),
            "file_name": pdf_path.name,
            "file_size": pdf_path.stat().st_size,
            "content_length": len(markdown),
            "parse_method": "openai_vision"
        }

    elif doc_type == DocumentType.GENERIC_PDF:
        # Use generic prompt without pair extraction
        markdown, _ = await vision_parse_generic(pdf_path, prompt_text, config)
        pairs = []
        metadata = {
            "source_type": "generic_pdf",
            "file_name": pdf_path.name,
            "file_size": pdf_path.stat().st_size,
            "content_length": len(markdown),
            "parse_method": "openai_vision"
        }

    # Cache result
    if cache:
        # Use the same content hash and cache key generated earlier
        try:
            file_content = pdf_path.read_bytes()
            content_hash = hashlib.sha256(file_content).hexdigest()
        except Exception:
            content_hash = hashlib.sha256(str(pdf_path).encode()).hexdigest()
        
        prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:12]
        cache_key = f"{doc_type.value}_{content_hash[:12]}_{prompt_hash}"
        
        cache.put(
            content_hash,
            cache_key,
            {"markdown": markdown, "pairs": pairs, "metadata": metadata},
        )

    return markdown, pairs, metadata


async def vision_parse_datasheet(
    pdf: Path, parsing_prompt: str, config: Optional[PipelineConfig] = None
) -> Tuple[str, List[Tuple[str, str]]]:
    """Parse datasheet PDF with model/part number extraction."""
    client = OpenAI()

    # Get model from config or use default
    model = config.openai.vision_model if config else "gpt-4o"
    max_retries = config.openai.max_retries if config else 3

    # Enhanced prompt structure from notebook
    parts = [
        {
            "type": "input_text",
            "text": (
                f"{parsing_prompt}\n\n"
                "## ADDITIONAL INSTRUCTIONS\n"
                "Return **one Markdown document** with two clearly-separated sections:\n"
                "1. `Metadata:` keep exactly the JSON structure shown below and fill the "
                "`pairs` list you extracted (no extra keys).\n"
                "2. The **entire datasheet** translated into GitHub-flavoured Markdown, "
                "preserving all tables, headings, lists, line-breaks, and footnotes.\n\n"
                "Example top of output (do not include the ``` fences):\n"
                "Metadata: {\n"
                "    'pairs': [\n"
                "        ('PM10K+ DB-25 + USB', '2293937'),\n"
                "        ('PM10K+ RS-232', '2293938')\n"
                "    ]\n"
                "}\n\n"
                "---  ← leave one blank line, then start the document body ---\n"
            )
        }
    ]

    # Add PDF pages as images (Responses API format) 
    dpi = config.pdf.dpi if config and hasattr(config, 'pdf') else 150
    parts += [{"type": "input_image", "image_url": uri} for uri in _pdf_to_data_uris(pdf, dpi=dpi)]

    # Make API call with retry using Responses API
    @retry_api_call(max_attempts=max_retries)
    async def call_api():
        return client.responses.create(
            model=model,
            input=[{"role": "user", "content": parts}],
            temperature=0.0,
        )

    response = await call_api()
    md = response.output[0].content[0].text

    # Extract pairs from metadata line
    first_line, *rest = md.split("\n", 1)
    try:
        if first_line.startswith("Metadata:"):
            metadata_text = first_line.replace("Metadata:", "").strip()
            # Handle single quotes in the response by converting to double quotes
            metadata_text = metadata_text.replace("'", '"')
            meta = json.loads(metadata_text)
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
    pdf: Path, parsing_prompt: str, config: Optional[PipelineConfig] = None
) -> Tuple[str, List[Tuple[str, str]]]:
    """Parse generic PDF without pair extraction."""
    client = OpenAI()

    # Get model from config or use default
    model = config.openai.vision_model if config else "gpt-4o"
    max_retries = config.openai.max_retries if config else 3

    # Enhanced prompt for generic PDFs
    parts = [
        {
            "type": "input_text",
            "text": (parsing_prompt or 
                "Extract all text from this document as GitHub-flavoured Markdown.\n\n"
                "## INSTRUCTIONS\n"
                "- Preserve all tables, headings, lists, and formatting\n"
                "- Maintain document structure and hierarchy\n"
                "- Include any technical specifications or data\n"
                "- Return **only** the Markdown content\n"
            ),
        }
    ]

    # Add PDF pages as images with configurable DPI
    dpi = config.pdf.dpi if config and hasattr(config, 'pdf') else 150
    parts += [{"type": "input_image", "image_url": uri} for uri in _pdf_to_data_uris(pdf, dpi=dpi)]

    @retry_api_call(max_attempts=max_retries)
    async def call_api():
        return client.responses.create(
            model=model,
            input=[{"role": "user", "content": parts}],
            temperature=0.0,
        )

    response = await call_api()
    return response.output[0].content[0].text, []
