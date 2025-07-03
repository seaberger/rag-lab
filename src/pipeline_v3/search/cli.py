"""
CLI for searching the indexed documents.
"""

import argparse
import asyncio

# LlamaIndex and Qdrant
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import QdrantClient
from rich.console import Console
from rich.table import Table
from search.hybrid import HybridSearch

# Project-specific
from storage.keyword_index import BM25Index

from utils.config import PipelineConfig


async def search_documents(query: str, mode: str = None, limit: int = None):
    """Search indexed documents."""

    # Initialize configuration
    config = PipelineConfig.from_yaml()

    # Use config values with fallbacks for mode and limit
    if mode is None:
        mode = config.search.default_mode
    if limit is None:
        limit = config.search.default_limit

    # Get values from config
    embedding_model_name = config.openai.embedding_model
    qdrant_path = config.qdrant.path
    keyword_index_path = config.storage.keyword_db_path
    collection_name = config.qdrant.collection_name
    hybrid_alpha = config.search.hybrid_alpha

    # Initialize components
    embedding_model = OpenAIEmbedding(model=embedding_model_name)
    qdrant_client = QdrantClient(path=qdrant_path)
    bm25_index = BM25Index(db_path=keyword_index_path)

    if mode == "hybrid":
        searcher = HybridSearch(
            qdrant_client, bm25_index, alpha=hybrid_alpha, collection_name=collection_name
        )
        results = await searcher.search(query, embedding_model, limit)
    elif mode == "vector":
        query_embedding = await embedding_model.aget_query_embedding(query)
        results = qdrant_client.search(
            collection_name=collection_name, query_vector=query_embedding, limit=limit
        )
    elif mode == "keyword":
        results = bm25_index.search(query, limit)

    # Display results
    console = Console()
    table = Table(title=f"Search Results for: {query}")
    table.add_column("Score", style="cyan")
    table.add_column("Document", style="green")
    table.add_column("Text Preview", style="white")

    for result in results:
        score = f"{result.get('score', 0):.3f}"
        doc_id = result.get("doc_id", "Unknown")[:8]
        text_preview = result.get("text", "")[:100] + "..."
        table.add_row(score, doc_id, text_preview)

    console.print(table)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Search query")
    parser.add_argument("--mode", choices=["hybrid", "vector", "keyword"], default="hybrid")
    parser.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()
    asyncio.run(search_documents(args.query, args.mode, args.limit))
