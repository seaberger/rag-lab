"""
Hybrid search combining vector similarity and BM25.
"""

from typing import Dict, List # Tuple was unused

# import numpy as np # numpy seems unused
from llama_index.embeddings.openai import OpenAIEmbedding # For type hinting
from qdrant_client import QdrantClient # For type hinting

from ..storage.keyword_index import BM25Index # For type hinting

# FIXME: Consider using PipelineConfig for collection_name
# from ..utils.config import PipelineConfig


class HybridSearch:
    """Combine vector and keyword search."""

    def __init__(
        self, vector_store: QdrantClient, keyword_index: BM25Index, alpha: float = 0.5
    ):
        """
        Args:
            alpha: Weight for vector search (1-alpha for BM25)
        """
        self.vector_store = vector_store
        self.keyword_index = keyword_index
        self.alpha = alpha

    async def search(
        self, query: str, embedding_model: OpenAIEmbedding, limit: int = 10
    ) -> List[Dict]:
        """Perform hybrid search."""

        # Vector search
        query_embedding = await embedding_model.aget_query_embedding(query)
        # FIXME: collection_name should come from config
        # config = PipelineConfig.from_yaml()
        # collection_name = config.qdrant.collection_name
        collection_name_to_use = "datasheets"

        vector_results = self.vector_store.search(
            collection_name=collection_name_to_use,
            query_vector=query_embedding,
            limit=limit * 2,  # Get more for reranking
        )

        # BM25 search
        keyword_results = self.keyword_index.search(query, limit=limit * 2)

        # Combine scores
        combined_scores = {}

        # Add vector scores (normalized)
        max_vector_score = (
            max([r.score for r in vector_results]) if vector_results else 1.0
        )
        for result in vector_results:
            chunk_id = result.id
            normalized_score = result.score / max_vector_score
            combined_scores[chunk_id] = self.alpha * normalized_score

        # Add BM25 scores (normalized)
        max_bm25_score = (
            max([r["score"] for r in keyword_results]) if keyword_results else 1.0
        )
        for result in keyword_results:
            chunk_id = result["chunk_id"]
            normalized_score = (
                abs(result["score"]) / max_bm25_score
            )  # BM25 scores can be negative

            if chunk_id in combined_scores:
                combined_scores[chunk_id] += (1 - self.alpha) * normalized_score
            else:
                combined_scores[chunk_id] = (1 - self.alpha) * normalized_score

        # Sort by combined score
        sorted_results = sorted(
            combined_scores.items(), key=lambda x: x[1], reverse=True
        )[:limit]

        # Fetch full results
        results = []
        for chunk_id, score in sorted_results:
            # Get from vector store (has all metadata)
            # FIXME: collection_name should come from config
            point = self.vector_store.retrieve(
                collection_name=collection_name_to_use, ids=[chunk_id]
            )[0]

            results.append(
                {
                    "chunk_id": chunk_id,
                    "text": point.payload["text"],
                    "score": score,
                    "doc_id": point.payload["doc_id"],
                    "source": point.payload["source"],
                    "metadata": point.payload,
                }
            )

        return results
