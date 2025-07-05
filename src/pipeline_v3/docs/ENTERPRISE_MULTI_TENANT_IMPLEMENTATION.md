# Enterprise Multi-Tenant Implementation Guide

**Created:** January 5, 2025
**Status:** Planning Phase
**Related Issues:** #77-#85
**Previous Doc:** [MULTI_TENANT_ARCHITECTURE.md](./MULTI_TENANT_ARCHITECTURE.md) (basic filesystem approach)

## Executive Summary

This document extends the basic multi-tenant architecture with enterprise-grade features including PostgreSQL migration, API authentication, MCP servers for agentic workflows, tenant-specific search optimization, and advanced multi-vector search capabilities. This represents the full vision for transforming RAG Lab into a true multi-tenant enterprise platform.

## Table of Contents

1. [Current Architecture Limitations](#current-architecture-limitations)
2. [PostgreSQL Migration Strategy](#postgresql-migration-strategy)
3. [Enterprise Collections Architecture](#enterprise-collections-architecture)
4. [Security & Authentication](#security--authentication)
5. [MCP Server Per Tenant](#mcp-server-per-tenant)
6. [Tenant-Specific Search Pipelines](#tenant-specific-search-pipelines)
7. [Agentic Workflows](#agentic-workflows)
8. [Multi-Vector Search](#multi-vector-search)
9. [Storage Architecture](#storage-architecture)
10. [Implementation Roadmap](#implementation-roadmap)

## Current Architecture Limitations

The existing architecture (described in [MULTI_TENANT_ARCHITECTURE.md](./MULTI_TENANT_ARCHITECTURE.md)) uses filesystem isolation with SQLite databases. This approach has critical limitations for enterprise deployment:

### Database Bottlenecks
- **SQLite Lock Contention**: Only one writer at a time
- **No Concurrent Access**: Multiple tenants can't search simultaneously
- **No Native JSON**: Complex metadata filtering requires text parsing
- **Limited Scalability**: Can't scale horizontally

### Missing Enterprise Features
- **No Authentication**: Anyone can access any collection
- **No Row-Level Security**: Can't restrict document access within collections
- **Basic Search Only**: No per-tenant optimization
- **No Audit Trail**: No compliance support

## PostgreSQL Migration Strategy

### Why PostgreSQL?

| Feature | SQLite | PostgreSQL | Benefit |
|---------|--------|------------|---------|
| **Concurrent Access** | ❌ Single writer | ✅ MVCC | Multiple tenants simultaneously |
| **JSON Support** | ❌ Text only | ✅ Native JSONB | Complex metadata filtering |
| **Full-Text Search** | Basic FTS5 | Advanced with weights | Better relevance |
| **Security** | File permissions | Row-level security | Fine-grained access |
| **Scalability** | Vertical only | Horizontal | Cloud-ready |

### Migration Architecture

```sql
-- Schema design supporting both patterns
-- Pattern 1: Schema per tenant (< 100 tenants)
CREATE SCHEMA tenant_acme;
CREATE SCHEMA tenant_globex;

-- Pattern 2: Shared tables with RLS (> 100 tenants)
CREATE TABLE public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    collection_id UUID NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB NOT NULL,
    security JSONB,
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', title), 'A') ||
        setweight(to_tsvector('english', content), 'B')
    ) STORED,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE public.documents ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON public.documents
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Indexes for performance
CREATE INDEX idx_search ON documents USING GIN(search_vector);
CREATE INDEX idx_metadata ON documents USING GIN(metadata);
CREATE INDEX idx_tenant_collection ON documents(tenant_id, collection_id);
```

### Advanced Search Features

```sql
-- PostgreSQL enables sophisticated search
-- 1. Fuzzy search with trigrams
CREATE EXTENSION pg_trgm;

SELECT * FROM documents
WHERE title % 'lazer sensor'  -- Typo tolerant
  AND similarity(title, 'lazer sensor') > 0.3;

-- 2. Complex metadata filtering
SELECT * FROM documents
WHERE tenant_id = $1
  AND metadata @> '{"product_type": "sensor"}'
  AND (metadata->>'power_range_max')::float > 5.0
  AND metadata->'certifications' ? 'ISO-17025';

-- 3. Phrase search with proximity
SELECT * FROM documents
WHERE search_vector @@ phraseto_tsquery('english', 'laser power meter');
```

## Enterprise Collections Architecture

### Collection Management System

```python
@dataclass
class EnterpriseCollectionConfig:
    """Enterprise collection configuration"""
    tenant_id: str
    collection_id: str
    name: str
    description: Optional[str]

    # Security
    api_keys: List[str]
    access_level: Literal["public", "internal", "restricted"]
    allowed_ips: List[str]

    # Search configuration
    search_pipelines: Dict[str, SearchPipelineConfig]
    default_pipeline: str

    # MCP configuration
    mcp_server_config: MCPServerConfig

    # Storage
    storage_quota_gb: int
    document_quota: int

    # Features
    enabled_features: List[str]  # ["colbert", "splade", "reranking"]

class EnterpriseCollectionManager:
    """Manages collections with full enterprise features"""

    def __init__(self, pg_client: PostgreSQLClient,
                 qdrant_client: QdrantClient,
                 redis_client: Redis):
        self.pg = pg_client
        self.qdrant = qdrant_client
        self.redis = redis_client

    async def create_collection(self, config: EnterpriseCollectionConfig):
        """Create collection with full isolation"""

        # 1. PostgreSQL setup
        if config.tenant_id not in self.existing_schemas:
            await self.pg.execute(f"""
                CREATE SCHEMA tenant_{config.tenant_id};
                GRANT USAGE ON SCHEMA tenant_{config.tenant_id}
                TO tenant_{config.tenant_id}_role;
            """)

        # 2. Create collection tables
        await self._create_collection_tables(config)

        # 3. Qdrant collections (multiple vectors)
        await self._create_qdrant_collections(config)

        # 4. Initialize search pipelines
        await self._initialize_search_pipelines(config)

        # 5. Start MCP server
        await self._start_mcp_server(config)

        # 6. Set up monitoring
        await self._initialize_monitoring(config)
```

## Security & Authentication

### API Key Management System

```python
@dataclass
class APIKeyConfig:
    """Comprehensive API key configuration"""
    key_id: str
    key_hash: str  # bcrypt hash
    tenant_id: str
    collection_ids: List[str]

    # Permissions
    permissions: Dict[str, List[str]]  # {"documents": ["read", "write"]}

    # Rate limiting
    rate_limit_per_minute: int
    rate_limit_per_hour: int
    burst_limit: int

    # Security
    allowed_ips: Optional[List[str]]
    require_https: bool

    # Lifecycle
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    rotation_required_by: Optional[datetime]

    # Metadata
    created_by: str
    description: str
    tags: List[str]

class EnterpriseAuthManager:
    """Handles authentication and authorization"""

    async def authenticate_request(self, request: Request) -> AuthContext:
        """Authenticate and authorize API request"""

        # 1. Extract API key
        api_key = self._extract_api_key(request)
        if not api_key:
            raise AuthenticationError("No API key provided")

        # 2. Check cache first
        cached = await self.redis.get(f"auth:{api_key[:8]}")
        if cached:
            return AuthContext.from_cache(cached)

        # 3. Validate against database
        key_config = await self.pg.fetchone("""
            SELECT * FROM api_keys
            WHERE key_id = $1 AND active = true
        """, api_key[:8])

        if not key_config:
            raise AuthenticationError("Invalid API key")

        # 4. Verify hash
        if not bcrypt.checkpw(api_key.encode(), key_config.key_hash):
            raise AuthenticationError("Invalid API key")

        # 5. Check expiration
        if key_config.expires_at and key_config.expires_at < datetime.utcnow():
            raise AuthenticationError("API key expired")

        # 6. Check IP restrictions
        if key_config.allowed_ips and request.client_ip not in key_config.allowed_ips:
            raise AuthorizationError("IP not allowed")

        # 7. Check rate limits
        if not await self._check_rate_limits(key_config, request):
            raise RateLimitError("Rate limit exceeded")

        # 8. Build auth context
        auth_context = AuthContext(
            tenant_id=key_config.tenant_id,
            collection_ids=key_config.collection_ids,
            permissions=key_config.permissions,
            user_id=key_config.created_by,
            api_key_id=key_config.key_id
        )

        # 9. Cache for performance
        await self.redis.setex(
            f"auth:{api_key[:8]}",
            300,  # 5 minutes
            auth_context.to_json()
        )

        # 10. Update last used
        await self._update_last_used(key_config.key_id)

        return auth_context
```

### Document-Level Security

```python
@dataclass
class DocumentSecurity:
    """Fine-grained document access control"""
    access_level: Literal["public", "internal", "restricted", "confidential"]

    # Access lists
    allowed_groups: List[str]
    allowed_users: List[str]
    excluded_users: List[str]  # Blacklist overrides allow

    # Security features
    encryption_at_rest: bool
    require_mfa: bool
    watermark_on_retrieval: bool

    # Audit
    audit_access: bool
    audit_modifications: bool

    # Compliance
    data_classification: str  # "public", "pii", "phi", "proprietary"
    retention_policy_days: Optional[int]
    legal_hold: bool
    gdpr_erasure_exempt: bool

    # Metadata
    classification_date: datetime
    classified_by: str
    next_review_date: Optional[datetime]

class DocumentSecurityEnforcer:
    """Enforces document-level security policies"""

    async def filter_search_results(
        self,
        results: List[SearchResult],
        auth_context: AuthContext
    ) -> List[SearchResult]:
        """Filter search results based on permissions"""

        filtered = []
        for result in results:
            # Load document security
            security = await self._load_document_security(result.doc_id)

            # Check access
            if await self._check_document_access(security, auth_context):
                # Apply watermark if needed
                if security.watermark_on_retrieval:
                    result = self._apply_watermark(result, auth_context)

                # Audit if required
                if security.audit_access:
                    await self._audit_access(result.doc_id, auth_context)

                filtered.append(result)
            else:
                # Audit denied access
                await self._audit_denied_access(result.doc_id, auth_context)

        return filtered
```

## MCP Server Per Tenant

### Tenant MCP Server Implementation

```python
class TenantMCPServer:
    """Each tenant gets customized MCP server"""

    def __init__(self, tenant_config: TenantConfig):
        self.tenant_id = tenant_config.tenant_id
        self.server = Server(f"tenant_{self.tenant_id}_mcp")
        self.tools = {}

        # Initialize components
        self.search_engine = TenantSearchEngine(tenant_config)
        self.document_store = TenantDocumentStore(tenant_config)
        self.analytics = TenantAnalytics(tenant_config)

        # Register tools
        self._register_standard_tools()
        self._register_tenant_tools(tenant_config.custom_tools)

    def _register_standard_tools(self):
        """Register standard MCP tools available to all tenants"""

        @self.server.tool(
            name="search_documents",
            description="Search tenant document collection with advanced options"
        )
        async def search_documents(
            query: str,
            pipeline: str = "default",
            filters: dict = None,
            top_k: int = 10,
            include_metadata: bool = True,
            explain_scores: bool = False
        ) -> dict:
            # Get pipeline configuration
            pipeline_config = self.tenant_config.search_pipelines.get(
                pipeline,
                self.tenant_config.default_pipeline
            )

            # Execute search
            results = await self.search_engine.search(
                query=query,
                pipeline_config=pipeline_config,
                filters=filters,
                top_k=top_k
            )

            # Add explanations if requested
            if explain_scores:
                results = await self._explain_scores(results, query)

            return {
                "results": results.documents,
                "total": results.total,
                "confidence": results.confidence,
                "pipeline": pipeline,
                "explanations": results.explanations if explain_scores else None
            }

        @self.server.tool(
            name="ingest_document",
            description="Dynamically add documents to collection"
        )
        async def ingest_document(
            url: str = None,
            content: str = None,
            file_path: str = None,
            metadata: dict = None,
            security: dict = None,
            processing_options: dict = None
        ) -> dict:
            # Validate input
            if not any([url, content, file_path]):
                raise ValueError("Must provide url, content, or file_path")

            # Create document
            doc = Document(
                content=content,
                metadata=metadata or {},
                security=DocumentSecurity(**security) if security else None
            )

            # Process based on source
            if url:
                doc = await self.document_store.fetch_and_process_url(
                    url, doc, processing_options
                )
            elif file_path:
                doc = await self.document_store.process_file(
                    file_path, doc, processing_options
                )

            # Index document
            doc_id = await self.document_store.store(doc)
            await self.search_engine.index_document(doc_id)

            return {
                "doc_id": doc_id,
                "status": "indexed",
                "metadata": doc.metadata,
                "processing_time_ms": doc.processing_time
            }

        @self.server.tool(
            name="analyze_document_gaps",
            description="Identify missing documentation based on queries"
        )
        async def analyze_document_gaps(
            recent_queries: int = 100,
            confidence_threshold: float = 0.5
        ) -> dict:
            # Get recent low-confidence queries
            queries = await self.analytics.get_recent_queries(
                limit=recent_queries,
                max_confidence=confidence_threshold
            )

            # Analyze patterns
            gaps = await self.gap_analyzer.analyze_queries(queries)

            # Suggest sources
            suggestions = await self.source_recommender.recommend(gaps)

            return {
                "gap_summary": gaps.summary,
                "missing_topics": gaps.topics,
                "suggested_sources": suggestions,
                "confidence": gaps.confidence,
                "based_on_queries": len(queries)
            }

        @self.server.tool(
            name="optimize_search_pipeline",
            description="Analyze and optimize search performance"
        )
        async def optimize_search_pipeline(
            pipeline: str = "default",
            test_queries: List[str] = None,
            optimization_goal: str = "relevance"  # or "speed"
        ) -> dict:
            # Get current configuration
            current_config = self.tenant_config.search_pipelines[pipeline]

            # Run optimization
            optimizer = SearchPipelineOptimizer(
                current_config,
                goal=optimization_goal
            )

            if test_queries:
                # Use provided queries
                results = await optimizer.optimize_with_queries(test_queries)
            else:
                # Use historical data
                results = await optimizer.optimize_from_history(
                    self.analytics.get_query_history()
                )

            return {
                "current_performance": results.baseline_metrics,
                "optimized_performance": results.optimized_metrics,
                "recommended_changes": results.config_changes,
                "improvement_percentage": results.improvement,
                "apply_changes_command": f"apply_optimization_{results.id}"
            }
```

### MCP Server Orchestration

```python
class MCPServerOrchestrator:
    """Manages fleet of tenant MCP servers"""

    def __init__(self):
        self.servers: Dict[str, MCPServerInstance] = {}
        self.load_balancer = LoadBalancer()
        self.health_monitor = HealthMonitor()

    async def ensure_tenant_server(self, tenant_id: str) -> MCPServerEndpoint:
        """Ensure MCP server is running for tenant"""

        if tenant_id in self.servers:
            # Check health
            if await self.health_monitor.is_healthy(tenant_id):
                return self.servers[tenant_id].endpoint
            else:
                # Restart unhealthy server
                await self.restart_tenant_server(tenant_id)

        # Start new server
        return await self.start_tenant_server(tenant_id)

    async def start_tenant_server(self, tenant_id: str) -> MCPServerEndpoint:
        """Start MCP server for tenant"""

        # Load configuration
        config = await self.load_tenant_config(tenant_id)

        # Create server instance
        server = TenantMCPServer(config)

        # Find available port
        port = await self.find_available_port(
            base=8000 + hash(tenant_id) % 1000
        )

        # Start server process
        process = await self.start_server_process(
            server,
            host="0.0.0.0",
            port=port
        )

        # Register with service discovery
        endpoint = MCPServerEndpoint(
            url=f"http://localhost:{port}",
            tenant_id=tenant_id,
            capabilities=server.list_tools()
        )

        await self.service_registry.register(endpoint)

        # Store reference
        self.servers[tenant_id] = MCPServerInstance(
            server=server,
            process=process,
            endpoint=endpoint,
            started_at=datetime.utcnow()
        )

        return endpoint

    async def scale_tenant(self, tenant_id: str, target_replicas: int):
        """Scale MCP servers for high-traffic tenants"""

        current = self.get_replica_count(tenant_id)

        if target_replicas > current:
            # Scale up
            new_instances = []
            for i in range(current, target_replicas):
                instance = await self.start_tenant_server_replica(
                    tenant_id,
                    replica_id=i
                )
                new_instances.append(instance)

            # Update load balancer
            await self.load_balancer.add_backends(
                tenant_id,
                [inst.endpoint for inst in new_instances]
            )

        elif target_replicas < current:
            # Scale down gracefully
            await self.scale_down_tenant(
                tenant_id,
                current - target_replicas
            )
```

## Tenant-Specific Search Pipelines

### Configurable Pipeline Framework

```python
@dataclass
class TenantSearchPipeline:
    """Highly configurable search pipeline per tenant"""

    name: str
    description: str

    # Pipeline stages
    stages: List[SearchStage]

    # Fusion configuration
    fusion: FusionConfig

    # Reranking
    reranker: Optional[RerankerConfig]

    # Performance
    timeout_ms: int = 5000
    cache_results: bool = True

    # Optimization
    auto_optimize: bool = True
    optimization_goal: str = "balanced"  # "relevance", "speed", "balanced"

@dataclass
class SearchStage:
    """Individual stage in search pipeline"""

    stage_id: str
    type: Literal["vector", "sparse", "colbert", "keyword", "filter", "custom"]

    # Model configuration
    model: Optional[str]
    model_params: Dict[str, Any]

    # Execution
    weight: float
    timeout_ms: int
    fallback_stage: Optional[str]

    # Stage-specific config
    config: Dict[str, Any]

class AdaptiveSearchPipeline:
    """Self-optimizing search pipeline"""

    def __init__(self, tenant_id: str, pipeline_config: TenantSearchPipeline):
        self.tenant_id = tenant_id
        self.config = pipeline_config
        self.metrics_collector = MetricsCollector(tenant_id)
        self.optimizer = PipelineOptimizer()

    async def execute(self, query: str, context: SearchContext) -> SearchResults:
        """Execute search with automatic optimization"""

        # Start timing
        start_time = time.time()

        # Execute stages
        stage_results = await self._execute_stages(query, context)

        # Fuse results
        fused_results = await self._fuse_results(stage_results)

        # Rerank if configured
        if self.config.reranker:
            fused_results = await self._rerank(query, fused_results)

        # Collect metrics
        execution_time = time.time() - start_time
        await self.metrics_collector.record_search(
            query=query,
            pipeline=self.config.name,
            results=fused_results,
            execution_time=execution_time,
            stage_timings=self._get_stage_timings()
        )

        # Auto-optimize if enabled
        if self.config.auto_optimize:
            await self._maybe_optimize()

        return fused_results

    async def _execute_stages(self, query: str, context: SearchContext):
        """Execute pipeline stages with optimization"""

        # Group stages for parallel execution
        execution_plan = self._create_execution_plan()

        results = {}
        for phase in execution_plan:
            # Execute stages in parallel within phase
            phase_tasks = []

            for stage in phase.stages:
                if stage.type == "vector":
                    task = self._execute_vector_search(
                        query, stage, context
                    )
                elif stage.type == "sparse":
                    task = self._execute_sparse_search(
                        query, stage, context
                    )
                elif stage.type == "colbert":
                    task = self._execute_colbert_search(
                        query, stage, context
                    )
                elif stage.type == "keyword":
                    task = self._execute_keyword_search(
                        query, stage, context
                    )
                elif stage.type == "custom":
                    task = self._execute_custom_stage(
                        query, stage, context, results
                    )

                # Wrap with timeout
                task = asyncio.wait_for(
                    task,
                    timeout=stage.timeout_ms / 1000
                )

                phase_tasks.append((stage.stage_id, task))

            # Execute phase
            phase_results = await asyncio.gather(
                *[task for _, task in phase_tasks],
                return_exceptions=True
            )

            # Process results
            for (stage_id, _), result in zip(phase_tasks, phase_results):
                if isinstance(result, Exception):
                    # Handle failure
                    logger.warning(f"Stage {stage_id} failed: {result}")
                    if stage.fallback_stage:
                        # Execute fallback
                        result = await self._execute_fallback(
                            stage.fallback_stage, query, context
                        )
                else:
                    results[stage_id] = result

        return results
```

### Example Pipeline Configurations

```python
# Technical Documentation Pipeline
TECHNICAL_SEARCH_PIPELINE = TenantSearchPipeline(
    name="technical_documentation",
    description="Optimized for technical manuals and datasheets",

    stages=[
        SearchStage(
            stage_id="exact_match",
            type="keyword",
            model="postgresql_fts",
            weight=0.3,
            config={
                "match_type": "phrase",
                "boost_exact": 2.0,
                "use_synonyms": False
            }
        ),
        SearchStage(
            stage_id="semantic",
            type="vector",
            model="text-embedding-3-small",
            weight=0.3,
            config={
                "normalize": True,
                "diversity_penalty": 0.1
            }
        ),
        SearchStage(
            stage_id="token_match",
            type="colbert",
            model="colbert-v2-technical",
            weight=0.4,
            config={
                "max_tokens": 512,
                "token_score_threshold": 0.7
            }
        ),
        SearchStage(
            stage_id="metadata_boost",
            type="filter",
            weight=0.0,  # Modifier only
            config={
                "boost_fields": {
                    "product_model": 1.5,
                    "error_code": 2.0,
                    "version": 1.2
                }
            }
        )
    ],

    fusion=FusionConfig(
        method="learned",
        model="fusion-net-v2",
        fallback="reciprocal_rank"
    ),

    reranker=RerankerConfig(
        model="cross-encoder/ms-marco-MiniLM-L-12-v2",
        top_k=10,
        min_score=0.5
    ),

    auto_optimize=True,
    optimization_goal="relevance"
)

# E-commerce Product Search Pipeline
ECOMMERCE_PIPELINE = TenantSearchPipeline(
    name="product_search",
    description="Optimized for product discovery and comparison",

    stages=[
        SearchStage(
            stage_id="attribute_match",
            type="sparse",
            model="splade-v3-product",
            weight=0.5,
            config={
                "expansion_weight": 0.3,
                "attribute_fields": ["color", "size", "brand", "category"]
            }
        ),
        SearchStage(
            stage_id="visual_similarity",
            type="vector",
            model="clip-product-v2",
            weight=0.3,
            config={
                "modality": "text",  # or "image"
                "diversity_boost": 0.2
            }
        ),
        SearchStage(
            stage_id="inventory_filter",
            type="filter",
            weight=0.0,
            config={
                "hard_filters": {
                    "in_stock": True,
                    "price_range": "user_defined"
                },
                "soft_filters": {
                    "popularity_score": 0.1,
                    "review_rating": 0.1
                }
            }
        ),
        SearchStage(
            stage_id="personalization",
            type="custom",
            weight=0.2,
            config={
                "model": "user-preference-net",
                "features": ["browsing_history", "purchase_history", "demographics"]
            }
        )
    ],

    fusion=FusionConfig(
        method="weighted_sum",
        normalize="min_max"
    ),

    reranker=RerankerConfig(
        model="product-reranker-v3",
        features=["price", "availability", "user_affinity"],
        personalized=True
    )
)
```

## Agentic Workflows

### Workflow Framework

```python
class AgenticWorkflow:
    """Base class for sophisticated multi-step workflows"""

    def __init__(
        self,
        tenant_id: str,
        workflow_config: WorkflowConfig,
        mcp_client: MCPClient
    ):
        self.tenant_id = tenant_id
        self.config = workflow_config
        self.mcp = mcp_client
        self.state = WorkflowState()
        self.llm = self._init_llm(workflow_config.llm_config)

    async def execute(self, initial_input: Dict[str, Any]) -> WorkflowResult:
        """Execute workflow with state management and error handling"""

        # Initialize workflow
        self.state.initialize(
            workflow_id=str(uuid.uuid4()),
            input=initial_input,
            started_at=datetime.utcnow()
        )

        try:
            # Execute workflow steps
            while not self.state.is_terminal():
                # Get next step
                next_step = self._determine_next_step()

                # Execute step
                step_result = await self._execute_step(next_step)

                # Update state
                self.state.record_step(next_step, step_result)

                # Check for early termination
                if self._should_terminate(step_result):
                    self.state.mark_terminated(step_result.reason)
                    break

            # Generate final result
            final_result = await self._generate_result()

            # Record completion
            self.state.mark_completed(final_result)

            return final_result

        except Exception as e:
            # Handle failure
            self.state.mark_failed(e)
            return await self._handle_failure(e)

        finally:
            # Cleanup and persist state
            await self._cleanup()
            await self._persist_state()
```

### Example: Advanced Tech Support Workflow

```python
class AdvancedTechSupportWorkflow(AgenticWorkflow):
    """Multi-stage technical support with learning"""

    async def execute(self, user_query: str) -> TechSupportResult:
        # Step 1: Query Understanding
        understanding = await self.llm.analyze(
            prompt=QUERY_ANALYSIS_PROMPT,
            query=user_query,
            extract_schema={
                "intent": "enum[troubleshooting,howto,compatibility,feature_request]",
                "products": "list[string]",
                "error_indicators": "list[string]",
                "urgency": "enum[low,medium,high,critical]",
                "technical_level": "enum[beginner,intermediate,expert]",
                "context_needed": "list[string]"
            }
        )
        self.state.set("understanding", understanding)

        # Step 2: Context Gathering
        if understanding.context_needed:
            context = await self._gather_context(understanding.context_needed)
            self.state.set("context", context)

        # Step 3: Multi-Strategy Search
        search_strategies = self._select_search_strategies(understanding)
        search_tasks = []

        for strategy in search_strategies:
            if strategy == "technical_docs":
                task = self.mcp.search_documents(
                    query=user_query,
                    pipeline="technical_support",
                    filters={
                        "products": understanding.products,
                        "document_type": ["manual", "troubleshooting", "faq"]
                    }
                )
            elif strategy == "similar_issues":
                task = self.mcp.search_similar_issues(
                    error_indicators=understanding.error_indicators,
                    products=understanding.products
                )
            elif strategy == "community_knowledge":
                task = self.mcp.search_community(
                    query=user_query,
                    min_relevance=0.7
                )

            search_tasks.append((strategy, task))

        # Execute searches in parallel
        search_results = {}
        for strategy, task in search_tasks:
            try:
                result = await task
                search_results[strategy] = result
            except Exception as e:
                logger.warning(f"Search strategy {strategy} failed: {e}")

        self.state.set("search_results", search_results)

        # Step 4: Confidence Assessment
        confidence = self._assess_result_confidence(search_results)

        if confidence < 0.6:
            # Step 5: Dynamic Knowledge Acquisition
            gaps = await self.mcp.analyze_document_gaps(
                query=user_query,
                existing_results=search_results
            )

            if gaps["gap_detected"]:
                # Fetch missing documentation
                acquisition_tasks = []
                for source in gaps["suggested_sources"][:5]:
                    task = self.mcp.ingest_document(
                        url=source["url"],
                        metadata={
                            "source": "dynamic_acquisition",
                            "query": user_query,
                            "gap_type": source["gap_type"]
                        },
                        processing_options={
                            "fast_mode": True,
                            "extract_troubleshooting": True
                        }
                    )
                    acquisition_tasks.append(task)

                # Ingest new documents
                ingestion_results = await asyncio.gather(
                    *acquisition_tasks,
                    return_exceptions=True
                )

                self.state.set("acquired_documents", [
                    r for r in ingestion_results
                    if not isinstance(r, Exception)
                ])

                # Re-search with expanded knowledge
                enhanced_results = await self.mcp.search_documents(
                    query=user_query,
                    pipeline="technical_support",
                    filters={
                        "products": understanding.products,
                        "$or": [
                            {"document_type": ["manual", "troubleshooting"]},
                            {"source": "dynamic_acquisition"}
                        ]
                    }
                )

                search_results["enhanced"] = enhanced_results
                confidence = self._assess_result_confidence(search_results)

        # Step 6: Solution Generation
        if confidence > 0.8:
            # High confidence - generate detailed solution
            solution = await self._generate_detailed_solution(
                query=user_query,
                understanding=understanding,
                search_results=search_results
            )
        elif confidence > 0.5:
            # Medium confidence - generate with caveats
            solution = await self._generate_tentative_solution(
                query=user_query,
                understanding=understanding,
                search_results=search_results
            )
        else:
            # Low confidence - escalate to human
            solution = await self._generate_escalation(
                query=user_query,
                understanding=understanding,
                search_results=search_results,
                reason="low_confidence"
            )

        # Step 7: Solution Verification (for critical issues)
        if understanding.urgency in ["high", "critical"] and solution.type != "escalation":
            verification = await self._verify_solution(solution)
            if not verification.is_safe:
                solution = await self._generate_escalation(
                    query=user_query,
                    understanding=understanding,
                    search_results=search_results,
                    reason="safety_concern",
                    details=verification.concerns
                )

        # Step 8: Response Enhancement
        enhanced_response = await self._enhance_response(
            solution=solution,
            user_level=understanding.technical_level,
            preferred_format=context.get("preferred_format", "steps")
        )

        # Step 9: Learning Feedback
        await self._record_interaction(
            query=user_query,
            understanding=understanding,
            solution=solution,
            confidence=confidence
        )

        return TechSupportResult(
            solution=enhanced_response,
            confidence=confidence,
            sources=self._extract_sources(search_results),
            follow_up_suggestions=self._generate_follow_ups(solution),
            escalation=solution.type == "escalation",
            workflow_id=self.state.workflow_id
        )
```

## Multi-Vector Search

### Qdrant Multi-Vector Configuration

```python
class MultiVectorManager:
    """Manages multiple vector representations per document"""

    async def create_multi_vector_collection(
        self,
        tenant_id: str,
        collection_name: str,
        vector_configs: Dict[str, VectorConfig]
    ):
        """Create collection with multiple vector types"""

        full_name = f"{tenant_id}_{collection_name}"

        # Define vector configurations
        vectors_config = {}

        # Dense embeddings (semantic search)
        if "dense" in vector_configs:
            vectors_config["dense"] = VectorParams(
                size=vector_configs["dense"].dimensions,
                distance=Distance.COSINE,
                hnsw_config=HnswConfig(
                    m=32,
                    ef_construct=200,
                    full_scan_threshold=10000
                )
            )

        # Sparse embeddings (SPLADE)
        if "sparse" in vector_configs:
            vectors_config["sparse"] = VectorParams(
                size=vector_configs["sparse"].dimensions,  # e.g., 30000
                distance=Distance.DOT,
                datatype=Datatype.UINT8,  # Quantized
                modifier=Modifier.IDF,  # IDF weighting
                sparse_vectors_config=SparseVectorConfig(
                    full_scan_threshold=5000
                )
            )

        # ColBERT embeddings (token-level)
        if "colbert" in vector_configs:
            vectors_config["colbert"] = VectorParams(
                size=vector_configs["colbert"].dimensions,  # e.g., 128
                distance=Distance.COSINE,
                on_disk=True,  # Large collections
                hnsw_config=HnswConfig(
                    m=16,  # Lower M for many vectors
                    ef_construct=100
                )
            )

        # BGE-M3 multi-representation
        if "bge_m3" in vector_configs:
            vectors_config["bge_m3_dense"] = VectorParams(
                size=1024,
                distance=Distance.COSINE
            )
            vectors_config["bge_m3_sparse"] = VectorParams(
                size=250002,
                distance=Distance.DOT,
                datatype=Datatype.FLOAT16
            )
            vectors_config["bge_m3_colbert"] = VectorParams(
                size=1024,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(
                    comparator=MultiVectorComparator.MAX_SIM
                )
            )

        # Create collection
        await self.qdrant.create_collection(
            collection_name=full_name,
            vectors_config=vectors_config,

            # Optimizations for multi-vector
            optimizers_config=OptimizersConfig(
                indexing_threshold=20000,
                memmap_threshold=100000,
                default_segment_number=4  # Parallelism
            ),

            # Quantization for efficiency
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8,
                    quantile=0.99,
                    always_ram=True
                )
            ),

            # Sharding for scale
            shard_number=4,
            replication_factor=2
        )
```

### ColBERT Implementation

```python
class ColBERTManager:
    """Manages ColBERT token-level embeddings"""

    def __init__(self, model_name: str = "colbert-ir/colbertv2.0"):
        self.model = ColBERTModel.from_pretrained(model_name)
        self.tokenizer = ColBERTTokenizer.from_pretrained(model_name)

    async def index_document(
        self,
        doc_id: str,
        text: str,
        tenant_id: str,
        collection: str
    ) -> IndexingResult:
        """Index document with ColBERT embeddings"""

        # Tokenize document
        doc_tokens = self.tokenizer.tokenize(
            text,
            max_length=512,
            add_special_tokens=True
        )

        # Generate embeddings
        with torch.no_grad():
            doc_embeddings = self.model.doc_encoder(doc_tokens)

        # Prepare points for batch insert
        points = []
        for idx, (token, embedding) in enumerate(zip(doc_tokens, doc_embeddings)):
            points.append(
                PointStruct(
                    id=f"{doc_id}_tok_{idx}",
                    vector={
                        "colbert": embedding.cpu().numpy().tolist()
                    },
                    payload={
                        "doc_id": doc_id,
                        "token_idx": idx,
                        "token": token,
                        "tenant_id": tenant_id,
                        "position": idx / len(doc_tokens)  # Normalized position
                    }
                )
            )

        # Batch insert with retries
        batch_size = 100
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            await self.qdrant.upsert(
                collection_name=f"{tenant_id}_{collection}",
                points=batch,
                wait=True
            )

        return IndexingResult(
            doc_id=doc_id,
            num_tokens=len(points),
            status="success"
        )

    async def search(
        self,
        query: str,
        tenant_id: str,
        collection: str,
        top_k: int = 10,
        rerank_multiplier: int = 10
    ) -> List[ColBERTResult]:
        """ColBERT search with MaxSim scoring"""

        # Encode query
        query_tokens = self.tokenizer.tokenize(query)
        query_embeddings = self.model.query_encoder(query_tokens)

        # Stage 1: Retrieve candidate documents
        candidate_docs = set()
        doc_token_scores = defaultdict(lambda: defaultdict(float))

        # Search for each query token
        for q_idx, q_emb in enumerate(query_embeddings):
            results = await self.qdrant.search(
                collection_name=f"{tenant_id}_{collection}",
                query_vector=("colbert", q_emb.tolist()),
                limit=100 * rerank_multiplier,  # Over-retrieve
                query_filter=Filter(
                    must=[
                        FieldCondition(
                            key="tenant_id",
                            match=MatchValue(value=tenant_id)
                        )
                    ]
                )
            )

            # Track scores
            for hit in results:
                doc_id = hit.payload["doc_id"]
                token_idx = hit.payload["token_idx"]
                candidate_docs.add(doc_id)
                doc_token_scores[doc_id][(q_idx, token_idx)] = hit.score

        # Stage 2: Compute MaxSim scores
        doc_scores = {}
        for doc_id in candidate_docs:
            # For each query token, find max document token score
            query_token_max_scores = []

            for q_idx in range(len(query_embeddings)):
                max_score = max(
                    score
                    for (q_i, _), score in doc_token_scores[doc_id].items()
                    if q_i == q_idx
                ) if any(q_i == q_idx for (q_i, _) in doc_token_scores[doc_id]) else 0.0

                query_token_max_scores.append(max_score)

            # Sum of max scores (ColBERT scoring)
            doc_scores[doc_id] = sum(query_token_max_scores)

        # Stage 3: Retrieve top-k documents
        top_docs = sorted(
            doc_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:top_k]

        # Stage 4: Get document details
        results = []
        for doc_id, score in top_docs:
            # Get document metadata
            doc_info = await self._get_document_info(doc_id)

            # Create result
            results.append(
                ColBERTResult(
                    doc_id=doc_id,
                    score=score,
                    title=doc_info.title,
                    content_preview=doc_info.preview,
                    metadata=doc_info.metadata,
                    token_matches=self._get_token_matches(
                        doc_id,
                        doc_token_scores[doc_id]
                    )
                )
            )

        return results
```

### Advanced Fusion Strategies

```python
class MultiVectorFusion:
    """Sophisticated fusion for multi-vector search"""

    def __init__(self, config: FusionConfig):
        self.config = config
        self.fusion_model = self._load_fusion_model()

    async def fuse_results(
        self,
        vector_results: Dict[str, List[SearchResult]],
        query_features: QueryFeatures
    ) -> List[FusedResult]:
        """Fuse results from multiple vector types"""

        if self.config.method == "learned":
            return await self._learned_fusion(
                vector_results,
                query_features
            )
        elif self.config.method == "reciprocal_rank":
            return self._reciprocal_rank_fusion(
                vector_results,
                self.config.rrf_k
            )
        elif self.config.method == "score_based":
            return self._score_based_fusion(
                vector_results,
                self.config.score_weights
            )
        elif self.config.method == "rank_biased_overlap":
            return self._rbo_fusion(
                vector_results,
                self.config.rbo_p
            )

    async def _learned_fusion(
        self,
        vector_results: Dict[str, List[SearchResult]],
        query_features: QueryFeatures
    ) -> List[FusedResult]:
        """ML-based fusion using neural networks"""

        # Extract features for each document
        doc_features = defaultdict(dict)
        all_doc_ids = set()

        # Collect all document IDs
        for vector_type, results in vector_results.items():
            for result in results:
                all_doc_ids.add(result.doc_id)

        # Extract features
        for doc_id in all_doc_ids:
            # Position features
            for vector_type in ["dense", "sparse", "colbert"]:
                results = vector_results.get(vector_type, [])
                position = next(
                    (i for i, r in enumerate(results) if r.doc_id == doc_id),
                    -1
                )
                doc_features[doc_id][f"{vector_type}_position"] = (
                    1.0 / (position + 1) if position >= 0 else 0.0
                )

            # Score features
            for vector_type in ["dense", "sparse", "colbert"]:
                results = vector_results.get(vector_type, [])
                score = next(
                    (r.score for r in results if r.doc_id == doc_id),
                    0.0
                )
                doc_features[doc_id][f"{vector_type}_score"] = score

            # Cross-vector agreement
            doc_features[doc_id]["appearance_count"] = sum(
                1 for results in vector_results.values()
                if any(r.doc_id == doc_id for r in results)
            )

            # Query-specific features
            doc_features[doc_id]["query_length"] = query_features.token_count
            doc_features[doc_id]["query_type"] = query_features.query_type
            doc_features[doc_id]["has_entities"] = query_features.has_entities

        # Prepare for model
        feature_matrix = []
        doc_ids = []

        for doc_id, features in doc_features.items():
            feature_vector = [
                features.get(f, 0.0) for f in self.fusion_model.feature_names
            ]
            feature_matrix.append(feature_vector)
            doc_ids.append(doc_id)

        # Run fusion model
        fusion_scores = await self.fusion_model.predict(
            np.array(feature_matrix)
        )

        # Create fused results
        fused_results = []
        for doc_id, score in zip(doc_ids, fusion_scores):
            # Get best metadata from any vector type
            metadata = self._get_best_metadata(doc_id, vector_results)

            fused_results.append(
                FusedResult(
                    doc_id=doc_id,
                    fusion_score=float(score),
                    vector_scores={
                        vtype: next(
                            (r.score for r in results if r.doc_id == doc_id),
                            0.0
                        )
                        for vtype, results in vector_results.items()
                    },
                    metadata=metadata,
                    fusion_method="learned"
                )
            )

        # Sort by fusion score
        fused_results.sort(key=lambda x: x.fusion_score, reverse=True)

        return fused_results
```

## Storage Architecture

### Enterprise Storage Manager

```python
class EnterpriseStorageManager:
    """Manages document storage with full tenant isolation"""

    def __init__(self, config: StorageConfig):
        self.config = config
        self.adapter = self._create_adapter(config.adapter_type)

    def _create_adapter(self, adapter_type: str) -> StorageAdapter:
        """Create storage adapter based on configuration"""

        if adapter_type == "local":
            return LocalFileStorage(self.config.local)
        elif adapter_type == "s3":
            return S3Storage(self.config.s3)
        elif adapter_type == "azure":
            return AzureBlobStorage(self.config.azure)
        elif adapter_type == "hybrid":
            return HybridStorage(
                local=LocalFileStorage(self.config.local),
                remote=S3Storage(self.config.s3),
                policy=self.config.hybrid_policy
            )

    async def store_document(
        self,
        doc: Document,
        tenant_id: str,
        collection_id: str
    ) -> StorageResult:
        """Store document with tenant isolation"""

        # Generate storage key
        key = self._generate_storage_key(
            tenant_id,
            collection_id,
            doc.id
        )

        # Serialize document
        serialized = await self._serialize_document(doc)

        # Apply compression
        if self.config.compression_enabled:
            serialized = await self._compress(serialized)

        # Apply encryption if required
        if doc.security and doc.security.encryption_at_rest:
            serialized = await self._encrypt(
                serialized,
                tenant_id
            )

        # Store
        storage_path = await self.adapter.store(
            key=key,
            content=serialized,
            metadata={
                "tenant_id": tenant_id,
                "collection_id": collection_id,
                "doc_id": doc.id,
                "content_type": "application/jsonl",
                "compressed": self.config.compression_enabled,
                "encrypted": doc.security.encryption_at_rest if doc.security else False,
                "created_at": datetime.utcnow().isoformat()
            }
        )

        # Update registry
        await self._update_storage_registry(
            tenant_id,
            collection_id,
            doc.id,
            storage_path
        )

        return StorageResult(
            doc_id=doc.id,
            storage_path=storage_path,
            size_bytes=len(serialized),
            status="stored"
        )
```

### Local Storage Implementation

```python
class LocalFileStorage(StorageAdapter):
    """Enhanced local storage with tenant isolation"""

    def __init__(self, config: LocalStorageConfig):
        self.base_path = Path(config.base_path)
        self.max_file_size = config.max_file_size_mb * 1024 * 1024

    async def store(
        self,
        key: str,
        content: bytes,
        metadata: dict = None
    ) -> str:
        """Store content with tenant isolation"""

        # Validate size
        if len(content) > self.max_file_size:
            raise StorageError(f"Content exceeds max size: {len(content)}")

        # Create file path
        file_path = self.base_path / key
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write content
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(content)

        # Write metadata
        if metadata:
            meta_path = file_path.with_suffix('.meta.json')
            async with aiofiles.open(meta_path, 'w') as f:
                await f.write(json.dumps(metadata, indent=2))

        # Set permissions
        os.chmod(file_path, 0o600)  # Owner read/write only

        return str(file_path)

    async def retrieve(self, key: str) -> bytes:
        """Retrieve content by key"""

        file_path = self.base_path / key

        if not file_path.exists():
            raise StorageError(f"Key not found: {key}")

        async with aiofiles.open(file_path, 'rb') as f:
            content = await f.read()

        return content

    def generate_key(
        self,
        tenant_id: str,
        collection_id: str,
        doc_id: str
    ) -> str:
        """Generate hierarchical storage key"""

        # Use date partitioning for better organization
        date_part = datetime.utcnow().strftime("%Y/%m/%d")

        return f"tenants/{tenant_id}/collections/{collection_id}/{date_part}/{doc_id}.jsonl"
```

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-4)

**1. PostgreSQL Migration (#77)**
- Design schema with tenant isolation options
- Build migration tools from SQLite
- Implement connection pooling with pgbouncer
- Test concurrent access performance
- Create rollback procedures

**2. API Authentication (#78)**
- API key generation and management system
- Rate limiting with Redis
- Basic RBAC implementation
- Request authentication middleware
- Audit logging framework

**3. Local Storage Enhancement**
- Implement tenant directory structure
- Add compression and encryption support
- Create storage abstraction layer
- Build quota management

### Phase 2: Multi-Tenancy Core (Weeks 5-8)

**1. Enhanced Collections (#56)**
- Update existing PR with enterprise features
- Full tenant isolation implementation
- Collection lifecycle management
- Resource quotas and limits
- Collection templates

**2. Document Security (#79)**
- Document classification system
- Access control implementation
- Security metadata storage
- Encryption at rest for sensitive docs
- Audit trail system

**3. Secure Search (#80)**
- Search result filtering by permissions
- Query audit logging
- Performance optimization with security
- Cache security considerations

### Phase 3: Advanced Features (Weeks 9-12)

**1. MCP Servers (#81)**
- MCP server framework
- Per-tenant server deployment
- Standard tool implementations
- Service discovery and registry
- Health monitoring

**2. Search Pipelines (#82)**
- Pipeline configuration framework
- Tenant-specific optimizations
- Model selection per tenant
- A/B testing infrastructure
- Pipeline templates

**3. Agentic Workflows (#83)**
- Workflow execution framework
- State management system
- MCP client integration
- Industry-specific templates
- Error handling and recovery

### Phase 4: Intelligence Layer (Weeks 13-16)

**1. Multi-Vector Search (#84)**
- ColBERT implementation
- SPLADE integration
- BGE-M3 support
- Advanced fusion strategies
- Performance optimization

**2. Adaptive Optimization (#85)**
- Usage analytics collection
- Performance monitoring
- Automatic pipeline tuning
- A/B testing automation
- Cross-tenant insights

### Phase 5: Production Hardening (Weeks 17-18)

**1. Monitoring & Observability**
- Comprehensive metrics
- Distributed tracing
- Alert system
- Performance dashboards

**2. Backup & Disaster Recovery**
- Automated backup system
- Point-in-time recovery
- Cross-region replication
- Disaster recovery procedures

**3. Documentation & Training**
- API documentation
- Administrator guides
- Developer tutorials
- Migration guides

## Summary

This implementation guide extends the basic multi-tenant architecture with enterprise-grade features:

1. **PostgreSQL** provides the foundation for scalable, concurrent access
2. **API Authentication** enables secure multi-tenant access
3. **MCP Servers** enable sophisticated agentic workflows per tenant
4. **Configurable Search** allows optimization for each use case
5. **Multi-Vector Search** provides state-of-the-art retrieval
6. **Adaptive Optimization** ensures continuous improvement

The phased approach allows incremental delivery of value while building toward a comprehensive enterprise platform.
