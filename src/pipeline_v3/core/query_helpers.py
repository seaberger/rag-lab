"""
Query helpers for PostgreSQL backend support.

This module provides backend-aware query handling and result processing
to ensure proper integration with both SQLite and PostgreSQL backends.
"""

from typing import Any, Dict, List, Union

from llama_index.core.schema import NodeWithScore
from llama_index.core.vector_stores import VectorStoreQuery

from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class BackendAwareQueryProcessor:
    """Processor for handling queries with backend-specific considerations."""

    def __init__(self, config: PipelineConfig):
        """Initialize with pipeline configuration."""
        self.config = config
        self.backend = config.database.backend
        self.is_postgresql = self.backend == "postgresql"

        # Get tenant_id if using PostgreSQL
        self.tenant_id = None
        if self.is_postgresql and hasattr(config.database.postgresql, "default_tenant_id"):
            self.tenant_id = config.database.postgresql.default_tenant_id

    def prepare_vector_query(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Dict[str, Any] | None = None,
    ) -> VectorStoreQuery:
        """
        Prepare a vector query with backend-specific filters.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            filters: Optional filters to apply

        Returns:
            VectorStoreQuery configured for the backend
        """
        # Start with basic query
        vector_query = VectorStoreQuery(
            query_embedding=query_embedding,
            similarity_top_k=top_k,
        )

        # Add backend-specific filters
        if filters:
            # processed_filters = self.process_filters(filters)  # TODO: Implement when needed
            # TODO: Implement MetadataFilters when LlamaIndex supports it properly
            # For now, we'll rely on post-filtering
            pass

        return vector_query

    def process_filters(self, filters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process filters for backend-specific requirements.

        Args:
            filters: Raw filters from user

        Returns:
            Processed filters suitable for the backend
        """
        processed = filters.copy()

        # Add tenant filter for PostgreSQL if not present
        if self.is_postgresql and self.tenant_id:
            if "tenant_id" not in processed:
                processed["tenant_id"] = self.tenant_id

        return processed

    def process_vector_results(
        self,
        results: Union[List[NodeWithScore], Any],
        filters: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Process vector search results with backend awareness.

        Args:
            results: Raw results from vector store
            filters: Optional filters for post-processing

        Returns:
            List of processed result dictionaries
        """
        processed_results = []

        # Handle different result structures
        if hasattr(results, "nodes"):
            result_nodes = results.nodes
        elif isinstance(results, list):
            result_nodes = results
        else:
            logger.error(f"Unexpected vector search result type: {type(results)}")
            return []

        for result in result_nodes:
            # Extract metadata
            metadata = self.extract_metadata(result)

            # Skip if tenant filtering needed and doesn't match
            if self.is_postgresql and self.tenant_id:
                result_tenant = metadata.get("tenant_id")
                if result_tenant and result_tenant != self.tenant_id:
                    continue

            # Apply additional filters
            if filters and not self.matches_filters(metadata, filters):
                continue

            # Build result dictionary
            result_dict = self.build_result_dict(result, metadata)
            processed_results.append(result_dict)

        return processed_results

    def extract_metadata(self, node: Any) -> Dict[str, Any]:
        """
        Extract metadata from a node result.

        Args:
            node: Node result from vector store

        Returns:
            Dictionary of metadata
        """
        # Try different ways to get metadata
        metadata = {}

        # Direct metadata attribute
        if hasattr(node, "metadata"):
            metadata = node.metadata or {}

        # Payload (Qdrant server mode)
        elif hasattr(node, "payload"):
            payload = node.payload
            if "_node_content" in payload and isinstance(payload["_node_content"], str):
                try:
                    import json

                    node_content = json.loads(payload["_node_content"])
                    metadata = node_content.get("metadata", {})
                except Exception as e:
                    logger.debug(f"Failed to parse _node_content: {e}")
            else:
                metadata = payload

        return metadata

    def matches_filters(self, metadata: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        """
        Check if metadata matches the given filters.

        Args:
            metadata: Node metadata
            filters: Filters to apply

        Returns:
            True if metadata matches all filters
        """
        for key, value in filters.items():
            # Handle special filter keys
            if key == "doc_ids":
                doc_id = metadata.get("doc_id")
                if doc_id not in value:
                    return False
            elif key == "tenant_id" and self.is_postgresql:
                if metadata.get("tenant_id") != value:
                    return False
            # Direct comparison
            elif metadata.get(key) != value:
                return False

        return True

    def build_result_dict(self, node: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a standardized result dictionary from a node.

        Args:
            node: Node result
            metadata: Extracted metadata

        Returns:
            Standardized result dictionary
        """
        # Extract text content
        text = ""
        if hasattr(node, "text"):
            text = node.text
        elif hasattr(node, "content"):
            text = node.content
        elif hasattr(node, "get_content"):
            text = node.get_content()

        # Extract node ID
        node_id = "unknown"
        if hasattr(node, "node_id"):
            node_id = node.node_id
        elif hasattr(node, "id_"):
            node_id = node.id_
        elif hasattr(node, "id"):
            node_id = node.id

        # Extract score
        score = 0.0
        if hasattr(node, "score"):
            score = node.score
        elif hasattr(node, "similarity"):
            score = node.similarity

        # Extract doc_id
        doc_id = metadata.get("doc_id", "unknown")
        if doc_id == "unknown" and hasattr(node, "doc_id"):
            doc_id = node.doc_id

        return {
            "node_id": node_id,
            "score": score,
            "text": text,
            "content": text,  # Compatibility
            "metadata": metadata,
            "doc_id": doc_id,
            "backend": self.backend,
        }

    def prepare_keyword_query(
        self,
        query: str,
        filters: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """
        Prepare a keyword query with backend-specific processing.

        Args:
            query: Search query string
            filters: Optional filters

        Returns:
            Processed query parameters
        """
        # Process filters
        processed_filters = self.process_filters(filters) if filters else {}

        # Build query parameters
        params = {
            "query": query,
            "filters": processed_filters,
        }

        # Add backend-specific parameters
        if self.is_postgresql:
            # PostgreSQL-specific query hints
            params["search_config"] = "english"  # Or from config
            if self.tenant_id:
                params["tenant_id"] = self.tenant_id

        return params

    def process_keyword_results(
        self,
        results: List[Dict[str, Any]],
        normalize_scores: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Process keyword search results with backend awareness.

        Args:
            results: Raw keyword search results
            normalize_scores: Whether to normalize scores

        Returns:
            List of processed result dictionaries
        """
        if not results:
            return []

        processed = []

        # Find max score for normalization
        max_score = 1.0
        if normalize_scores and results:
            scores = [r.get("score", 0) for r in results if r.get("score")]
            if scores:
                max_score = max(scores)

        for result in results:
            # Copy result
            processed_result = result.copy()

            # Normalize score if needed
            if normalize_scores and max_score > 0:
                current_score = processed_result.get("score", 0)
                processed_result["score"] = current_score / max_score

            # Add backend info
            processed_result["backend"] = self.backend

            # Ensure consistent structure
            if "content" not in processed_result and "text" in processed_result:
                processed_result["content"] = processed_result["text"]
            elif "text" not in processed_result and "content" in processed_result:
                processed_result["text"] = processed_result["content"]

            processed.append(processed_result)

        return processed


def create_backend_aware_query(
    config: PipelineConfig,
    query_embedding: List[float],
    top_k: int = 10,
    filters: Dict[str, Any] | None = None,
) -> VectorStoreQuery:
    """
    Convenience function to create a backend-aware vector query.

    Args:
        config: Pipeline configuration
        query_embedding: Query embedding vector
        top_k: Number of results
        filters: Optional filters

    Returns:
        VectorStoreQuery configured for the backend
    """
    processor = BackendAwareQueryProcessor(config)
    return processor.prepare_vector_query(query_embedding, top_k, filters)
