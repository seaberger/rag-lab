from typing import List # Added List

import numpy as np
from llama_index.core import Settings
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import TextNode # Added TextNode
from llama_index.embeddings.openai import OpenAIEmbedding
from qdrant_client import QdrantClient # Added QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams # Added Qdrant models

# FIXME: Consider using PipelineConfig for model names, dimensions, paths, etc.
# from ..utils.config import PipelineConfig


class EmbeddingManager:
    """Manage document embeddings with explicit configuration."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
    ):
        # Configure embedding model
        # FIXME: model name, dimensions should come from config
        # config = PipelineConfig.from_yaml() # Example: load config
        # model = config.openai.embedding_model
        # dimensions = config.openai.dimensions
        self.embed_model = OpenAIEmbedding(
            model=model, # Use model from params or config
            embed_batch_size=100,  # Process in batches
            dimensions=dimensions if model == "text-embedding-3-small" else None, # Use dimensions from params or config
        )

        # Set global settings
        Settings.embed_model = self.embed_model
        # FIXME: chunk_size and chunk_overlap should come from config.chunking
        Settings.chunk_size = chunk_size # Use chunk_size from params or config
        Settings.chunk_overlap = chunk_overlap # Use chunk_overlap from params or config

        # Initialize Qdrant
        # FIXME: Qdrant path should come from config.qdrant.path
        self.qdrant_client = QdrantClient(path="./qdrant_data") # Use path from config
        self._init_collection()

    def _init_collection(self):
        """Initialize Qdrant collection if not exists."""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        # FIXME: collection_name should come from config.qdrant.collection_name
        # FIXME: vector size (1536) should come from config.openai.dimensions
        collection_name_to_check = "datasheets" # Use collection name from config

        if collection_name_to_check not in collection_names:
            self.qdrant_client.create_collection(
                collection_name=collection_name_to_check,
                vectors_config=VectorParams(
                    size=1536,  # Use dimension from config
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
        # FIXME: collection_name should come from config.qdrant.collection_name
        self.qdrant_client.upsert(collection_name="datasheets", points=points) # Use collection name from config

        return len(points)
