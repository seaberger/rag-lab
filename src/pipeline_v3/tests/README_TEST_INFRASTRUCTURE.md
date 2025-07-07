# Test Infrastructure for Pipeline v3

This document explains the test infrastructure for end-to-end testing with PostgreSQL and Qdrant.

## Overview

Our test infrastructure supports multiple environments:
- **Local Development**: Uses .env file or Docker defaults
- **GitHub Actions**: Uses GitHub secrets for credentials
- **Docker CI**: Uses container-specific settings

## Database Credential Management

### Local Development

For local development, credentials are loaded in this priority order:

1. **Environment Variables**: If `POSTGRES_PASSWORD` is set
2. **.env.postgres File**: PostgreSQL-specific configuration (recommended)
3. **.env File**: Main environment file
4. **Docker Defaults**: Uses `postgres` as password for local Docker containers

Example `.env.postgres` file:
```bash
POSTGRES_PASSWORD=your_local_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DATABASE=rag_lab
POSTGRES_USER=postgres
```

Or add to main `.env` file:
```bash
# Other app config...
OPENAI_API_KEY=sk-...

# PostgreSQL config
POSTGRES_PASSWORD=your_local_password
```

### GitHub Actions

In GitHub Actions, the PostgreSQL password is stored as a repository secret:
- Secret Name: `POSTGRES_PASSWORD`
- Used by: CI workflow for PostgreSQL service and test execution

The CI workflow:
1. Starts PostgreSQL service with the secret
2. Passes the secret to test execution environment
3. Tests use the credential manager to access it

### Test Database Setup

The test infrastructure automatically:

1. **Checks if databases are running**
   - PostgreSQL on port 5432
   - Qdrant on port 6333

2. **Starts databases if needed**
   - Tries Docker first (preferred)
   - Falls back to native installations
   - In GitHub Actions, uses service containers

3. **Creates test tenant**
   - Name: `test_tenant`
   - Purpose: Isolated testing environment
   - Cleanup: Data removed after test session

## Usage in Tests

### Basic Setup

```python
import pytest
from src.pipeline_v3.tests.fixtures.test_database_setup import (
    test_databases, test_tenant_id, test_tenant_config
)

def test_with_real_database(test_tenant_config):
    """Test using real PostgreSQL and Qdrant."""
    # test_tenant_config has the test tenant ID configured
    pipeline = EnhancedPipeline(test_tenant_config)
    # ... run your tests
```

### Manual Database Management

```python
from src.pipeline_v3.tests.fixtures.test_database_setup import TestDatabaseManager

# Create manager
manager = TestDatabaseManager()

# Ensure databases are ready
success, tenant_info = manager.ensure_databases_ready()
if success:
    tenant_id = tenant_info['tenant_id']
    # Run tests with tenant_id

# Cleanup when done
manager.cleanup_test_tenant()
```

## Running Tests Locally

### With Docker (Recommended)

```bash
# Start databases
docker-compose up -d postgres qdrant

# Run tests
./run_local_quickci.sh
```

### With Manual Setup

1. Ensure PostgreSQL is running and accessible
2. Ensure Qdrant is running on port 6333
3. Set up `.env` file with credentials
4. Run tests:
```bash
pytest src/pipeline_v3/tests/integration/
```

## Troubleshooting

### PostgreSQL Connection Issues

1. **Password Authentication Failed**
   - Check `.env` file exists and has `POSTGRES_PASSWORD`
   - Verify PostgreSQL is configured to accept password auth
   - Try connecting manually: `psql -h localhost -U postgres -d rag_lab`

2. **Connection Refused**
   - Check PostgreSQL is running: `lsof -i :5432`
   - Start with Docker: `docker start rag-lab-postgres`
   - Or native: `pg_ctl start` or `brew services start postgresql`

### Qdrant Connection Issues

1. **Connection Refused**
   - Check Qdrant is running: `lsof -i :6333`
   - Start with Docker: `docker start rag-lab-qdrant`
   - Or script: `./scripts/qdrant_server.sh start`

### Test Tenant Issues

1. **Tenant Already Exists**
   - Tests will reuse existing test tenant
   - To force recreation: Delete tenant manually first

2. **Cleanup Failed**
   - Check PostgreSQL logs for permission issues
   - Manually clean with: `DELETE FROM schema.table WHERE tenant_id = 'test_tenant_uuid'`

## CI/CD Configuration

### GitHub Actions Setup

1. **Add Secret**: Settings → Secrets → Actions → New repository secret
   - Name: `POSTGRES_PASSWORD`
   - Value: Your secure password

2. **Workflow Configuration**: Already configured in `.github/workflows/ci.yml`
   - PostgreSQL service uses the secret
   - Test job passes secret to test environment

### Local CI Simulation

To simulate CI environment locally:

```bash
# Set CI environment variables
export CI=true
export POSTGRES_PASSWORD=your_password

# Run tests
./run_local_quickci.sh
```

## Best Practices

1. **Never commit passwords**: Use environment variables or .env files
2. **Clean up test data**: Tests should clean up after themselves
3. **Use test tenant**: Never run tests against production data
4. **Check database state**: Ensure databases are ready before tests
5. **Handle failures gracefully**: Tests should not leave database in bad state

## Future Improvements

1. **Test data fixtures**: Pre-populate common test scenarios
2. **Parallel test support**: Multiple test tenants for parallel execution
3. **Performance monitoring**: Track test database performance
4. **Automatic cleanup**: Scheduled cleanup of old test data
