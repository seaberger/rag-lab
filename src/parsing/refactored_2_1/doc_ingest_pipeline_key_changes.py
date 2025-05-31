# Add at the top of the file
from pipeline_utils import (
    DocumentValidator,
    ValidationError,
    ParseError,
    retry_api_call,
    logger,
)
from cache_manager import CacheManager
from progress_monitor import ProgressMonitor


# Update the main ingestion function
async def ingest_sources(
    sources: Iterable[str | Path],
    *,
    prompt_file: str | None = None,
    with_keywords: bool = False,
    keyword_model: str = "gpt-4o-mini",
    config_file: str = "config.yaml",
):
    """Enhanced ingestion with caching, validation, and progress tracking."""

    # Load configuration
    config = PipelineConfig(config_file)

    # Initialize components
    cache = CacheManager() if config.enable_cache else None
    validator = DocumentValidator(config)
    progress = ProgressMonitor(
        callback=_progress_callback if config.progress_callback else None
    )

    # Process documents
    for src in sources:
        doc_id = None
        try:
            # Start tracking
            progress.start_document(doc_id or "unknown", str(src))

            # Validate source
            if str(src).startswith("http"):
                validator.validate_url(str(src))
            else:
                validator.validate_file(Path(src), config.max_file_size)

            # Fetch and hash
            with progress.stage("fetching"):
                pdf_path, doc_id, raw_bytes = await fetch_document(src)

            # Check cache
            if cache:
                cached = cache.get(doc_id, prompt_hash)
                if cached:
                    progress.complete_document(
                        doc_id, cached.get("chunks", 0), cached=True
                    )
                    continue

            # Parse document
            with progress.stage("parsing"):
                if pdf_path.suffix.lower() == ".pdf":
                    markdown, pairs = await parse_with_retry(pdf_path, prompt_text)
                else:
                    markdown = pdf_path.read_text()
                    pairs = []

            # Process and store
            # ... rest of processing ...

            # Cache result
            if cache:
                cache.put(
                    doc_id,
                    prompt_hash,
                    {"markdown": markdown, "pairs": pairs, "chunks": len(nodes)},
                )

            progress.complete_document(doc_id, len(nodes))

        except Exception as e:
            logger.error(f"Failed to process {src}: {e}")
            progress.fail_document(doc_id or str(src), str(e))
            if not config.continue_on_error:
                raise

    # Save report
    if config.save_report:
        progress.save_report()

    # Log summary
    summary = progress.get_summary()
    logger.info(
        f"Pipeline complete: {summary['processed_docs']}/{summary['total_docs']} processed"
    )
