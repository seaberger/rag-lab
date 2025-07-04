# CI/CD Guide for Pipeline v3

This guide covers the continuous integration and deployment setup for Pipeline v3.

## Overview

Pipeline v3 uses GitHub Actions for CI/CD with:
- Automated testing on every push and PR
- Code quality checks (linting, formatting, security)
- Coverage reporting with Codecov
- Multi-platform compatibility testing
- Pre-commit hooks for local quality assurance

## GitHub Actions Workflow

### Workflow File: `.github/workflows/pipeline_v3_ci.yml`

The CI pipeline runs on:
- Push to `main`, `develop`, or `feature/*` branches
- Pull requests to `main` or `develop`
- Only when Pipeline v3 files are modified

### Jobs

#### 1. Test Job
Runs the complete test suite with coverage reporting:
- Unit tests (must pass)
- Security tests (must pass)
- Integration tests (must pass for non-Qdrant tests)
- Search/Qdrant tests (allowed to fail until server mode)
- E2E tests (allowed to fail until server mode)
- Regression tests (allowed to fail)

#### 2. Lint Job
Runs code quality checks:
- `ruff` - Python linting
- `black` - Code formatting
- `isort` - Import sorting
- `mypy` - Type checking (non-blocking)

#### 3. Build Job
Creates distribution packages if tests and linting pass.

#### 4. Compatibility Job
Tests on multiple Python versions (3.11, 3.12) and platforms (Ubuntu, macOS).

## Pre-commit Hooks

Pre-commit hooks run automatically before each commit to catch issues early.

### Installation

```bash
# Install pre-commit
uv pip install pre-commit

# Install the git hooks
pre-commit install

# Run manually on all files
pre-commit run --all-files
```

### Configured Hooks

1. **File Formatting**
   - Remove trailing whitespace
   - Fix end-of-file newlines
   - Ensure LF line endings

2. **Code Quality**
   - `ruff` - Python linting with auto-fix
   - `ruff-format` - Python formatting

3. **Security**
   - `detect-secrets` - Prevent committing secrets
   - Check for private keys

4. **Validation**
   - YAML/JSON/TOML syntax checking
   - Large file detection (>1MB warning)
   - Merge conflict detection

### Skipping Hooks (Emergency Only)

```bash
# Skip pre-commit for emergency fixes
git commit --no-verify -m "Emergency fix"
```

## Coverage Reporting

### Current Status
- Target: 40% minimum coverage
- Current: ~12% (needs improvement)

### Viewing Coverage Locally

```bash
# Run tests with coverage
uv run pytest --cov=src.pipeline_v3 --cov-report=html

# Open coverage report
open htmlcov/index.html
```

### Codecov Integration

Coverage reports are automatically uploaded to Codecov on successful test runs. Add your Codecov token as a GitHub secret:

1. Go to Settings → Secrets → Actions
2. Add `CODECOV_TOKEN` with your token from codecov.io

## Running CI Locally

### Simulate GitHub Actions

```bash
# Install act (GitHub Actions locally)
brew install act  # macOS
# or
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | bash  # Linux

# Run the workflow
act push
```

### Manual Test Suite

```bash
# Run the same test groups as CI
cd src/pipeline_v3

# Unit tests
uv run pytest tests/unit/ -v

# Security tests
uv run pytest tests/security/ -v

# Integration tests (non-Qdrant)
uv run pytest tests/integration/ -k "not search and not vector and not e2e" -v

# All tests with coverage
uv run pytest tests/ --cov=src.pipeline_v3 --cov-report=term-missing
```

## Troubleshooting CI Failures

### Common Issues

1. **Import Errors**
   - Ensure all imports use absolute paths
   - Check that `__init__.py` files exist

2. **Test Timeouts**
   - E2E tests have 600s timeout
   - Consider using the queue system for long operations

3. **Resource Conflicts**
   - Tests use cleanup fixtures to avoid conflicts
   - Qdrant tests run serially

4. **Coverage Drops**
   - Add tests for new code
   - Focus on high-value unit tests

### Debugging Failed Workflows

1. Check the workflow logs in GitHub Actions tab
2. Download test artifacts for detailed results
3. Run failing tests locally with verbose output:
   ```bash
   uv run pytest path/to/test.py::TestClass::test_method -vvs
   ```

## Best Practices

### Before Pushing

1. Run pre-commit hooks: `pre-commit run --all-files`
2. Run quick tests: `uv run pytest tests/unit/ -x`
3. Check coverage: `uv run pytest --cov=src.pipeline_v3 --cov-report=term`

### Writing Tests

1. Use descriptive test names
2. Group related tests in classes
3. Use fixtures for common setup
4. Mock external dependencies
5. Test both success and failure cases

### CI-Friendly Code

1. Avoid hardcoded paths
2. Use environment variables for configuration
3. Handle missing dependencies gracefully
4. Keep tests isolated and independent

## Future Improvements

1. **Increase Coverage** (Issue #17)
   - Target: 70% coverage
   - Focus on integration tests

2. **Qdrant Server Mode** (Issue #71)
   - Will resolve E2E test failures
   - Enable full parallel testing

3. **Performance Testing**
   - Add benchmarks for search performance
   - Monitor processing times

4. **Deployment Pipeline**
   - Docker container builds
   - Automated releases
   - Version tagging

## Related Documentation

- [Testing Guide](../tests/README.md)
- [Development Status](../DEVELOPMENT_STATUS.md)
- [Architecture](./architecture.md)
