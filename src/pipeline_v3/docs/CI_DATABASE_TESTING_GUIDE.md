# CI Database Testing Guide

This guide explains the database testing strategy for RAG Lab Pipeline v3, supporting both local development and CI/CD environments.

## Overview

Our testing strategy uses real PostgreSQL and Qdrant databases for integration and e2e tests, while allowing unit tests to run without external dependencies.

## Test Categories

### 1. Unit Tests (`@pytest.mark.unit`)
- **Purpose**: Test individual components in isolation
- **Database**: None or mocked
- **Speed**: Fast (<1 second per test)
- **Examples**: Configuration parsing, utility functions, data structures

### 2. Integration Tests (`@pytest.mark.integration`)
- **Purpose**: Test component interactions
- **Database**: Real PostgreSQL and Qdrant (when marked)
- **Speed**: Medium (1-10 seconds per test)
- **Examples**: Document registry operations, search functionality

### 3. E2E Tests (`@pytest.mark.e2e`)
- **Purpose**: Test complete workflows
- **Database**: Real PostgreSQL and Qdrant required
- **Speed**: Slow (10+ seconds per test)
- **Examples**: Full document processing pipeline, multi-tenant scenarios

### 4. Security Tests (`@pytest.mark.security`)
- **Purpose**: Test security features and vulnerabilities
- **Database**: Real PostgreSQL for SQL injection tests
- **Speed**: Fast to medium
- **Examples**: SQL injection prevention, tenant isolation

## Database Requirements

### Tests Requiring PostgreSQL (`@pytest.mark.requires_postgres`)
- Document registry operations
- Keyword search with PostgreSQL FTS
- Job queue management
- Tenant isolation and RLS
- Migration tests

### Tests Requiring Qdrant (`@pytest.mark.requires_qdrant`)
- Vector search operations
- Hybrid search (vector + keyword)
- Collection management
- Embedding storage

## Running Tests

### Local Development

#### Run All Tests
```bash
# Ensure databases are running
docker-compose up -d postgres qdrant

# Run all tests
pytest

# Run with coverage
pytest --cov=src/pipeline_v3 --cov-report=html
```

#### Run by Category
```bash
# Fast unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Tests that don't need databases
pytest -m "not (requires_postgres or requires_qdrant)"

# PostgreSQL tests only
pytest -m requires_postgres

# All except slow tests
pytest -m "not slow"
```

### CI/CD Environment

In GitHub Actions, databases are automatically provisioned:

```yaml
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_PASSWORD: ${{ secrets.POSTGRES_PASSWORD }}

  qdrant:
    image: qdrant/qdrant:latest
```

The CI workflow:
1. Starts database services
2. Runs `ci_database_setup.py` to create test tenant
3. Executes tests with proper environment variables
4. Cleans up resources

## Test Database Setup

### Automatic Setup (Recommended)

Tests use the `test_databases` fixture which automatically:
1. Ensures databases are running
2. Creates a test tenant
3. Configures the test environment
4. Cleans up after tests

```python
@pytest.mark.integration
@pytest.mark.requires_postgres
def test_with_database(test_tenant_config):
    """Test using real PostgreSQL."""
    pipeline = EnhancedPipeline(test_tenant_config)
    # Test code here
```

### Manual Setup

For specific test scenarios:

```python
from src.pipeline_v3.tests.fixtures.test_database_setup import TestDatabaseManager

manager = TestDatabaseManager()
success, tenant_info = manager.ensure_databases_ready()
if success:
    tenant_id = tenant_info['tenant_id']
    # Run tests
    manager.cleanup_test_tenant()
```

## Environment Variables

### Local Development
Create `.env` file:
```bash
OPENAI_API_KEY=sk-...
POSTGRES_PASSWORD=your_password
```

Or use `.env.postgres`:
```bash
export POSTGRES_PASSWORD=your_password
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_DATABASE=rag_lab
export POSTGRES_USER=postgres
```

### GitHub Actions
Set repository secrets:
- `OPENAI_API_KEY`
- `POSTGRES_PASSWORD`

## Writing Database Tests

### Good Practices

1. **Use appropriate markers**:
```python
@pytest.mark.integration
@pytest.mark.requires_postgres
@pytest.mark.requires_qdrant
async def test_hybrid_search(test_tenant_config):
    """Test requiring both databases."""
    pass
```

