# Test Ordering and Dependencies Guide

## Problem Summary

Some tests were failing because:
1. **Path Resolution**: Tests couldn't find sample documents due to relative path issues
2. **Execution Order**: Database cleanup tests ran before data consumption tests
3. **Data Dependencies**: Search tests expected documents that weren't created yet

## Solutions Implemented

### 1. Fixed Path Resolution in conftest.py
```python
# Now searches for project root dynamically
current_dir = Path(__file__).parent
while current_dir != current_dir.parent:
    if (current_dir / "data" / "sample_docs").exists():
        sample_dir = current_dir / "data" / "sample_docs"
        break
    current_dir = current_dir.parent
```

### 2. Test Class Naming for Order Control
- `Test_A_E2EIntegration` - Runs first, creates data
- `Test_B_SmokeIntegration` - Runs second
- `Test_Z_DatabaseIsolation` - Runs last, cleans up

### 3. Identified Test Dependencies

#### Data Creators (must run first):
- `test_document_ingestion` - Creates documents in registry
- `test_smoke_document_ingestion` - Quick document creation

#### Data Consumers (need data to exist):
- `test_search_functionality` - Searches for documents
- `test_complete_pipeline_flow` - Full workflow including search

#### Data Cleaners (must run last):
- `test_database_cleanup` - Removes all data
- `test_environment_isolation` - Creates/destroys environments

## Running Tests Correctly

### Run all tests in correct order:
```bash
cd src/pipeline_v3
uv run pytest tests/integration/test_e2e_integration.py -v
```

### Run specific test categories:
```bash
# Data creation tests only
uv run pytest tests/integration/test_e2e_integration.py::Test_A_E2EIntegration -v

# Cleanup tests only
uv run pytest tests/integration/test_e2e_integration.py::Test_Z_DatabaseIsolation -v
```

### Skip slow tests for quick runs:
```bash
uv run pytest tests/integration/test_e2e_integration.py -v -m "not slow"
```

## Alternative Solutions

### 1. pytest-order Plugin
```python
@pytest.mark.order(1)
def test_create_data():
    pass

@pytest.mark.order(-1)  # Run last
def test_cleanup():
    pass
```

### 2. Session Fixtures
```python
@pytest.fixture(scope="session", autouse=True)
def setup_test_data():
    # Create data once for all tests
    yield
    # Cleanup after all tests
```

### 3. Separate Test Modules
```
tests/
├── 01_setup/
├── 02_integration/
└── 99_cleanup/
```

## Key Learnings

1. **Test isolation is important** but some tests naturally have dependencies
2. **Execution order matters** when tests share state or data
3. **Path resolution** must work from any directory
4. **Document your dependencies** so other developers understand the constraints

## Remaining Issues

While individual tests pass, some still fail when run in the full suite due to:
- Timing issues with async operations
- Resource contention (Qdrant file locks)
- State pollution between test classes

These are harder to fix and may require:
- More aggressive cleanup between tests
- Longer delays between operations
- Moving to Qdrant server mode (Issue #71)
