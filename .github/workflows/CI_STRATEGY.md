# CI/CD Strategy

## Overview

We use a two-tier CI/CD strategy to balance thorough testing with OpenAI API cost management:

1. **Quick CI** - Runs on every commit/PR
2. **Comprehensive CI** - Runs only when explicitly triggered

## Quick CI (Default)

**File:** `quick-ci.yml`
**Triggers:** Every push, every PR
**Cost:** Minimal - single test run
**Duration:** ~5-10 minutes

Includes:
- All unit tests
- Security tests
- Integration tests (excluding heavy/regression)
- Code quality checks (ruff, formatting)
- Basic security scanning

## Comprehensive CI (On-Demand)

**File:** `comprehensive-ci.yml`
**Triggers:** Manual only
**Cost:** High - multiple test stages (~$0.50-$2.00)
**Duration:** ~30-45 minutes

### How to Trigger Comprehensive CI:

1. **For Pull Requests:**
   - Add the `comprehensive-ci` label to your PR
   - Tests will run automatically when label is added
   - Remove and re-add label to re-run

2. **Manual Trigger:**
   - Go to Actions tab in GitHub
   - Select "Comprehensive CI" workflow
   - Click "Run workflow"
   - Enter reason (optional)

3. **Automatic on Release:**
   - Push a tag starting with `v` (e.g., `v1.0.0`)
   - Comprehensive tests run automatically

### Test Stages in Comprehensive CI:

1. Unit tests
2. Security tests
3. Smoke integration tests
4. Lightweight integration tests
5. Server-specific tests
6. E2E tests
7. Heavy resource tests
8. Regression tests
9. Full coverage reporting

## Workflow Process

### Normal Development:
```
Push commit → Quick CI runs → Get fast feedback
```

### Ready to Merge:
```
1. PR passes Quick CI
2. Add 'comprehensive-ci' label to PR
3. Comprehensive CI runs (once)
4. Review results
5. Merge if passing
```

### Release Process:
```
1. Tag release (e.g., git tag v1.0.0)
2. Push tag
3. Comprehensive CI runs automatically
4. Release if passing
```

## Cost Management

- Quick CI minimizes API calls by running all tests in one pytest command
- Comprehensive CI runs tests in stages, which may call APIs multiple times
- Use comprehensive CI judiciously - only for final validation before merge/release

## Local Testing

Before triggering CI:
- Run `./run_local_quickci.sh` for fast local validation
- Run `./run_local_ci.sh` for comprehensive local testing (if needed)
