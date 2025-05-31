"""
CLI for searching the indexed documents.
"""

import asyncio
import argparse
from rich.console import Console
from rich.table import Table

# LlamaIndex and Qdrant
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import QdrantClient

# Project-specific
from ..storage.keyword_index import BM25Index
from .hybrid import HybridSearch
# FIXME: Consider using PipelineConfig for paths, model names, collection names, etc.
# from ..utils.config import PipelineConfig


async def search_documents(query: str, mode: str = "hybrid", limit: int = 5):
    """Search indexed documents."""

    # FIXME: Initialize components using PipelineConfig
    # config = PipelineConfig.from_yaml()
    # embedding_model_name = config.openai.embedding_model
    # qdrant_path = config.qdrant.path
    # keyword_index_path = config.storage.keyword_index_path # Assuming you add this to config
    # collection_name = config.qdrant.collection_name
    # hybrid_alpha = config.search.hybrid_alpha # Assuming you add this

    embedding_model_name = "text-embedding-3-small" # Placeholder
    qdrant_path = "./qdrant_data" # Placeholder
    keyword_index_path = "./keyword_index.db" # Placeholder
    collection_name = "datasheets" # Placeholder
    hybrid_alpha = 0.7 # Placeholder


    # Initialize components
    embedding_model = OpenAIEmbedding(model=embedding_model_name)
    qdrant_client = QdrantClient(path=qdrant_path)
    bm25_index = BM25Index(db_path=keyword_index_path)

    if mode == "hybrid":
        searcher = HybridSearch(qdrant_client, bm25_index, alpha=hybrid_alpha)
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
    parser.add_argument(
        "--mode", choices=["hybrid", "vector", "keyword"], default="hybrid"
    )
    parser.add_argument("--limit", type=int, default=5)

    args = parser.parse_args()
    asyncio.run(search_documents(args.query, args.mode, args.limit))
