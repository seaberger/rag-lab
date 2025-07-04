# Pipeline v3 Test Suite 🧪

This directory contains the organized test suite for Pipeline v3, following software testing best practices.

## 📁 Test Organization

```
tests/
├── unit/                              # Unit tests - test individual components
│   ├── __init__.py
│   ├── test_cli.py                   # Advanced CLI component tests (requires full deps)
│   └── test_cli_simple.py            # Basic CLI functionality tests
├── integration/                       # Integration tests - test component interactions
│   ├── __init__.py
│   ├── test_integration.py           # Full pipeline integration tests
│   └── test_quick_integration.py     # Quick integration verification
├── regression/                        # Regression tests - prevent bugs from returning
│   ├── __init__.py
│   ├── test_cli_regression.py        # Comprehensive pytest-based regression tests
│   └── test_cli_simple_regression.py # Simple regression tests (no external deps)
├── advanced/                          # Advanced tests (full environment required)
│   └── __init__.py                   # Complex tests requiring all dependencies
├── __init__.py
└── README.md                         # This file
```

## 🚀 Running Tests

### ⚠️ IMPORTANT: UV Environment Required
**All tests MUST be run using the UV environment to ensure proper dependencies and Python setup.**

### Quick Start
```bash
# Run all tests (using UV environment)
uv run python run_tests.py

# Run specific test categories
uv run python run_tests.py --unit          # Unit tests only
uv run python run_tests.py --integration   # Integration tests only
uv run python run_tests.py --regression    # Regression tests only

# Quick verification (fast check)
uv run python run_tests.py --quick
```

### Individual Test Files
```bash
# Run a specific test file (using UV environment)
uv run python tests/unit/test_cli_simple.py
uv run python tests/regression/test_cli_simple_regression.py

# Run regression tests with quick mode
uv run python tests/regression/test_cli_simple_regression.py --quick
```

## 📋 Test Categories

### 🔧 Unit Tests (`unit/`)
- **Purpose**: Test individual functions and components in isolation
- **Speed**: Fast (seconds)
- **Focus**: Single component functionality
- **Examples**: CLI argument parsing, help command output

### 🔗 Integration Tests (`integration/`)
- **Purpose**: Test multiple components working together
- **Speed**: Medium (minutes)
- **Focus**: Component interactions and data flow
- **Examples**: Full document processing pipeline, database connections

### 🛡️ Regression Tests (`regression/`)
- **Purpose**: Ensure previously fixed bugs don't return
- **Speed**: Medium to slow (minutes)
- **Focus**: Known bug scenarios and edge cases
- **Examples**: Error handling, exit codes, graceful degradation

## 📊 Test Coverage

### Current Test Coverage
- ✅ **CLI Command Interface**: All commands and subcommands
- ✅ **Error Handling**: Invalid arguments, missing dependencies
- ✅ **Exit Codes**: Proper exit codes for all scenarios
- ✅ **Help System**: Comprehensive help command testing
- ✅ **Configuration**: Bad config file handling
- ✅ **Interruption**: Ctrl-C handling
- ✅ **Logging**: Traceback separation and log file creation

### Test Results Format
```
🧪 Testing: Normal help command
   ✅ PASSED
     Exit code: 0 ✓
     Contains expected text ✓

📊 TEST RESULTS SUMMARY
Tests passed: 12/12 (100.0%)
🎉 CLI Backward-Compatibility Tests PASSED!
```

## 🔧 Test Configuration

### Logging
- **Test logs**: Automatically created with timestamps (e.g., `test_results_20241230_160328.log`)
- **Console output**: Real-time test progress
- **Log separation**: Test logs separate from production logs

### Exit Codes
Tests verify proper exit codes for different scenarios:
- `0`: Success
- `1`: General error
- `126`: Dependency error
- `128`: Invalid argument error
- `130`: Keyboard interrupt (Ctrl-C)

## 🎯 Best Practices

### ✅ What Our Tests Do Well
1. **Separation of Concerns**: Tests organized by purpose and scope
2. **Real Subprocess Testing**: Tests actual CLI execution, not just imports
3. **Comprehensive Error Testing**: Tests both success and failure scenarios
4. **Exit Code Verification**: Ensures proper error signaling
5. **Graceful Degradation Testing**: Verifies resilient behavior
6. **Logging Verification**: Ensures proper log/console separation

### 🚀 Running in CI/CD
```bash
# In CI/CD pipeline (ensure UV is available)
uv run python run_tests.py --regression  # Focus on critical functionality
uv run python run_tests.py --quick       # Fast verification
```

## ⚙️ UV Environment Setup

### Why UV is Required
- **Dependency Management**: Ensures all required packages are available
- **Python Version**: Uses the correct Python interpreter
- **Environment Isolation**: Prevents conflicts with system packages
- **Reproducible Results**: Same environment across different machines

### Setting Up UV
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify UV installation
uv --version

# Install project dependencies
uv sync

# Run tests
uv run python run_tests.py
```

### ⚠️ Common UV Issues
- **UV not found**: Install UV or ensure it's in your PATH
- **Dependencies missing**: Run `uv sync` to install dependencies
- **Wrong Python version**: UV will use the project's specified Python version

## 📈 Adding New Tests

### For New Features
1. **Add unit tests** in `unit/` for individual functions
2. **Add integration tests** in `integration/` for feature workflows
3. **Update regression tests** in `regression/` for critical paths

### Test File Naming
- `test_*.py` - All test files must start with `test_`
- Use descriptive names: `test_cli_authentication.py`
- Include test type in path: `unit/test_auth.py`

### Test Function Naming
```python
def test_normal_help_command():        # ✅ Descriptive
def test_invalid_command_handling():   # ✅ Clear purpose
def test_auth():                       # ❌ Too vague
```

## 🐛 Debugging Failed Tests

### Check Test Logs
```bash
# Test logs are automatically created with timestamps
ls test_results_*.log
tail -f test_results_20241230_160328.log
```

### Run Individual Tests
```bash
# Run specific failing test (using UV)
uv run python tests/unit/test_cli_simple.py

# Run with verbose output (using UV)
uv run python tests/regression/test_cli_simple_regression.py
```

### Common Issues
1. **Import Errors**: Check paths in moved test files
2. **Missing Dependencies**: Ensure `uv` environment is activated
3. **Working Directory**: Tests run from project root
4. **File Paths**: Use relative paths from test file location

## 🎉 Success Criteria

A test suite passes when:
- **Success Rate**: ≥80% of tests pass
- **Exit Codes**: Proper codes for all scenarios
- **Error Handling**: Graceful degradation works
- **Help System**: All help commands functional
- **Logging**: Proper separation maintained

---

**Remember**: Good tests are investments in code quality and development velocity! 🚀
