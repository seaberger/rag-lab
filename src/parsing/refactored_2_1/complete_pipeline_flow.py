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

    config = PipelineConfig(config_file)
    cache = CacheManager() if config.enable_cache else None
    progress = ProgressMonitor()

    # Initialize storage
    qclient = QdrantClient(path=VECTOR_DB_PATH)
    vstore = QdrantVectorStore(client=qclient, collection_name="datasheets")
    storage = StorageContext.from_defaults(vector_store=vstore)

    prompt_text = _resolve_prompt(prompt_file)

    for src in tqdm(sources, desc="Processing documents"):
        try:
            # Classify document type
            doc_type = DocumentClassifier.classify(src, is_datasheet_mode)

            # Fetch document
            pdf_path, doc_id, raw_bytes = await fetch_document(src)
            progress.start_document(doc_id, str(src), len(raw_bytes))

            # Skip if already processed
            artefact_path = ARTEFACT_DIR / f"{doc_id}.jsonl"
            if artefact_path.exists():
                progress.complete_document(doc_id, cached=True)
                continue

            # Parse based on document type
            markdown, pairs, metadata = await parse_document(
                pdf_path, doc_type, prompt_text, cache
            )

            # Save artefact with all metadata
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
