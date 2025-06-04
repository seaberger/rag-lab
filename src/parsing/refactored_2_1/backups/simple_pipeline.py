#!/usr/bin/env python3
"""
Simplified datasheet ingestion pipeline - all components in one file for easy execution.
"""

import asyncio
import base64
import hashlib
import io
import json
import logging
import os
import shutil
import sys
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
from openai import OpenAI
from pdf2image import convert_from_path


# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_environment(start_dir: Optional[str] = None) -> bool:
    """Complete environment setup: find .env, load it, and verify required keys."""
    logger.info("🔧 Setting up environment...")
    
    # Try to find and load .env file
    try:
        from dotenv import load_dotenv
        
        # Walk up directory tree to find .env
        current_dir = Path(start_dir) if start_dir else Path.cwd()
        while current_dir != current_dir.parent:
            env_path = current_dir / ".env"
            if env_path.exists():
                logger.info(f"Found .env file at: {env_path}")
                load_dotenv(env_path)
                break
            current_dir = current_dir.parent
        else:
            logger.info("No .env file found in directory tree")
            
    except ImportError:
        logger.warning("python-dotenv not installed. Skipping .env file loading.")
    
    # Verify API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.error("❌ OPENAI_API_KEY not found in environment variables!")
        return False
    
    if not api_key.startswith("sk-"):
        logger.warning("⚠️ OPENAI_API_KEY doesn't start with 'sk-', may be invalid")
        return False
    
    logger.info("✅ OpenAI API key found in environment")
    return True


def find_poppler() -> Optional[str]:
    """Return directory that contains pdfinfo/pdftoppm (Poppler) or None."""
    exe = shutil.which("pdfinfo")
    return None if exe is None else str(Path(exe).parent)


def pdf_to_data_uris(pdf_path: Path, dpi: int = 150, poppler_path: Optional[str] = None) -> List[str]:
    """Convert PDF pages to base64 data URIs for OpenAI Vision API."""
    
    # Auto-discover Poppler if not provided
    if poppler_path is None:
        poppler_path = find_poppler()
        if poppler_path is None:
            logger.warning("Poppler not found in PATH. PDF conversion may fail.")
    
    try:
        # Convert PDF pages to PIL Images
        images = convert_from_path(
            str(pdf_path),
            dpi=dpi,
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


class DocumentType(Enum):
    MARKDOWN = "markdown"
    DATASHEET_PDF = "datasheet_pdf"
    GENERIC_PDF = "generic_pdf"


def classify_document(source: Union[str, Path], is_datasheet_mode: bool = True) -> DocumentType:
    """Classify document type based on file extension and heuristics."""
    path = Path(source) if isinstance(source, Path) else Path(str(source))

    # Markdown and text files
    if path.suffix.lower() in {".md", ".markdown", ".txt"}:
        return DocumentType.MARKDOWN

    # PDF files
    if path.suffix.lower() == ".pdf":
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

    raise ValueError(f"Unsupported file type: {path.suffix}")


async def parse_datasheet_pdf(pdf_path: Path, prompt_text: str, model: str = "gpt-4o") -> Tuple[str, List[Tuple[str, str]]]:
    """Parse datasheet PDF with model/part number extraction."""
    client = OpenAI()

    # Enhanced prompt structure
    parts = [
        {
            "type": "input_text",
            "text": (
                f"{prompt_text}\n\n"
                "## ADDITIONAL INSTRUCTIONS\n"
                "Return **one Markdown document** with two clearly-separated sections:\n"
                "1. `Metadata:` with the JSON structure containing extracted pairs\n"
                "2. The **entire datasheet** translated into GitHub-flavoured Markdown\n\n"
                "Example format:\n"
                "Metadata: {\n"
                "    'pairs': [\n"
                "        ('PM10K+ DB-25 + USB', '2293937'),\n"
                "        ('PM10K+ RS-232', '2293938')\n"
                "    ]\n"
                "}\n\n"
                "# Document content starts here...\n"
            )
        }
    ]

    # Add PDF pages as images
    parts += [{"type": "input_image", "image_url": uri} for uri in pdf_to_data_uris(pdf_path)]

    # Make API call
    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": parts}],
        temperature=0.0,
    )
    
    md = response.output[0].content[0].text

    # Extract pairs from metadata and clean up the response
    import re
    
    # Remove markdown code fences if present
    md = re.sub(r'^```\w*\n?', '', md, flags=re.MULTILINE)
    md = re.sub(r'^```\s*$', '', md, flags=re.MULTILINE)
    
    lines = md.split("\n")
    pairs = []
    
    # Look for metadata in the response
    for i, line in enumerate(lines):
        if line.strip().startswith("Metadata:"):
            try:
                # Look for the metadata block, might span multiple lines
                metadata_text = ""
                j = i
                brace_count = 0
                started = False
                
                while j < len(lines):
                    current_line = lines[j]
                    metadata_text += current_line + "\n"
                    
                    # Count braces to find complete JSON object
                    for char in current_line:
                        if char == '{':
                            brace_count += 1
                            started = True
                        elif char == '}':
                            brace_count -= 1
                    
                    j += 1
                    
                    # Stop when we have a complete JSON object or hit content
                    if started and brace_count == 0:
                        break
                    if current_line.strip().startswith("#"):
                        break
                
                # Extract and parse JSON
                json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', metadata_text, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    # Convert single quotes to double quotes for valid JSON
                    json_str = re.sub(r"'([^']*)'", r'"\1"', json_str)
                    
                    try:
                        metadata_obj = json.loads(json_str)
                        pairs = [tuple(p) for p in metadata_obj.get('pairs', [])]
                        logger.info(f"Extracted {len(pairs)} pairs from metadata")
                    except json.JSONDecodeError as je:
                        logger.warning(f"JSON decode error: {je}")
                        logger.debug(f"Attempted to parse: {json_str}")
                
                # Remove metadata lines from markdown and find content start
                content_start = j
                for k in range(i, len(lines)):
                    if lines[k].strip().startswith("#"):
                        content_start = k
                        break
                        
                md = "\n".join(lines[content_start:]) if content_start < len(lines) else ""
                break
                
            except Exception as e:
                logger.warning(f"Failed to extract pairs: {e}")
                break

    return md, pairs


