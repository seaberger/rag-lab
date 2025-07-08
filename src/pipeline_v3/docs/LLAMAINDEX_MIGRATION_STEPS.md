# LlamaIndex Migration - Step-by-Step Plan

## Phase 1: Core Index Manager Migration

### Step 1: Replace index_manager.py imports
Replace LlamaIndex imports with custom structures:
- `Document` → `src.pipeline_v3.core.data_structures.Document`
- `TextNode` → `src.pipeline_v3.core.data_structures.TextChunk`
- `SentenceSplitter` → `src.pipeline_v3.core.data_structures.TextSplitter`
- `OpenAIEmbedding` → `src.pipeline_v3.core.embedding_service.EmbeddingService`
- Remove VectorStoreIndex, StorageContext, Settings imports

### Step 2: Update initialization methods
- Replace `OpenAIEmbedding` with `EmbeddingService`
- Replace `SentenceSplitter` with `TextSplitter`
- Remove LlamaIndex Settings usage
- Update text splitting to use new `create_chunks` method

### Step 3: Update document processing
- Replace `Document` creation with custom structure
- Update `text_splitter.get_nodes_from_documents` → `text_splitter.create_chunks`
- Remove VectorStoreIndex usage, use direct Qdrant client operations
- Update node/chunk metadata handling

### Step 4: Update search methods
- Remove VectorStoreQuery usage
- Use EmbeddingService for query embeddings
- Implement direct Qdrant search
- Update result processing for new structures

### Step 5: Update helper methods
- Update `_keyword_index_nodes` to work with TextChunk
- Update all node references to chunk references
- Ensure metadata compatibility

## Implementation Order

1. **Create backup**: Copy current `index_manager.py` to `index_manager_llama.py`
2. **Update imports**: Replace all LlamaIndex imports
3. **Update class initialization**: Replace embedding and splitter initialization
4. **Update add_document**: Use new structures and direct Qdrant operations
5. **Update add_nodes**: Rename to add_chunks, update implementation
6. **Update search methods**: Implement direct search without LlamaIndex
7. **Test incrementally**: Test each method as updated
8. **Remove legacy code**: Clean up unused imports and methods

## Key Changes

### Document Creation
```python
# Old (LlamaIndex)
doc = Document(text=content, doc_id=doc_id, metadata=metadata)

# New (Custom)
doc = Document(text=content, doc_id=doc_id, metadata=metadata)
```

### Text Splitting
```python
# Old (LlamaIndex)
nodes = self.text_splitter.get_nodes_from_documents([doc])

# New (Custom)
chunks = self.text_splitter.create_chunks(doc)
```

### Embeddings
```python
# Old (LlamaIndex)
self.embedding_model = OpenAIEmbedding(...)
embedding = self.embedding_model.get_text_embedding(text)

# New (Custom)
self.embedding_service = EmbeddingService(config)
embedding = self.embedding_service.get_text_embedding(text)
```

### Vector Indexing
```python
# Old (LlamaIndex)
VectorStoreIndex(nodes, storage_context=storage_context)

# New (Direct Qdrant)
points = []
for chunk, embedding in zip(chunks, embeddings):
    point = PointStruct(
        id=chunk.id,
        vector=embedding,
        payload={...}
    )
    points.append(point)
self.qdrant_client.upsert(collection_name=..., points=points)
```

## Testing Strategy

1. Create unit tests for new index_manager.py
2. Ensure backward compatibility for API
3. Test all search types (vector, keyword, hybrid)
4. Verify metadata preservation
5. Test with existing data

## Rollback Plan

If issues arise:
1. Revert to `index_manager_llama.py`
2. Debug specific failures
3. Fix incrementally
4. Re-test thoroughly
