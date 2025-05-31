# The chunking and metadata enhancement remains the same


async def process_and_index_document(
    doc_id: str,
    source: str,
    markdown: str,
    pairs: List[Tuple[str, str]],
    metadata: Dict[str, Any],
    with_keywords: bool = False,
    progress: Optional[ProgressMonitor] = None,
) -> List[TextNode]:
    """Chunk document and add metadata + optional keywords."""

    # Create document with metadata
    doc = Document(
        text=markdown,
        metadata={
            "doc_id": doc_id,
            "source": source,
            "pairs": pairs,  # Model/part number pairs
            **metadata,  # Additional metadata from parsing
        },
    )

    # Chunk using MarkdownNodeParser (preserves structure)
    with progress.stage("chunking") if progress else nullcontext():
        md_parser = MarkdownNodeParser()
        nodes = md_parser.get_nodes_from_documents([doc])

    # Add metadata to each chunk
    for node in nodes:
        node.metadata.update(
            {
                "doc_id": doc_id,
                "pairs": pairs,
                "chunk_index": nodes.index(node),
                "total_chunks": len(nodes),
            }
        )

    # Optional keyword augmentation
    if with_keywords:
        with progress.stage("keywords") if progress else nullcontext():
            if len(nodes) > 50:  # Use batch for large documents
                nodes = await batch_generate_keywords(nodes)
            else:
                keyword_gen = KeywordGenerator()
                nodes = await keyword_gen.atransform(nodes)

    return nodes
