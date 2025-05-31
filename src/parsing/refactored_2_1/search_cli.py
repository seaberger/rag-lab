"""
CLI for searching the indexed documents.
"""

import asyncio
import argparse
from rich.console import Console
from rich.table import Table


async def search_documents(query: str, mode: str = "hybrid", limit: int = 5):
    """Search indexed documents."""

    # Initialize components
    embedding_model = OpenAIEmbedding(model="text-embedding-3-small")
    qdrant_client = QdrantClient(path="./qdrant_data")
    bm25_index = BM25Index(db_path="./keyword_index.db")

    if mode == "hybrid":
        searcher = HybridSearch(qdrant_client, bm25_index, alpha=0.7)
        results = await searcher.search(query, embedding_model, limit)
    elif mode == "vector":
        query_embedding = await embedding_model.aget_query_embedding(query)
        results = qdrant_client.search(
            collection_name="datasheets", query_vector=query_embedding, limit=limit
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
