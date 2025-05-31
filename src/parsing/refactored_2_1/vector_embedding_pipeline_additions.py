from llama_index.core import Settings
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.node_parser import SentenceSplitter
import numpy as np


class EmbeddingManager:
    """Manage document embeddings with explicit configuration."""

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        chunk_size: int = 1024,
        chunk_overlap: int = 128,
    ):
        # Configure embedding model
        self.embed_model = OpenAIEmbedding(
            model=model,
            embed_batch_size=100,  # Process in batches
            dimensions=1536 if model == "text-embedding-3-small" else None,
        )

        # Set global settings
        Settings.embed_model = self.embed_model
        Settings.chunk_size = chunk_size
        Settings.chunk_overlap = chunk_overlap

        # Initialize Qdrant
        self.qdrant_client = QdrantClient(path="./qdrant_data")
        self._init_collection()

    def _init_collection(self):
        """Initialize Qdrant collection if not exists."""
        collections = self.qdrant_client.get_collections().collections
        collection_names = [c.name for c in collections]

        if "datasheets" not in collection_names:
            self.qdrant_client.create_collection(
                collection_name="datasheets",
                vectors_config=VectorParams(
                    size=1536,  # OpenAI embedding dimension
                    distance=Distance.COSINE,
                ),
            )

    async def embed_and_store_nodes(self, nodes: List[TextNode], batch_size: int = 50):
        """Embed nodes and store in Qdrant."""
        from qdrant_client.models import PointStruct

        points = []
        for i in range(0, len(nodes), batch_size):
            batch_nodes = nodes[i : i + batch_size]

            # Get embeddings
            texts = [node.text for node in batch_nodes]
            embeddings = await self.embed_model.aget_text_embedding_batch(texts)

            # Create Qdrant points
            for node, embedding in zip(batch_nodes, embeddings):
                point = PointStruct(
                    id=node.id_,
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
        self.qdrant_client.upsert(collection_name="datasheets", points=points)

        return len(points)
