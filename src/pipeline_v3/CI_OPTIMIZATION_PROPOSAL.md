# CI Pipeline Optimization Proposal

## Current Problem

1. **Redundancy**: Quick CI and Comprehensive CI run the same tests
2. **Inefficiency**: Comprehensive CI runs tests in 9 stages, potentially processing documents multiple times
3. **Misalignment**: Fast tests (security, unit) are unnecessarily in Comprehensive CI
4. **Cost**: Every Comprehensive CI run wastes API credits on redundant testing

## Proposed Solution

### Quick CI (Every Commit/PR)
**Purpose**: Fast feedback with minimal API usage
**Duration**: ~5-10 minutes

Include:
- ✅ All unit tests (no API calls)
- ✅ All security tests (no API calls)
- ✅ Database connectivity tests (no API calls)
- ✅ CLI tests (no API calls)
- ✅ Basic integration tests with mocked APIs
- ✅ `test_search_real_documents_optimized.py` (processes 2 docs once, tests all search functionality)
- ❌ Exclude: Tests marked as `@pytest.mark.heavy` or `@pytest.mark.comprehensive`

### Comprehensive CI (On-Demand Only)
**Purpose**: Extended validation with real-world scenarios
**Duration**: ~15-20 minutes

Include ONLY:
- ✅ Heavy document processing tests (`@pytest.mark.heavy`)
- ✅ Extended E2E tests (`@pytest.mark.e2e`)
- ✅ Multi-document batch processing
- ✅ Performance/stress tests
- ✅ Edge cases with various document types
- ❌ Exclude: Everything already tested in Quick CI

## Implementation Steps

### Step 1: Mark Tests Appropriately
```python
# For Comprehensive CI only
@pytest.mark.comprehensive
@pytest.mark.heavy
def test_batch_processing_100_documents():
    """Test processing large batches"""
    pass

# For Quick CI (default - no mark needed)
def test_basic_pdf_processing():
    """Test basic functionality"""
    pass
```

### Step 2: Update Quick CI Command
```yaml
# Quick CI - Exclude heavy/comprehensive tests
pytest src/pipeline_v3/tests/ \
  -m "not heavy and not comprehensive" \
  -k "not test_cli_regression" \
  --maxfail=5
```

### Step 3: Update Comprehensive CI Command
```yaml
# Comprehensive CI - ONLY run heavy/comprehensive tests
pytest src/pipeline_v3/tests/ \
  -m "heavy or comprehensive" \
  --timeout=1800
```

### Step 4: Create Shared Test Fixtures
```python
# conftest.py - Process documents once, share across all tests
@pytest.fixture(scope="session")
def processed_documents():
    """Process test documents once per session"""
    # Process 1 datasheet, 1 Word doc, 1 PowerPoint
    # Cache results for all tests to use
    pass
```

## Benefits

1. **No Redundancy**: Each test runs in exactly one pipeline
2. **Cost Savings**: ~80% reduction in API calls for Comprehensive CI
3. **Faster Feedback**: Quick CI remains fast, Comprehensive CI becomes focused
4. **Clear Purpose**: Each pipeline has a distinct role

## Test Migration Plan

### Move to Quick CI (from Comprehensive stages):
- Unit tests (already there)
- Security tests (already there)
- Database tests
- CLI tests
- Basic integration tests

### Keep in Comprehensive CI only:
- Batch processing tests
- Multi-document type tests
- Performance benchmarks
- Edge case scenarios
- Stress tests

## Example Test Structure

```
tests/
├── unit/              # Quick CI (no API)
├── security/          # Quick CI (no API)
├── integration/
│   ├── basic/         # Quick CI (mocked or optimized)
│   ├── heavy/         # Comprehensive CI only
│   └── test_search_real_documents_optimized.py  # Quick CI
└── comprehensive/     # New folder for Comprehensive CI only
    ├── test_batch_processing.py
    ├── test_performance_benchmarks.py
    └── test_edge_cases.py
```

## Next Steps

1. Audit existing tests to identify which need API calls
2. Add appropriate pytest markers
3. Create shared fixtures for document processing
4. Update CI configurations
5. Move heavy tests to dedicated folder/marks
6. Document which tests belong where

This approach will make Comprehensive CI truly comprehensive (not redundant) while keeping Quick CI fast and efficient.