2. **Use test fixtures**:
```python
def test_document_processing(test_tenant_config, sample_documents):
    """Use provided fixtures for consistency."""
    pipeline = EnhancedPipeline(test_tenant_config)
    result = pipeline.process_document(sample_documents["small_datasheet"])
```

3. **Clean up resources**:
```python
@pytest.fixture
def test_collection(test_tenant_config):
    """Create and clean up test collection."""
    manager = IndexManager(test_tenant_config)
    yield manager
    # Cleanup happens automatically via fixtures
```

### Bad Practices to Avoid

1. **Don't use SQLite in integration tests**:
```python
# BAD - SQLite is not supported
conn = sqlite3.connect(":memory:")

# GOOD - Use database adapters
from src.pipeline_v3.core.database_factory import DatabaseFactory
factory = DatabaseFactory(config)
adapters = factory.create_all()
```

2. **Don't hardcode credentials**:
```python
# BAD
password = "postgres"  # pragma: allowlist secret

# GOOD
from src.pipeline_v3.tests.fixtures.database_credentials import TestDatabaseCredentials
creds = TestDatabaseCredentials.get_postgres_credentials()
```

3. **Don't skip cleanup**:
```python
# BAD - Leaves test data
def test_something():
    create_test_data()
    # No cleanup!

# GOOD - Uses fixtures with automatic cleanup
def test_something(test_tenant_config):
    # Cleanup handled by fixture
```

## Troubleshooting

### PostgreSQL Connection Issues
```bash
# Check if PostgreSQL is running
lsof -i :5432

# Test connection
psql -h localhost -U postgres -d rag_lab

# Check logs
docker logs rag-lab-postgres
```

### Qdrant Connection Issues
```bash
# Check if Qdrant is running
lsof -i :6333

# Test API
curl http://localhost:6333/health

# Check logs
docker logs rag-lab-qdrant
```

### Test Tenant Issues
```bash
# Manually check test tenant
psql -h localhost -U postgres -d rag_lab -c "SELECT * FROM tenants.tenants WHERE name = 'test_tenant';"

# Force cleanup
psql -h localhost -U postgres -d rag_lab -c "DELETE FROM registry.documents WHERE tenant_id = (SELECT tenant_id FROM tenants.tenants WHERE name = 'test_tenant');"
```

## Performance Considerations

### Test Execution Time
- Unit tests: < 1 minute total
- Integration tests: 5-10 minutes
- E2E tests: 10-20 minutes
- Full suite: ~30 minutes

### Parallel Execution
```bash
# Run tests in parallel (requires pytest-xdist)
pytest -n auto

# Run specific marker in parallel
pytest -m unit -n 4
```

### Database Connection Pooling
Tests automatically use connection pooling to avoid exhausting database connections during parallel execution.

## CI/CD Optimization

### Quick CI (Default)
- Runs all tests together
- 10-minute timeout
- Fails fast on first 5 failures
- Suitable for PRs

### Comprehensive CI
- Runs tests in stages
- Detailed reporting
- Full coverage analysis
- Suitable for main branch

## Migration Guide

### Converting SQLite Tests to PostgreSQL

1. **Add markers**:
```python
@pytest.mark.integration
@pytest.mark.requires_postgres
```

2. **Use test fixtures**:
```python
# Before
def test_registry():
    registry = DocumentRegistry()  # Uses SQLite

# After
def test_registry(test_tenant_config):
    registry = DocumentRegistry(test_tenant_config)  # Uses PostgreSQL
```

3. **Update SQL syntax**:
```python
# SQLite
"SELECT * FROM documents WHERE source LIKE ?"

# PostgreSQL
"SELECT * FROM registry.documents WHERE source LIKE %s"
```

4. **Handle tenant context**:
```python
# Ensure tenant isolation
config.database.postgresql.default_tenant_id = test_tenant_id
```

## Future Improvements

1. **Test Data Fixtures**: Pre-populate common scenarios
2. **Performance Benchmarks**: Track test execution time
3. **Parallel Test Tenants**: Support concurrent test execution
4. **Test Coverage by Feature**: Ensure all features tested
5. **Synthetic Data Generation**: Create realistic test documents
