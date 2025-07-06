"""
Direct embedding service to replace LlamaIndex OpenAIEmbedding.

Provides a simple, direct interface to OpenAI's embedding API
without the overhead of LlamaIndex abstractions.
"""

import os
from typing import List

import numpy as np
import openai
from openai import AsyncOpenAI

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class EmbeddingService:
    """
    Direct OpenAI embedding service.
    Replaces llama_index.embeddings.openai.OpenAIEmbedding.
    """

    def __init__(self, config: PipelineConfig | None = None):
        """Initialize the embedding service."""
        self.config = config or PipelineConfig()
        self.model = self.config.openai.embedding_model
        self.dimensions = self.config.openai.dimensions

        # Initialize OpenAI client
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.client = openai.OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)

        logger.info(f"EmbeddingService initialized with model: {self.model}")

    def get_text_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions if self.dimensions else None,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            raise

    async def aget_text_embedding(self, text: str) -> List[float]:
        """
        Get embedding for a single text asynchronously.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        try:
            response = await self.async_client.embeddings.create(
                model=self.model,
                input=text,
                dimensions=self.dimensions if self.dimensions else None,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Failed to get embedding: {e}")
            raise

    def get_text_embedding_batch(
        self, texts: List[str], show_progress: bool = True
    ) -> List[List[float]]:
        """
        Get embeddings for multiple texts in batch.

        Args:
            texts: List of texts to embed
            show_progress: Whether to show progress

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        try:
            # OpenAI has a limit of 2048 texts per batch
            batch_size = 2048
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                if show_progress:
                    logger.info(
                        f"Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}"
                    )

                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions if self.dimensions else None,
                )

                embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(embeddings)

            return all_embeddings

        except Exception as e:
            logger.error(f"Failed to get batch embeddings: {e}")
            raise

    async def aget_text_embedding_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts in batch asynchronously.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        try:
            # OpenAI has a limit of 2048 texts per batch
            batch_size = 2048
            all_embeddings = []

            for i in range(0, len(texts), batch_size):
                batch = texts[i : i + batch_size]

                response = await self.async_client.embeddings.create(
                    model=self.model,
                    input=batch,
                    dimensions=self.dimensions if self.dimensions else None,
                )

                embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(embeddings)

            return all_embeddings

        except Exception as e:
            logger.error(f"Failed to get batch embeddings: {e}")
            raise

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """
        Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score
        """
        # Convert to numpy arrays
        vec1 = np.array(embedding1)
        vec2 = np.array(embedding2)

        # Calculate cosine similarity
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return dot_product / (norm1 * norm2)


# Convenience function
def create_embedding_service(config: PipelineConfig | None = None) -> EmbeddingService:
    """Create an embedding service with the given configuration."""
    return EmbeddingService(config)
