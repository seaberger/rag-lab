import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

# Third-party
try:
    from llama_index.core import StorageContext, VectorStoreIndex
    from llama_index.vector_stores.qdrant import QdrantVectorStore
except ImportError as e:
    raise ImportError(
        f"LlamaIndex imports failed: {e}. "
        "Please install with: uv add llama-index llama-index-vector-stores-qdrant"
    )

from qdrant_client import QdrantClient
from tqdm import tqdm

# Project-specific imports - using absolute imports to avoid relative import issues
try:
    from storage.cache import CacheManager
    from storage.keyword_index import BM25Index
    from utils.chunking_metadata import process_and_index_document
    from utils.common_utils import logger
    from utils.config import PipelineConfig
    from utils.monitoring import ProgressMonitor
    from pipeline.parsers import DocumentClassifier, parse_document
except ImportError:
    # Fallback for when running from different directory
    import sys
    sys.path.append(str(Path(__file__).parent.parent))
    from storage.cache import CacheManager
    from storage.keyword_index import BM25Index
    from utils.chunking_metadata import process_and_index_document
    from utils.common_utils import logger
    from utils.config import PipelineConfig
    from utils.monitoring import ProgressMonitor
    from pipeline.parsers import DocumentClassifier, parse_document

# FIXME: These names are used but not defined/imported in this snippet.
# They might come from other local modules, constants files, or need to be implemented/moved.
# Example: from .helpers import fetch_document, _resolve_prompt
# Example: from .models import DatasheetArtefact
# Example: from .processing import process_and_index_document
# Example: from .constants import ARTEFACT_DIR, VECTOR_DB_PATH

# These constants are now handled via configuration

async def fetch_document(source: Union[str, Path]) -> Tuple[Path, str, bytes]:
    """Fetch document from file path or URL.
    
    Returns:
        Tuple of (pdf_path, doc_id, raw_bytes)
    """
    import hashlib
    import aiohttp
    from urllib.parse import urlparse
    
    # Handle URL sources
    if isinstance(source, str) and (source.startswith('http://') or source.startswith('https://')):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(source) as response:
                    response.raise_for_status()
                    raw_bytes = await response.read()
                    
                    # Create doc_id from URL
                    doc_id = hashlib.sha256(source.encode()).hexdigest()[:16]
                    
                    # Save to temporary file
                    parsed_url = urlparse(source)
                    filename = Path(parsed_url.path).name or f"document_{doc_id}"
                    temp_path = Path(f"./temp_{filename}")
                    temp_path.write_bytes(raw_bytes)
                    
                    logger.info(f"Downloaded {len(raw_bytes)} bytes from {source}")
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
    
    def __init__(self, doc_id: str, source: str, pairs: List[Tuple[str, str]], 
                 markdown: str, parse_version: int, metadata: Dict[str, Any]):
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
            "pairs_count": len(self.pairs)
        }
        
        return json.dumps(data, ensure_ascii=False)
    
    @classmethod
    def from_jsonl(cls, jsonl_line: str) -> 'DatasheetArtefact':
        """Create instance from JSONL line."""
        import json
        
        data = json.loads(jsonl_line)
        artifact = cls(
            doc_id=data["doc_id"],
            source=data["source"],
            pairs=data["pairs"],
            markdown=data["markdown"],
            parse_version=data["parse_version"],
            metadata=data["metadata"]
        )
        artifact.created_at = data.get("created_at")
        return artifact

# Removed placeholder for process_and_index_document as it's now imported

def _resolve_prompt(prompt_file: Optional[str]) -> str:
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
                content = prompt_path.read_text(encoding='utf-8')
                logger.info(f"Loaded prompt from {prompt_path}")
                return content
            except Exception as e:
                logger.error(f"Failed to read prompt file {prompt_path}: {e}")
    
    # Try to load default datasheet prompt
    default_prompt_path = Path("datasheet_parsing_prompt.md")
    if default_prompt_path.exists():
        try:
            content = default_prompt_path.read_text(encoding='utf-8')
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