async def parse_generic_pdf(pdf_path: Path, prompt_text: str, model: str = "gpt-4o") -> str:
    """Parse generic PDF without pair extraction."""
    client = OpenAI()

    # Generic prompt
    parts = [
        {
            "type": "input_text",
            "text": (
                prompt_text or 
                "Extract all text from this document as GitHub-flavoured Markdown.\n\n"
                "## INSTRUCTIONS\n"
                "- Preserve all tables, headings, lists, and formatting\n"
                "- Maintain document structure and hierarchy\n"
                "- Include any technical specifications or data\n"
                "- Return **only** the Markdown content\n"
            ),
        }
    ]

    # Add PDF pages as images
    parts += [{"type": "input_image", "image_url": uri} for uri in pdf_to_data_uris(pdf_path)]

    response = client.responses.create(
        model=model,
        input=[{"role": "user", "content": parts}],
        temperature=0.0,
    )
    
    return response.output[0].content[0].text


def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if config_path is None:
        config_path = Path("config.yaml")
    
    if not config_path.exists():
        logger.warning(f"Config file not found: {config_path}")
        return {}
    
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def load_prompt(prompt_path: Optional[Path] = None) -> str:
    """Load parsing prompt from file."""
    if prompt_path is None:
        prompt_path = Path("datasheet_parsing_prompt.md")
    
    if not prompt_path.exists():
        logger.warning(f"Prompt file not found: {prompt_path}")
        return "Extract content from this document as GitHub-flavored Markdown."
    
    try:
        return prompt_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Failed to load prompt: {e}")
        return "Extract content from this document as GitHub-flavored Markdown."


async def process_document(
    doc_path: Path,
    output_path: Optional[Path] = None,
    is_datasheet_mode: bool = True,
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Process a single document through the pipeline."""
    
    logger.info(f"Processing document: {doc_path}")
    
    # Classify document
    doc_type = classify_document(doc_path, is_datasheet_mode)
    logger.info(f"Document classified as: {doc_type.value}")
    
    # Load prompt
    prompt_text = load_prompt()
    
    # Generate document ID
    doc_id = hashlib.sha256(str(doc_path).encode()).hexdigest()[:16]
    
    # Parse based on type
    if doc_type == DocumentType.MARKDOWN:
        markdown = doc_path.read_text(encoding="utf-8", errors="ignore")
        pairs = []
        metadata = {"source_type": "markdown"}
        
    elif doc_type == DocumentType.DATASHEET_PDF:
        model = config.get("openai", {}).get("vision_model", "gpt-4o") if config else "gpt-4o"
        markdown, pairs = await parse_datasheet_pdf(doc_path, prompt_text, model)
        metadata = {"source_type": "datasheet_pdf", "extracted_pairs": len(pairs)}
        
    elif doc_type == DocumentType.GENERIC_PDF:
        model = config.get("openai", {}).get("vision_model", "gpt-4o") if config else "gpt-4o"
        markdown = await parse_generic_pdf(doc_path, prompt_text, model)
        pairs = []
        metadata = {"source_type": "generic_pdf"}
    
    # Create artifact
    artifact = {
        "doc_id": doc_id,
        "source": str(doc_path),
        "pairs": pairs,
        "markdown": markdown,
        "parse_version": 2,
        "metadata": metadata,
        "created_at": datetime.utcnow().isoformat(),
        "markdown_length": len(markdown),
        "pairs_count": len(pairs)
    }
    
    # Save artifact if output path specified
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(artifact, f, indent=2, ensure_ascii=False)
        logger.info(f"Artifact saved to: {output_path}")
    
    logger.info(f"✅ Processing complete: {len(pairs)} pairs, {len(markdown)} chars")
    return artifact


async def main():
    """Main CLI interface."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Datasheet Ingestion Pipeline")
    parser.add_argument("document", help="Path to document to process")
    parser.add_argument("--output", "-o", help="Output JSON file path")
    parser.add_argument("--generic", action="store_true", help="Use generic mode instead of datasheet mode")
    parser.add_argument("--config", help="Path to config YAML file")
    
    args = parser.parse_args()
    
    # Setup environment
    if not setup_environment():
        logger.error("❌ Environment setup failed")
        sys.exit(1)
    
    # Load config
    config_path = Path(args.config) if args.config else None
    config = load_config(config_path)
    
    # Process document
    doc_path = Path(args.document)
    if not doc_path.exists():
        logger.error(f"❌ Document not found: {doc_path}")
        sys.exit(1)
    
    output_path = Path(args.output) if args.output else None
    is_datasheet_mode = not args.generic
    
    try:
        artifact = await process_document(doc_path, output_path, is_datasheet_mode, config)
        
        # Print summary
        print("\n🎉 Processing Complete!")
        print(f"📄 Document: {doc_path.name}")
        print(f"📋 Type: {artifact['metadata']['source_type']}")
        print(f"🔢 Pairs extracted: {len(artifact['pairs'])}")
        print(f"📝 Content length: {len(artifact['markdown']):,} chars")
        
        if artifact['pairs']:
            print("📋 Extracted pairs:")
            for model, part in artifact['pairs']:
                print(f"   • {model}: {part}")
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())