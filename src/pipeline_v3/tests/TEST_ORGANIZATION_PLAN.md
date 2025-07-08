# Test Organization Plan for CI Optimization

## Current State Analysis

### Quick CI Tests (Run on every commit)
1. **Unit Tests** (289 tests) - No API calls ✅
2. **Security Tests** (33 tests) - No API calls ✅
3. **Integration Tests**:
   - `test_search_real_documents_optimized.py` - **USES OpenAI API** (2 docs) ✅
     - Processes 1 datasheet + 1 Word doc ONCE
     - Tests: vector search, keyword search, hybrid search, metadata extraction
     - Tests: search quality metrics, chunk-level search, cache functionality
     - **KEEP IN QUICK CI** - Already optimized for minimal API usage
4. **Smoke Tests** - Lightweight integration tests

### Comprehensive CI Tests (Run on-demand)
Currently empty - we need to move appropriate tests here WITHOUT duplicating Quick CI coverage.

## Proposed Reorganization

### Keep in Quick CI
1. **All Unit Tests** - Fast, no external dependencies
2. **All Security Tests** - Fast, critical for every commit
3. **Database Connectivity Tests** - Fast, ensure basic functionality
4. **CLI Validation Tests** - Fast, ensure interface works
5. **test_search_real_documents_optimized.py** - Already optimized (2 docs only)
6. **Smoke Tests** - Designed to be lightweight

### Move to Comprehensive CI
Mark these existing tests with `@pytest.mark.comprehensive`:

1. **test_e2e_integration.py**:
   - `test_document_ingestion` - Processes 5 documents (DUPLICATE of Quick CI - SKIP)
   - `test_complete_pipeline_flow` - Full pipeline with multiple docs
   - `test_environment_isolation` - Heavy isolation testing

2. **test_qdrant_server_operations.py**:
   - `test_batch_operations_server_mode` - Batch processing (5+ docs)
   - `test_collection_isolation` - Multiple collection testing

3. **Create New Comprehensive Tests** (NO OVERLAP with Quick CI):
   - `test_batch_processing.py` - Test 10+ documents ✅ (already created)
   - `test_performance_benchmarks.py` - Measure processing speed with 20+ docs
   - `test_edge_cases.py` - Test scenarios NOT covered in Quick CI:
     - Corrupted PDFs
     - Very large documents (100+ pages)
     - Non-English documents
     - Complex table-heavy documents
   - `test_stress_testing.py` - High load scenarios:
     - Concurrent processing of 50+ documents
     - Memory usage under load
     - Queue saturation testing

## Implementation Steps

### Step 1: Mark Heavy Tests
Add `@pytest.mark.comprehensive` to tests that:
- Process more than 3 documents
- Take longer than 30 seconds
- Test edge cases or stress scenarios
- Perform extensive API calls

### Step 2: Update Test Commands
**Quick CI**:
```bash
pytest -m "not comprehensive and not heavy"
```

**Comprehensive CI**:
```bash
pytest -m "comprehensive or heavy"
```

### Step 3: Document Test Categories
Create clear documentation about which tests belong where and why.

## What Quick CI Already Covers (DO NOT DUPLICATE)

The `test_search_real_documents_optimized.py` in Quick CI already tests:
1. **Document Processing**: 1 PDF datasheet + 1 Word document
2. **Search Types**: Vector, keyword, and hybrid search
3. **Metadata Extraction**: Datasheet parameters and specifications
4. **Search Quality**: Relevance scoring and result ranking
5. **Chunk-Level Search**: Fine-grained content retrieval
6. **Cache Functionality**: API response caching

**Comprehensive CI should test DIFFERENT scenarios, not more of the same.**

## Cost Analysis

### Current State
- Quick CI: ~$0.10-0.20 per run (test_search_real_documents_optimized.py)
- Comprehensive CI: ~$0.50-2.00 per run (if all e2e tests run)

### After Optimization
- Quick CI: ~$0.10-0.20 per run (same - keeping optimized test)
- Comprehensive CI: ~$1.00-3.00 per run (only when needed, no duplication)

## Benefits
1. **Fast Feedback**: Quick CI remains under 10 minutes
2. **Cost Control**: Heavy tests only run when needed
3. **Clear Separation**: Developers know what each pipeline tests
4. **Scalability**: Easy to add more comprehensive tests without slowing Quick CI
