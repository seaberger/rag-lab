from pathlib import Path
from typing import Iterable, Optional, Union

# Third-party
from llama_index.core import StorageContext, VectorStoreIndex
from llama_index.vector_stores.qdrant import QdrantVectorStore # Check if this is the correct import path for your LlamaIndex version
from qdrant_client import QdrantClient
from tqdm import tqdm

# Project-specific
from ..storage.cache import CacheManager # FIXME: Verify CacheManager class name and existence in cache.py
from ..utils.chunking_metadata import process_and_index_document # Added import
from ..utils.common_utils import logger # FIXME: Ensure logger is configured and available
from ..utils.config import PipelineConfig
from ..utils.monitoring import ProgressMonitor # FIXME: Verify ProgressMonitor class name
from .parsers import DocumentClassifier, parse_document

# FIXME: These names are used but not defined/imported in this snippet.
# They might come from other local modules, constants files, or need to be implemented/moved.
# Example: from .helpers import fetch_document, _resolve_prompt
# Example: from .models import DatasheetArtefact
# Example: from .processing import process_and_index_document
# Example: from .constants import ARTEFACT_DIR, VECTOR_DB_PATH

# Placeholder definitions or values (remove or replace with actual imports/definitions)
ARTEFACT_DIR = Path("./artefacts") # Placeholder
VECTOR_DB_PATH = "./qdrant_data" # Placeholder

async def fetch_document(source: Union[str, Path]): # Placeholder
    logger.warning(f"fetch_document is a placeholder for {source}")
    # Returns: pdf_path, doc_id, raw_bytes
    return Path(source) if isinstance(source, Path) else Path(str(source)), str(source), b""

class DatasheetArtefact: # Placeholder
    def __init__(self, doc_id, source, pairs, markdown, parse_version, metadata):
        self.doc_id = doc_id
        self.source = source
        self.pairs = pairs
        self.markdown = markdown
        self.parse_version = parse_version
        self.metadata = metadata
    def to_jsonl(self):
        return "{}"

# Removed placeholder for process_and_index_document as it's now imported

def _resolve_prompt(prompt_file: Optional[str]) -> str: # Placeholder
    if prompt_file:
        logger.warning(f"_resolve_prompt is a placeholder for {prompt_file}")
        return "Placeholder prompt text from file"
    return "Placeholder default prompt text"


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

    config = PipelineConfig.from_yaml(config_file) # Assuming from_yaml is the intended constructor
    cache = CacheManager() if config.cache.enabled else None # Adjusted to example config structure
    progress = ProgressMonitor()

    # Initialize storage
    # FIXME: VECTOR_DB_PATH should ideally come from config.qdrant.path
    qclient = QdrantClient(path=config.qdrant.path if hasattr(config, 'qdrant') else VECTOR_DB_PATH)
    # FIXME: collection_name should ideally come from config.qdrant.collection_name
    vstore = QdrantVectorStore(client=qclient, collection_name=config.qdrant.collection_name if hasattr(config, 'qdrant') else "datasheets")
    storage = StorageContext.from_defaults(vector_store=vstore)

    # FIXME: prompt_file / prompt_text resolution logic may need adjustment based on _resolve_prompt actual implementation
    # And config.parser.datasheet_prompt_path might be relevant.
    prompt_text = _resolve_prompt(prompt_file or (config.parser.datasheet_prompt_path if hasattr(config, 'parser') else None) )

    for src in tqdm(sources, desc="Processing documents"):
        try:
            # Classify document type
            doc_type = DocumentClassifier.classify(src, is_datasheet_mode)

            # Fetch document
            pdf_path, doc_id, raw_bytes = await fetch_document(src)
            progress.start_document(doc_id, str(src), len(raw_bytes))

            # Skip if already processed
            # FIXME: ARTEFACT_DIR should be configurable or a well-defined constant path
            artefact_path = (ARTEFACT_DIR if isinstance(ARTEFACT_DIR, Path) else Path(ARTEFACT_DIR)) / f"{doc_id}.jsonl"
            if artefact_path.exists():
                progress.complete_document(doc_id, cached=True)
                continue

            # Parse based on document type
            # FIXME: is_datasheet_mode should ideally come from config.datasheet_mode
            markdown, pairs, metadata = await parse_document(
                pdf_path, doc_type, prompt_text, cache # Pass cache instance
            )

            # Save artefact with all metadata
            # Ensure DatasheetArtefact is defined or imported
            artefact = DatasheetArtefact(
                doc_id=doc_id,
                source=str(src),
                pairs=pairs,  # Empty for non-datasheet docs
                markdown=markdown,
                parse_version=2,
                metadata=metadata,  # Add this field to DatasheetArtefact
            )
            artefact_path.write_text(artefact.to_jsonl())

            # Process and index
            nodes = await process_and_index_document(
                doc_id=doc_id,
                source=str(src),
                markdown=markdown,
                pairs=pairs,
                metadata=metadata,
                with_keywords=with_keywords,
                progress=progress,
            )

            # Index nodes
            index = VectorStoreIndex.from_nodes(nodes, storage_context=storage)

            progress.complete_document(doc_id, len(nodes))

        except Exception as e:
            logger.error(f"Failed to process {src}: {e}")
            progress.fail_document(doc_id, str(e))
            raise

    # Save final report
    progress.save_report()
    logger.info(f"Ingestion complete: {progress.get_summary()}")
