"""
LlamaIndex helpers for PostgreSQL backend support.

This module provides backend-aware node creation and metadata handling
to ensure proper integration with both SQLite and PostgreSQL backends.
"""

from typing import Any, Dict, List, Optional
from llama_index.core.schema import TextNode, Document
from llama_index.core import Settings
from src.pipeline_v3.utils.config import PipelineConfig
from src.pipeline_v3.utils.common_utils import logger


class BackendAwareNodeFactory:
    """Factory for creating LlamaIndex nodes with backend-specific metadata."""

    def __init__(self, config: PipelineConfig):
        """Initialize with pipeline configuration."""
        self.config = config
        self.backend = config.database.backend
        self.is_postgresql = self.backend == "postgresql"

        # Get tenant_id if using PostgreSQL
        self.tenant_id = None
        if self.is_postgresql and hasattr(config.database.postgresql, 'default_tenant_id'):
            self.tenant_id = config.database.postgresql.default_tenant_id

    def create_document(
        self,
        text: str,
        doc_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        excluded_llm_metadata_keys: Optional[List[str]] = None,
        excluded_embed_metadata_keys: Optional[List[str]] = None,
    ) -> Document:
        """
        Create a Document with backend-specific metadata.

        Args:
            text: Document text content
            doc_id: Document identifier
            metadata: Additional metadata
            excluded_llm_metadata_keys: Keys to exclude from LLM metadata
            excluded_embed_metadata_keys: Keys to exclude from embedding metadata

        Returns:
            Document with proper metadata for the backend
        """
        # Prepare metadata
        doc_metadata = metadata or {}
        doc_metadata["doc_id"] = doc_id

        # Add backend-specific metadata
        if self.is_postgresql and self.tenant_id:
            doc_metadata["tenant_id"] = self.tenant_id
            doc_metadata["backend"] = "postgresql"
        else:
            doc_metadata["backend"] = "sqlite"

        # Create document
        doc = Document(
            text=text,
            doc_id=doc_id,
            metadata=doc_metadata,
            excluded_llm_metadata_keys=excluded_llm_metadata_keys or [],
            excluded_embed_metadata_keys=excluded_embed_metadata_keys or [],
        )

        return doc

    def create_nodes_from_document(
        self,
        document: Document,
        text_splitter: Any = None,
    ) -> List[TextNode]:
        """
        Create nodes from a document with backend-specific metadata.

        Args:
            document: Source document
            text_splitter: Optional text splitter (uses Settings default if not provided)

        Returns:
            List of TextNode objects with proper metadata
        """
        # Use provided splitter or default from Settings
        if text_splitter is None:
            text_splitter = Settings.text_splitter

        # Split document into nodes
        nodes = text_splitter.get_nodes_from_documents([document])

        # Enhance each node with backend-specific metadata
        for node in nodes:
            self.enhance_node_metadata(node, document.metadata)

        return nodes

    def create_text_node(
        self,
        text: str,
        node_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        excluded_llm_metadata_keys: Optional[List[str]] = None,
        excluded_embed_metadata_keys: Optional[List[str]] = None,
    ) -> TextNode:
        """
        Create a single TextNode with backend-specific metadata.

        Args:
            text: Node text content
            node_id: Optional node identifier
            metadata: Additional metadata
            excluded_llm_metadata_keys: Keys to exclude from LLM metadata
            excluded_embed_metadata_keys: Keys to exclude from embedding metadata

        Returns:
            TextNode with proper metadata for the backend
        """
        # Prepare metadata
        node_metadata = metadata or {}

        # Add backend-specific metadata
        if self.is_postgresql and self.tenant_id:
            node_metadata["tenant_id"] = self.tenant_id
            node_metadata["backend"] = "postgresql"
        else:
            node_metadata["backend"] = "sqlite"

        # Create node
        node = TextNode(
            text=text,
            id_=node_id,
            metadata=node_metadata,
            excluded_llm_metadata_keys=excluded_llm_metadata_keys or [],
            excluded_embed_metadata_keys=excluded_embed_metadata_keys or [],
        )

        return node

    def enhance_node_metadata(self, node: TextNode, parent_metadata: Optional[Dict[str, Any]] = None):
        """
        Enhance node metadata with backend-specific fields.

        Args:
            node: TextNode to enhance
            parent_metadata: Optional parent document metadata to inherit
        """
        # Ensure node has metadata dict
        if not hasattr(node, 'metadata') or node.metadata is None:
            node.metadata = {}

        # Inherit parent metadata if provided
        if parent_metadata:
            # Copy important fields from parent
            for key in ['doc_id', 'source', 'tenant_id', 'backend']:
                if key in parent_metadata and key not in node.metadata:
                    node.metadata[key] = parent_metadata[key]

        # Add backend-specific metadata
        if self.is_postgresql and self.tenant_id:
            if 'tenant_id' not in node.metadata:
                node.metadata['tenant_id'] = self.tenant_id
            node.metadata['backend'] = 'postgresql'
        else:
            node.metadata['backend'] = 'sqlite'

        # Ensure doc_id is present
        if 'doc_id' not in node.metadata:
            logger.warning(f"Node {node.node_id} missing doc_id in metadata")

    def prepare_nodes_for_indexing(
        self,
        nodes: List[TextNode],
        doc_id: str,
        source: Optional[str] = None,
    ) -> List[TextNode]:
        """
        Prepare nodes for indexing by ensuring all required metadata is present.

        Args:
            nodes: List of nodes to prepare
            doc_id: Document identifier
            source: Optional document source

        Returns:
            List of nodes ready for indexing
        """
        for i, node in enumerate(nodes):
            # Ensure metadata exists
            if not hasattr(node, 'metadata') or node.metadata is None:
                node.metadata = {}

            # Set required fields
            node.metadata['doc_id'] = doc_id
            if source:
                node.metadata['source'] = source

            # Add chunk index if not present
            if 'chunk_index' not in node.metadata:
                node.metadata['chunk_index'] = i

            # Add content hash
            if hasattr(node, 'hash'):
                node.metadata['content_hash'] = node.hash

            # Enhance with backend-specific metadata
            self.enhance_node_metadata(node)

        return nodes

    def extract_metadata_for_query(
        self,
        node: TextNode,
        include_backend_fields: bool = True
    ) -> Dict[str, Any]:
        """
        Extract metadata from node for query results.

        Args:
            node: TextNode to extract metadata from
            include_backend_fields: Whether to include backend-specific fields

        Returns:
            Dictionary of metadata suitable for query results
        """
        metadata = node.metadata.copy() if node.metadata else {}

        # Remove internal fields unless requested
        if not include_backend_fields:
            internal_fields = ['tenant_id', 'backend', 'content_hash']
            for field in internal_fields:
                metadata.pop(field, None)

        return metadata


def create_backend_aware_nodes(
    config: PipelineConfig,
    content: str,
    doc_id: str,
    metadata: Optional[Dict[str, Any]] = None,
    text_splitter: Any = None,
) -> List[TextNode]:
    """
    Convenience function to create backend-aware nodes from content.

    Args:
        config: Pipeline configuration
        content: Document content
        doc_id: Document identifier
        metadata: Optional metadata
        text_splitter: Optional text splitter

    Returns:
        List of TextNode objects ready for indexing
    """
    factory = BackendAwareNodeFactory(config)

    # Create document
    doc = factory.create_document(content, doc_id, metadata)

    # Create nodes
    nodes = factory.create_nodes_from_document(doc, text_splitter)

    # Prepare for indexing
    nodes = factory.prepare_nodes_for_indexing(nodes, doc_id)

    return nodes
