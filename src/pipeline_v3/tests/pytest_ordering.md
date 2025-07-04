# Pytest Test Ordering Solutions

## Current Solution: Alphabetical Naming

We've renamed test classes with prefixes to control execution order:
- `Test_A_*` - Setup and data creation tests (run first)
- `Test_B_*` - General tests (run middle)
- `Test_Z_*` - Cleanup and isolation tests (run last)

## Alternative Solutions

### 1. Using pytest-order Plugin

```bash
# Install plugin
pip install pytest-order

# Mark tests with order
import pytest

@pytest.mark.order(1)
class TestDataCreation:
    """Tests that create data"""

@pytest.mark.order(2)
class TestDataConsumption:
    """Tests that use data"""

@pytest.mark.order(-1)  # Run last
class TestCleanup:
    """Tests that clean up data"""
```

### 2. Using pytest Dependency Plugin

```bash
# Install plugin
pip install pytest-dependency

# Mark dependencies
@pytest.mark.dependency()
def test_create_data():
    pass

@pytest.mark.dependency(depends=["test_create_data"])
def test_search_data():
    pass
```

### 3. Session-Scoped Fixtures

```python
@pytest.fixture(scope="session")
def populated_test_data():
    """Create test data once for entire session"""
    # Create data
    yield data
    # Cleanup after all tests
```

### 4. Separate Test Runs in CI/CD

```yaml
# In GitHub Actions
- name: Run setup tests
  run: pytest tests/setup/

- name: Run integration tests
  run: pytest tests/integration/

- name: Run cleanup tests
  run: pytest tests/cleanup/
```

## Why Test Order Matters

1. **Data Dependencies**: Search tests need documents to exist
2. **Resource Cleanup**: Cleanup must happen after consumption
3. **Shared State**: Tests may share Qdrant collections or databases
4. **Performance**: Avoid recreating test data for each test

## Current Test Dependencies

### E2E Integration Tests
- `test_document_ingestion` - Creates documents
- `test_search_functionality` - Searches for documents
- `test_database_cleanup` - Removes all data (must run last!)

### Search Integration Tests
- Self-contained with `add_test_documents()` helper
- Don't depend on other tests

### CLI Regression Tests
- Mostly independent
- Some may be affected by global state changes
