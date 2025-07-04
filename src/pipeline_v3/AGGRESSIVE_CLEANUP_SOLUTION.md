# Aggressive Cleanup Solution for Test Conflicts

## Root Cause Analysis

After investigation, the test failures are **NOT** due to test ordering but rather:

1. **Qdrant File Locks**: Local Qdrant uses file-based storage that doesn't handle rapid creation/deletion well
2. **SQLite Lock Contention**: Multiple tests accessing keyword index and registry databases
3. **Async Operation Overlap**: Vector indexing continues after tests "complete"
4. **OS File Handle Delays**: File system operations have inherent delays

## Solutions Implemented

### 1. Automatic Cleanup Fixtures

Created `tests/fixtures/cleanup.py` with:
- `cleanup_between_tests`: Runs after each test (0.1s async delay + GC)
- `cleanup_between_test_classes`: Runs between test classes (0.5s delay)
- `force_cleanup`: Manual cleanup for specific tests

### 2. Grouped Test Execution

Created `run_tests_grouped.sh` that runs tests in isolated groups:
1. Unit tests (no external resources)
2. Integration tests without Qdrant
3. Search/Qdrant tests (serially)
4. E2E tests (with extended timeout)
5. Regression tests
6. Security tests

Each group has a 2-second delay to ensure complete cleanup.

### 3. Optimized pytest Configuration

Created `pytest_optimized.ini` with:
- Disabled parallel execution by default
- Increased timeouts for slow operations
- Proper warning filters
- Clear test markers for grouping

## How to Use

### Option 1: Run All Tests with Grouping (Recommended)
```bash
cd src/pipeline_v3
./run_tests_grouped.sh
```

### Option 2: Run Specific Test Groups
```bash
# Fast unit tests only
uv run pytest tests/unit/ -v -m unit

# Integration without Qdrant
uv run pytest tests/integration/ -v -k "not qdrant"

# Qdrant tests serially
uv run pytest tests/ -v -m qdrant --maxfail=1
```

### Option 3: Use Aggressive Cleanup Config
```bash
uv run pytest -c pytest_optimized.ini tests/
```

## Why This Works

1. **Resource Isolation**: Tests that use the same resources don't run concurrently
2. **Cleanup Time**: Delays allow file handles and locks to be released
3. **Serial Execution**: Qdrant tests run one at a time
4. **Garbage Collection**: Forces Python to release resources

## Future Improvements

### Short Term
- Add `@pytest.mark.qdrant` to all Qdrant-using tests
- Increase delays if conflicts persist
- Consider process isolation for problematic tests

### Long Term (Issue #71)
- Migrate to Qdrant server mode
- Use Docker containers for test isolation
- Implement true parallel testing

## Key Insight

**Test ordering plugins won't help** because the issue isn't dependencies between tests, but rather:
- Multiple tests trying to acquire the same file locks
- Async operations not completing before the next test starts
- OS-level file system delays

The solution is **resource isolation and cleanup delays**, not execution order.
