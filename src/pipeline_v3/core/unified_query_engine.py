"""
Unified Query Engine for RAG Lab.

A modern, backend-aware query engine that replaces LlamaIndex dependencies
with direct integrations for vector search (Qdrant), keyword search (PostgreSQL/SQLite),
and advanced hybrid fusion algorithms.
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List

from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


@dataclass
class QueryRequest:
    """Unified query request structure."""

    query: str
    top_k: int = 10
    search_type: str = "hybrid"  # "vector", "keyword", "hybrid"
    filters: Dict[str, Any] | None = None
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    fusion_method: str = "rrf"  # "rrf", "weighted", "adaptive"
    include_metadata: bool = True
    tenant_id: str | None = None


@dataclass
class QueryResult:
    """Unified query result structure."""

    doc_id: str
    chunk_id: str
    score: float
    text: str
    metadata: Dict[str, Any]
    source: str
    search_type: str  # Which search contributed this result
    backend: str


class UnifiedQueryEngine:
    """
    A unified query engine that handles vector, keyword, and hybrid search
    across SQLite and PostgreSQL backends without LlamaIndex dependencies.
    """

    def __init__(
        self,
        config: PipelineConfig,
        registry: DocumentRegistry | None = None,
        keyword_index: Any | None = None,
        qdrant_client: QdrantClient | None = None,
        embedding_service: Any | None = None,
    ):
        """
        Initialize the unified query engine.

        Args:
            config: Pipeline configuration
            registry: Document registry for metadata lookups
            keyword_index: Keyword search index (PostgreSQL or SQLite)
            qdrant_client: Direct Qdrant client
            embedding_service: Service for generating embeddings
        """
        self.config = config
        self.backend = config.database.backend
        self.is_postgresql = self.backend == "postgresql"

        # Components
        self.registry = registry or DocumentRegistry(config)
        self.keyword_index = keyword_index
        self.qdrant_client = qdrant_client
        self.embedding_service = embedding_service

        # Tenant configuration for PostgreSQL
        self.tenant_id = None
        if self.is_postgresql and hasattr(config.database.postgresql, "default_tenant_id"):
            self.tenant_id = config.database.postgresql.default_tenant_id

        # Cache for document sources
        self._doc_source_cache = {}

        logger.info(f"UnifiedQueryEngine initialized for {self.backend} backend")

    async def search(self, request: QueryRequest) -> List[QueryResult]:
        """
        Execute a search based on the request parameters.

        Args:
            request: Query request with search parameters

        Returns:
            List of query results
        """
        # Override tenant_id if specified in request
        tenant_id = request.tenant_id or self.tenant_id

        # Add tenant filter for PostgreSQL
        if self.is_postgresql and tenant_id:
            if not request.filters:
                request.filters = {}
            request.filters["tenant_id"] = tenant_id

        # Route to appropriate search method
        if request.search_type == "vector":
            return await self._vector_search(request)
        elif request.search_type == "keyword":
            return await self._keyword_search(request)
        elif request.search_type == "hybrid":
            return await self._hybrid_search(request)
        else:
            raise ValueError(f"Unknown search type: {request.search_type}")

    async def _vector_search(self, request: QueryRequest) -> List[QueryResult]:
        """Execute vector similarity search using Qdrant directly."""
        if not self.qdrant_client or not self.embedding_service:
            logger.error("Vector search not available - missing Qdrant client or embedding service")
            return []

        try:
            # Generate query embedding
            query_embedding = await self._get_embedding(request.query)

            # Build Qdrant filters
            qdrant_filter = self._build_qdrant_filter(request.filters)

            # Search Qdrant directly
            search_result = self.qdrant_client.search(
                collection_name=self.config.qdrant.collection_name,
                query_vector=query_embedding,
                limit=request.top_k,
                query_filter=qdrant_filter,
                with_payload=True,
                with_vectors=False,
            )

            # Convert to unified results
            results = []
            for point in search_result:
                result = self._convert_qdrant_result(point, "vector")
                if result:
                    results.append(result)

            return results

        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return []

    async def _keyword_search(self, request: QueryRequest) -> List[QueryResult]:
        """Execute keyword search using PostgreSQL or SQLite."""
        if not self.keyword_index:
            logger.error("Keyword search not available - no keyword index")
            return []

        try:
            # Search keyword index
            keyword_results = self.keyword_index.search(
                query=request.query, limit=request.top_k, filters=request.filters
            )

            # Convert to unified results
            results = []
            for kr in keyword_results:
                result = self._convert_keyword_result(kr, "keyword")
                if result:
                    results.append(result)

            return results

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return []

    async def _hybrid_search(self, request: QueryRequest) -> List[QueryResult]:
        """Execute hybrid search with fusion."""
        # Get more results for better fusion
        search_multiplier = max(3, request.top_k // 5)
        temp_request = QueryRequest(
            query=request.query,
            top_k=request.top_k * search_multiplier,
            filters=request.filters,
            tenant_id=request.tenant_id,
        )

        # Execute both searches in parallel
        vector_task = asyncio.create_task(self._vector_search(temp_request))
        keyword_task = asyncio.create_task(self._keyword_search(temp_request))

        vector_results, keyword_results = await asyncio.gather(vector_task, keyword_task)

        # Apply fusion algorithm
        if request.fusion_method == "rrf":
            return self._reciprocal_rank_fusion(
                vector_results, keyword_results, request.top_k, request.query
            )
        elif request.fusion_method == "adaptive":
            return self._adaptive_fusion(
                vector_results, keyword_results, request.top_k, request.query
            )
        else:  # weighted
            return self._weighted_fusion(
                vector_results,
                keyword_results,
                request.top_k,
                request.vector_weight,
                request.keyword_weight,
            )

    def _reciprocal_rank_fusion(
        self,
        vector_results: List[QueryResult],
        keyword_results: List[QueryResult],
        top_k: int,
        query: str,
        k: int = 60,
    ) -> List[QueryResult]:
        """
        Reciprocal Rank Fusion - robust hybrid search fusion.
        """
        combined_scores = {}

        # Process vector results
        for rank, result in enumerate(vector_results, 1):
            key = f"{result.doc_id}:{result.chunk_id}"
            rrf_score = 1.0 / (k + rank)
            combined_scores[key] = {
                "result": result,
                "vector_rank": rank,
                "vector_rrf": rrf_score,
                "keyword_rank": None,
                "keyword_rrf": 0.0,
                "total_rrf": rrf_score,
            }

        # Process keyword results
        for rank, result in enumerate(keyword_results, 1):
            key = f"{result.doc_id}:{result.chunk_id}"
            rrf_score = 1.0 / (k + rank)

            if key in combined_scores:
                combined_scores[key]["keyword_rank"] = rank
                combined_scores[key]["keyword_rrf"] = rrf_score
                combined_scores[key]["total_rrf"] += rrf_score
            else:
                combined_scores[key] = {
                    "result": result,
                    "vector_rank": None,
                    "vector_rrf": 0.0,
                    "keyword_rank": rank,
                    "keyword_rrf": rrf_score,
                    "total_rrf": rrf_score,
                }

        # Sort by combined RRF score
        sorted_results = sorted(
            combined_scores.values(), key=lambda x: x["total_rrf"], reverse=True
        )

        # Return top k with updated scores
        final_results = []
        for item in sorted_results[:top_k]:
            result = item["result"]
            result.score = item["total_rrf"]
            result.metadata["fusion_debug"] = {
                "vector_rank": item["vector_rank"],
                "keyword_rank": item["keyword_rank"],
                "fusion_method": "rrf",
            }
            final_results.append(result)

        return final_results

    def _weighted_fusion(
        self,
        vector_results: List[QueryResult],
        keyword_results: List[QueryResult],
        top_k: int,
        vector_weight: float,
        keyword_weight: float,
    ) -> List[QueryResult]:
        """
        Simple weighted score fusion.
        """
        combined_scores = {}

        # Normalize and combine vector scores
        if vector_results:
            max_vector = max(r.score for r in vector_results)
            for result in vector_results:
                key = f"{result.doc_id}:{result.chunk_id}"
                normalized_score = result.score / max_vector if max_vector > 0 else 0
                combined_scores[key] = {
                    "result": result,
                    "score": normalized_score * vector_weight,
                    "vector_score": normalized_score,
                    "keyword_score": 0.0,
                }

        # Normalize and combine keyword scores
        if keyword_results:
            max_keyword = max(r.score for r in keyword_results)
            for result in keyword_results:
                key = f"{result.doc_id}:{result.chunk_id}"
                normalized_score = result.score / max_keyword if max_keyword > 0 else 0

                if key in combined_scores:
                    combined_scores[key]["score"] += normalized_score * keyword_weight
                    combined_scores[key]["keyword_score"] = normalized_score
                else:
                    combined_scores[key] = {
                        "result": result,
                        "score": normalized_score * keyword_weight,
                        "vector_score": 0.0,
                        "keyword_score": normalized_score,
                    }

        # Sort and return top k
        sorted_results = sorted(combined_scores.values(), key=lambda x: x["score"], reverse=True)

        final_results = []
        for item in sorted_results[:top_k]:
            result = item["result"]
            result.score = item["score"]
            result.metadata["fusion_debug"] = {
                "vector_score": item["vector_score"],
                "keyword_score": item["keyword_score"],
                "fusion_method": "weighted",
            }
            final_results.append(result)

        return final_results

    def _adaptive_fusion(
        self,
        vector_results: List[QueryResult],
        keyword_results: List[QueryResult],
        top_k: int,
        query: str,
    ) -> List[QueryResult]:
        """
        Adaptive fusion that adjusts weights based on query characteristics.
        """
        # Analyze query to determine optimal weights
        query_length = len(query.split())
        has_technical_terms = any(
            term in query.lower()
            for term in ["model", "part", "specification", "datasheet", "sensor", "laser"]
        )

        # Adjust weights based on query analysis
        if query_length <= 2 and has_technical_terms:
            # Short technical queries favor keyword search
            vector_weight = 0.3
            keyword_weight = 0.7
        elif query_length > 5:
            # Longer queries favor semantic search
            vector_weight = 0.8
            keyword_weight = 0.2
        else:
            # Balanced approach
            vector_weight = 0.6
            keyword_weight = 0.4

        # Use weighted fusion with adaptive weights
        results = self._weighted_fusion(
            vector_results, keyword_results, top_k, vector_weight, keyword_weight
        )

        # Add adaptive weights to metadata
        for result in results:
            result.metadata["fusion_debug"]["adaptive_weights"] = {
                "vector": vector_weight,
                "keyword": keyword_weight,
                "query_length": query_length,
                "has_technical": has_technical_terms,
            }

        return results

    async def _get_embedding(self, text: str) -> List[float]:
        """Generate embedding for text."""
        if self.embedding_service:
            return self.embedding_service.get_text_embedding(text)
        else:
            # Fallback to direct OpenAI call
            import openai

            response = await openai.embeddings.create(
                model=self.config.openai.embedding_model, input=text
            )
            return response.data[0].embedding

    def _build_qdrant_filter(self, filters: Dict[str, Any] | None) -> Filter | None:
        """Build Qdrant filter from unified filters."""
        if not filters:
            return None

        conditions = []

        for key, value in filters.items():
            if key == "doc_ids" and isinstance(value, list):
                # Handle multiple doc IDs
                conditions.append(FieldCondition(key="doc_id", match=MatchValue(any=value)))
            elif key == "tenant_id" and self.is_postgresql:
                # Tenant filter for PostgreSQL
                conditions.append(
                    FieldCondition(key="metadata.tenant_id", match=MatchValue(value=value))
                )
            else:
                # Generic field match
                conditions.append(
                    FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
                )

        return Filter(must=conditions) if conditions else None

    def _convert_qdrant_result(self, point: Any, search_type: str) -> QueryResult | None:
        """Convert Qdrant point to unified result."""
        try:
            payload = point.payload

            # Extract metadata
            metadata = {}
            if "_node_content" in payload and isinstance(payload["_node_content"], str):
                # Server mode with serialized content
                import json

                node_content = json.loads(payload["_node_content"])
                metadata = node_content.get("metadata", {})
                text = node_content.get("text", "")
            else:
                # Direct payload
                metadata = payload.get("metadata", {})
                text = payload.get("text", "")

            # Get doc_id
            doc_id = metadata.get("doc_id") or payload.get("doc_id", "unknown")

            return QueryResult(
                doc_id=doc_id,
                chunk_id=str(point.id),
                score=point.score,
                text=text,
                metadata=metadata,
                source=self._get_document_source(doc_id),
                search_type=search_type,
                backend=self.backend,
            )

        except Exception as e:
            logger.error(f"Failed to convert Qdrant result: {e}")
            return None

    def _convert_keyword_result(
        self, result: Dict[str, Any], search_type: str
    ) -> QueryResult | None:
        """Convert keyword search result to unified result."""
        try:
            return QueryResult(
                doc_id=result.get("doc_id", "unknown"),
                chunk_id=result.get("chunk_id", result.get("node_id", "unknown")),
                score=result.get("score", 0.0),
                text=result.get("text", result.get("content", "")),
                metadata=result.get("metadata", {}),
                source=self._get_document_source(result.get("doc_id", "unknown")),
                search_type=search_type,
                backend=self.backend,
            )
        except Exception as e:
            logger.error(f"Failed to convert keyword result: {e}")
            return None

    def _get_document_source(self, doc_id: str) -> str:
        """Get document source with caching."""
        if doc_id in self._doc_source_cache:
            return self._doc_source_cache[doc_id]

        try:
            doc = self.registry.get_document(doc_id)
            if doc:
                source = doc.source.split("/")[-1] if "/" in doc.source else doc.source
                self._doc_source_cache[doc_id] = source
                return source
        except Exception:
            pass

        return "unknown"


# Convenience functions for migration
async def create_query_engine(
    config: PipelineConfig,
    registry: DocumentRegistry | None = None,
    keyword_index: Any | None = None,
    qdrant_client: QdrantClient | None = None,
    embedding_service: Any | None = None,
) -> UnifiedQueryEngine:
    """Create a unified query engine with automatic configuration."""

    # Initialize Qdrant client if not provided
    if not qdrant_client and config.qdrant.use_server:
        qdrant_client = QdrantClient(
            host=config.qdrant.host,
            port=config.qdrant.port,
        )
    elif not qdrant_client:
        qdrant_client = QdrantClient(path=config.qdrant.path)

    return UnifiedQueryEngine(
        config=config,
        registry=registry,
        keyword_index=keyword_index,
        qdrant_client=qdrant_client,
        embedding_service=embedding_service,
    )
