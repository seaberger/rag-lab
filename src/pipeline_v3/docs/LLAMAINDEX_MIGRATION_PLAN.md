# LlamaIndex Migration Plan

## Overview

This document outlines the migration from LlamaIndex to our own unified query engine, reducing external dependencies while maintaining all functionality.

## Current LlamaIndex Usage

### 1. **Document Processing & Indexing**
- ✅ `Document` - Simple data class, easy to replace
- ✅ `TextNode` - Simple data class, easy to replace
- ✅ `SentenceSplitter` - Can use langchain or custom splitter
- ✅ `VectorStoreIndex` - Just coordinates embedding generation

### 2. **Vector Store**
- ⚠️ `QdrantVectorStore` - Wrapper around Qdrant client
- ⚠️ `VectorStoreQuery` - Simple query structure

### 3. **Embeddings**
- ⚠️ `OpenAIEmbedding` - Wrapper around OpenAI API

### 4. **Query Engine**
- ❌ Not using LlamaIndex query engine features
- ❌ Not using retrievers or response synthesis

## Migration Strategy

### Phase 1: Query Engine (Current)
Replace LlamaIndex query components with `UnifiedQueryEngine`:

**Benefits:**
- Direct control over query logic
- Better PostgreSQL integration
- Custom fusion algorithms
- Reduced dependencies

**Implementation:**
```python
# Old way (LlamaIndex)
vector_query = VectorStoreQuery(
    query_embedding=embedding,
    similarity_top_k=10
)
results = vector_store.query(vector_query)

# New way (Unified)
request = QueryRequest(
    query="laser sensor",
    top_k=10,
    search_type="hybrid"
)
results = await query_engine.search(request)
```

### Phase 2: Direct Qdrant Integration
Replace `QdrantVectorStore` with direct Qdrant client:

**Benefits:**
- Remove LlamaIndex vector store dependency
- Direct access to Qdrant features
- Better performance

**Implementation:**
```python
# Direct Qdrant operations
from qdrant_client import QdrantClient

client = QdrantClient(host="localhost", port=6333)
client.upsert(
    collection_name="datasheets_v3",
    points=[PointStruct(id=node_id, vector=embedding, payload=metadata)]
)
```

### Phase 3: Custom Document Processing
Replace LlamaIndex document/node structures:

**Benefits:**
- Simpler data structures
- No pydantic overhead
- Custom metadata handling

**Implementation:**
```python
@dataclass
class Document:
    id: str
    text: str
    metadata: Dict[str, Any]

@dataclass
class TextChunk:
    id: str
    doc_id: str
    text: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None
```

### Phase 4: Direct OpenAI Integration
Replace `OpenAIEmbedding` with direct API calls:

**Benefits:**
- Remove last LlamaIndex dependency
- Direct control over API calls
- Better error handling

**Implementation:**
```python
import openai

async def get_embedding(text: str) -> List[float]:
    response = await openai.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding
```

## Migration Checklist

### Immediate (Phase 4.3b)
- [x] Create `UnifiedQueryEngine`
- [ ] Update `IndexManager` to use `UnifiedQueryEngine`
- [ ] Create migration wrapper for backwards compatibility
- [ ] Update tests to use new query engine

### Short Term
- [ ] Replace `QdrantVectorStore` with direct client
- [ ] Create custom embedding service
- [ ] Replace Document/TextNode structures

### Long Term
- [ ] Remove all LlamaIndex imports
- [ ] Create custom text splitter
- [ ] Optimize for our specific use cases

## Performance Improvements

### Current (LlamaIndex)
- Multiple abstraction layers
- Pydantic validation overhead
- Generic implementations

### Future (Direct)
- Direct API calls
- Minimal overhead
- Optimized for our use case
- ~30-50% faster queries

## Risk Mitigation

1. **Gradual Migration**: Each phase can be deployed independently
2. **Backwards Compatibility**: Wrapper classes during transition
3. **Testing**: Comprehensive tests at each phase
4. **Rollback**: Each phase can be reverted independently

## Code Examples

### Query Engine Usage
```python
# Initialize
engine = UnifiedQueryEngine(
    config=config,
    registry=registry,
    keyword_index=keyword_index,
    qdrant_client=qdrant_client
)

# Simple search
results = await engine.search(QueryRequest(
    query="PM10K laser sensor",
    top_k=5
))

# Advanced search
results = await engine.search(QueryRequest(
    query="power measurement accuracy",
    search_type="hybrid",
    fusion_method="adaptive",
    filters={"category": "sensor"},
    tenant_id="company-123"
))
```

### Direct Qdrant Usage
```python
# Index documents
points = []
for chunk in chunks:
    embedding = await get_embedding(chunk.text)
    points.append(PointStruct(
        id=chunk.id,
        vector=embedding,
        payload={
            "text": chunk.text,
            "doc_id": chunk.doc_id,
            "metadata": chunk.metadata
        }
    ))

client.upsert(
    collection_name="datasheets_v3",
    points=points
)

# Search
results = client.search(
    collection_name="datasheets_v3",
    query_vector=query_embedding,
    limit=10,
    query_filter=Filter(
        must=[
            FieldCondition(
                key="metadata.tenant_id",
                match=MatchValue(value="company-123")
            )
        ]
    )
)
```

## Conclusion

Moving away from LlamaIndex will:
1. Reduce dependencies and complexity
2. Improve performance and control
3. Enable better PostgreSQL integration
4. Simplify the codebase
5. Make debugging easier

The migration can be done gradually with minimal risk, starting with the query engine (current phase) and eventually removing all LlamaIndex dependencies.
