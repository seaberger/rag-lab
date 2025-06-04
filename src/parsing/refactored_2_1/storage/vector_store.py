from typing import List # Added List

import numpy as np
from llama_index.core import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode # Added TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import QdrantClient # Added QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams # Added Qdrant models

from ..utils.config import PipelineConfig


class EmbeddingManager:
    """Manage document embeddings with explicit configuration."""

    def __init__(
        self,
        config: PipelineConfig = None,
        model: str = None,
        chunk_size: int = None,
        chunk_overlap: int = None,
    ):
        # Use config if provided, otherwise defaults
        self.config = config
        if config:
            model = model or config.openai.embedding_model
            chunk_size = chunk_size or config.chunking.chunk_size
            chunk_overlap = chunk_overlap or config.chunking.chunk_overlap
            self.dimensions = config.openai.dimensions
            self.qdrant_path = config.qdrant.path
            self.collection_name = config.qdrant.collection_name
        else:
            model = model or "text-embedding-3-small"
            chunk_size = chunk_size or 1024
            chunk_overlap = chunk_overlap or 128
            self.dimensions = 1536
            self.qdrant_path = "./qdrant_data"
            self.collection_name = "datasheets"

        # Configure embedding model
        self.embed_model = OpenAIEmbedding(
            model=model,
            embed_batch_size=100,  # Process in batches
            dimensions=self.dimensions if model == "text-embedding-3-small" else None,
        )

        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.chunk_size = chunk_size
        Settings.chunk_overlap = chunk_overlap

        # Initialize Qdrant
        self.qdrant_client = QdrantClient(path=self.qdrant_path)
        self._init_collection()

    def _init_collection(self):
        """Initialize Qdrant collection if not exists."""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if self.collection_name not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.dimensions,
                    distance=Distance.COSINE,
                ),
            )

    async def embed_and_store_nodes(self, nodes: List[TextNode], batch_size: int = 50):
        """Embed nodes and store in Qdrant."""
        # PointStruct moved to top-level imports

        points = []
        for i in range(0, len(nodes), batch_size):
            batch_nodes = nodes[i : i + batch_size]

            # Get embeddings
            texts = [node.text for node in batch_nodes]
            embeddings = await self.embed_model.aget_text_embedding_batch(texts)

            # Create Qdrant points
            for node, embedding in zip(batch_nodes, embeddings):
                # Ensure node.id_ is a valid UUID or string for Qdrant
                point_id = node.id_ if isinstance(node.id_, (str)) and len(node.id_) <= 36 else str(node.id_)
                point = PointStruct(
                    id=point_id, # Use validated/converted point_id
                    vector=embedding,
                    payload={
                        "text": node.text,
                        "doc_id": node.metadata.get("doc_id"),
                        "source": node.metadata.get("source"),
                        "pairs": node.metadata.get("pairs", []),
                        "chunk_index": node.metadata.get("chunk_index"),
                        "total_chunks": node.metadata.get("total_chunks"),
                        "has_keywords": "Context:" in node.text,
                    },
                )
                points.append(point)

        # Upsert to Qdrant
        self.qdrant_client.upsert(collection_name=self.collection_name, points=points)

        return len(points)