async def ingest_sources(
    sources: Iterable[Union[str, Path]],
    *,
    prompt_file: Optional[str] = None,
    with_keywords: bool = False,
    keyword_model: str = "gpt-4o-mini",
    is_datasheet_mode: bool = True,
    config_file: str = "config.yaml",
):
    """Main ingestion pipeline preserving all three parsing paths."""

    config = PipelineConfig.from_yaml(config_file)
    cache = CacheManager(config=config) if config.cache.enabled else None
    progress = ProgressMonitor()

    # Initialize embedding model with config
    from llama_index.core import Settings
    from llama_index.embeddings.openai import OpenAIEmbedding
    
    embed_model = OpenAIEmbedding(
        model=config.openai.embedding_model,
        dimensions=config.openai.dimensions,
    )
    Settings.embed_model = embed_model

    # Initialize storage
    qclient = QdrantClient(path=config.qdrant.path)
    vstore = QdrantVectorStore(client=qclient, collection_name=config.qdrant.collection_name)
    storage = StorageContext.from_defaults(vector_store=vstore)
    
    # Initialize BM25 keyword index
    keyword_index = BM25Index(config=config)

    prompt_text = _resolve_prompt(prompt_file or config.parser.datasheet_prompt_path)

    for src in tqdm(sources, desc="Processing documents"):
        doc_id = None
        try:
            # Classify document type
            try:
                stage_start = time.time()
                doc_type = DocumentClassifier.classify(src, is_datasheet_mode)
                logger.info(f"Classified {src} as {doc_type.value}")
            except Exception as e:
                logger.error(f"Classification failed for {src}: {e}")
                continue

            # Fetch document
            try:
                pdf_path, doc_id, raw_bytes = await fetch_document(src)
                progress.start_document(doc_id, str(src), len(raw_bytes))
                progress.update_stage(doc_id, "classification", time.time() - stage_start)
                logger.info(f"Fetched document {doc_id} ({len(raw_bytes)} bytes)")
                progress.update_stage(doc_id, "fetch", time.time() - stage_start)
            except Exception as e:
                logger.error(f"Document fetch failed for {src}: {e}")
                if doc_id:
                    progress.fail_document(doc_id, f"Fetch failed: {e}")
                continue

            # Skip if already processed
            artefact_dir = Path(config.storage.base_dir)
            artefact_dir.mkdir(exist_ok=True)
            artefact_path = artefact_dir / f"{doc_id}.jsonl"
            
            if artefact_path.exists():
                logger.info(f"Document {doc_id} already processed, skipping")
                progress.complete_document(doc_id, cached=True)
                continue

            # Parse based on document type
            try:
                parse_start = time.time()
                markdown, pairs, metadata = await parse_document(
                    pdf_path, doc_type, prompt_text, cache, config
                )
                progress.update_stage(doc_id, "parsing", time.time() - parse_start)
                logger.info(f"Parsed {doc_id}: {len(markdown)} chars, {len(pairs)} pairs")
            except Exception as e:
                logger.error(f"Parsing failed for {doc_id}: {e}")
                progress.fail_document(doc_id, f"Parse failed: {e}")
                continue

            # Save artefact with all metadata
            try:
                save_start = time.time()
                artefact = DatasheetArtefact(
                    doc_id=doc_id,
                    source=str(src),
                    pairs=pairs,
                    markdown=markdown,
                    parse_version=2,
                    metadata=metadata,
                )
                artefact_path.write_text(artefact.to_jsonl())
                progress.update_stage(doc_id, "save_artifact", time.time() - save_start)
                logger.info(f"Saved artefact for {doc_id}")
            except Exception as e:
                logger.error(f"Artefact save failed for {doc_id}: {e}")
                progress.fail_document(doc_id, f"Save failed: {e}")
                continue

            # Process and index
            try:
                chunking_start = time.time()
                nodes = await process_and_index_document(
                    doc_id=doc_id,
                    source=str(src),
                    markdown=markdown,
                    pairs=pairs,
                    metadata=metadata,
                    with_keywords=with_keywords,
                    progress=progress,
                    config=config,
                )
                progress.update_stage(doc_id, "chunking", time.time() - chunking_start)
                logger.info(f"Created {len(nodes)} nodes for {doc_id}")
            except Exception as e:
                logger.error(f"Node processing failed for {doc_id}: {e}")
                progress.fail_document(doc_id, f"Node processing failed: {e}")
                continue

            # Index nodes in vector store
            try:
                index_start = time.time()
                index = VectorStoreIndex(nodes, storage_context=storage)
                progress.update_stage(doc_id, "vector_indexing", time.time() - index_start)
                logger.info(f"Vector indexed {len(nodes)} nodes for {doc_id}")
            except Exception as e:
                logger.error(f"Vector indexing failed for {doc_id}: {e}")
                progress.fail_document(doc_id, f"Vector indexing failed: {e}")
                continue

            # Index nodes in keyword store (BM25)
            try:
                keyword_start = time.time()
                keyword_index.index_nodes(nodes, doc_id, str(src), pairs)
                progress.update_stage(doc_id, "keyword_indexing", time.time() - keyword_start)
                logger.info(f"Keyword indexed {len(nodes)} nodes for {doc_id}")
                progress.complete_document(doc_id, len(nodes))
            except Exception as e:
                logger.error(f"Keyword indexing failed for {doc_id}: {e}")
                progress.fail_document(doc_id, f"Keyword indexing failed: {e}")
                continue

        except Exception as e:
            logger.error(f"Unexpected error processing {src}: {e}")
            if doc_id:
                progress.fail_document(doc_id, f"Unexpected error: {e}")
            # Continue processing other documents instead of raising

    # Save final report
    report_file = config.monitoring.report_file
    progress.save_report(report_file)
    logger.info(f"Ingestion complete: {progress.get_summary()}")
    logger.info(f"Detailed report saved to: {report_file}")
