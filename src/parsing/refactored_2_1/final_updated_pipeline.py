# Add to datasheet_ingest_pipeline.py


async def ingest_sources(
    sources: Iterable[Union[str, Path]],
    *,
    prompt_file: Optional[str] = None,
    with_keywords: bool = False,
    keyword_model: str = "gpt-4o-mini",
    config_file: str = "config.yaml",
):
    """Enhanced pipeline with proper embedding and indexing."""

    # Initialize components
    config = PipelineConfig(config_file)
    embedding_manager = EmbeddingManager(
        model=config.embedding_model, chunk_size=config.chunk_size
    )
    bm25_index = BM25Index(db_path="./keyword_index.db")

    # ... existing code ...

    for src in tqdm(sources, desc="Processing documents"):
        try:
            # ... parsing and chunking code ...

            # After getting nodes, embed and index them
            with progress.stage("embedding"):
                embedded_count = await embedding_manager.embed_and_store_nodes(nodes)
                logger.info(f"Embedded {embedded_count} chunks for {doc_id}")

            with progress.stage("indexing"):
                bm25_index.index_nodes(nodes, doc_id, str(src), pairs)
                logger.info(f"Indexed {len(nodes)} chunks for BM25 search")

            progress.complete_document(doc_id, len(nodes))

        except Exception as e:
            logger.error(f"Failed to process {src}: {e}")
            progress.fail_document(doc_id, str(e))
