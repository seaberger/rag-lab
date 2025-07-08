# CI Optimization Summary

## What We've Done

### 1. Registered `comprehensive` Marker
- Added `comprehensive` to pytest.ini markers
- Tests can now be marked with `@pytest.mark.comprehensive`

### 2. Updated CI Workflows
- **Quick CI** (`quick-ci.yml`): Runs on every commit/PR
  - Excludes tests marked as `comprehensive` or `heavy`
  - Includes optimized real document test (2 docs only)
  - ~5-10 minutes runtime

- **Comprehensive CI** (`comprehensive-ci.yml`): Runs on-demand only
  - Only runs tests marked as `comprehensive`
  - Triggered by: label, manual dispatch, or release tags
  - ~15-30 minutes runtime

### 3. Marked Existing Tests
Tests now marked as `@pytest.mark.comprehensive`:
- `test_e2e_integration.py`:
  - `test_document_ingestion` - Processes 5 documents
  - `test_complete_pipeline_flow` - Full pipeline flow
  - `test_environment_isolation` - Multi-environment testing
- `test_qdrant_server_operations.py`:
  - `test_batch_operations_server_mode` - 5+ document batch
  - `test_collection_isolation` - Multiple collections

### 4. Created New Comprehensive Test Structure
```
tests/comprehensive/
├── __init__.py
├── test_batch_processing.py      # 10+ document batches
├── test_edge_cases.py           # Scenarios NOT in Quick CI
└── test_performance_benchmarks.py # Performance at scale
```

### 5. Avoided Duplication
Quick CI already covers (via `test_search_real_documents_optimized.py`):
- Basic document processing (1 PDF + 1 Word doc)
- All search types (vector, keyword, hybrid)
- Metadata extraction
- Search quality metrics
- Cache functionality

Comprehensive CI focuses on:
- Large batches (10+ documents)
- Edge cases (large files, corrupted PDFs, non-English)
- Performance benchmarks
- Stress testing

## API Efficiency & PostgreSQL Compatibility

### Already Efficient Tests
- `test_batch_operations_server_mode` - Uses markdown files (no API calls)
- `test_collection_isolation` - Uses markdown files (no API calls)
- `test_document_ingestion` - Only processes 1 PDF (not 5 as originally thought)

### PostgreSQL Compatibility
✅ All tests use `DatabaseFactory` with PostgreSQL adapters
✅ The `test_pipeline` fixture properly initializes PostgreSQL connections
✅ Tests should work with the multi-tenant PostgreSQL architecture

### New Optimized Test
Created `test_multi_document_processing.py` that:
- Processes 5 documents ONCE using class-scoped fixture
- Tests different modes (datasheet vs generic)
- Tests with/without keyword enhancement
- Tests cross-format search (PDF, Word, PowerPoint)
- Measures batch performance metrics

## Next Steps

1. **Replace test_document_ingestion**: Consider using the new optimized multi-document test
2. **Add More Edge Cases**: Implement the placeholder tests with real scenarios
3. **Monitor Costs**: Track API usage difference between pipelines
4. **Documentation**: Update main docs with new CI strategy

## Running Tests

### Quick CI (local):
```bash
pytest -m "not comprehensive and not heavy"
```

### Comprehensive CI (local):
```bash
pytest -m "comprehensive"
```

### All Comprehensive Tests:
```bash
pytest src/pipeline_v3/tests/comprehensive/ -v
```
