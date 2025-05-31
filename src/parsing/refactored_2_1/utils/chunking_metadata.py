# The chunking and metadata enhancement remains the same
from contextlib import nullcontext
from typing import Any, Dict, List, Optional, Tuple

from llama_index.core.node_parser import MarkdownNodeParser # Or MarkdownNodeParser from llama_index.node_parser
from llama_index.core.schema import Document, TextNode

from .monitoring import ProgressMonitor

# FIXME: batch_generate_keywords and KeywordGenerator are not defined.
# They might come from another local module (e.g., .keywords) or need to be defined/moved here.
async def batch_generate_keywords(nodes: List[TextNode]) -> List[TextNode]: # Placeholder
    print(f"Placeholder: batch_generate_keywords called for {len(nodes)} nodes")
    return nodes

class KeywordGenerator: # Placeholder
    async def atransform(self, nodes: List[TextNode]) -> List[TextNode]:
        print(f"Placeholder: KeywordGenerator.atransform called for {len(nodes)} nodes")
        return nodes


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
