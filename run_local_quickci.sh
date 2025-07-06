#!/bin/bash

# Local Quick CI Pipeline Runner
# Mirrors the GitHub Actions quick CI pipeline for rapid local testing

set -e  # Exit on any error

echo "=================================="
echo "🚀 Quick CI - Local Runner"
echo "=================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print step headers
print_step() {
    echo -e "\n${BLUE}📋 $1${NC}"
    echo "----------------------------------------"
}

# Function to print success
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Function to print warning
print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Track overall status
TESTS_PASSED=true
QUALITY_PASSED=true
SECURITY_PASSED=true

# Create test results directory
mkdir -p test-results

# Set PYTHONPATH for relative imports
export PYTHONPATH="${PWD}/src/pipeline_v3:${PYTHONPATH}"

print_step "Environment Check"
echo "OPENAI_API_KEY: $(if [[ -n "$OPENAI_API_KEY" ]]; then echo "✅ Set"; else echo "❌ Missing"; fi)"
echo "Python: $(python3 --version)"
echo "UV: $(uv --version)"
echo "Working directory: $(pwd)"

# Quick smoke test
print_step "Quick Smoke Test"
if uv run python -m src.pipeline_v3.cli_main --help > /dev/null 2>&1; then
    print_success "CLI loads successfully"
else
    print_error "CLI failed to load"
    exit 1
fi

# Import verification
if uv run python -c "
from src.pipeline_v3.core.registry import DocumentRegistry
from src.pipeline_v3.storage.keyword_index import BM25Index
print('Core modules imported successfully')
" > /dev/null 2>&1; then
    print_success "Core modules import successfully"
else
    print_error "Core module imports failed"
    exit 1
fi

print_step "Running All Tests (including Security)"
echo "This combines unit, security, and integration tests in one run"
echo "Excluding heavy tests and regression tests for speed"

set +e  # Don't exit on test failures
uv run pytest \
    --cov=src/pipeline_v3 \
    --cov-report=xml \
    --cov-report=html \
    --cov-report=term-missing \
    --cov-fail-under=10 \
    --html=test-report.html \
    --self-contained-html \
    --json-report \
    --json-report-file=test-results.json \
    -k "not test_cli_regression" \
    --maxfail=5 \
    --timeout=300 \
    --ignore=src/pipeline_v3/tests/archive \
    src/pipeline_v3/tests/ \
    -v

TEST_EXIT_CODE=$?
set -e

if [ $TEST_EXIT_CODE -ne 0 ]; then
    TESTS_PASSED=false
    print_warning "Some tests failed (exit code: $TEST_EXIT_CODE)"
else
    print_success "All tests passed!"
fi

# Parse test results if available
if [ -f "test-results.json" ]; then
    echo ""
    echo "Test Summary:"
    python3 -c "
import json
with open('test-results.json', 'r') as f:
    data = json.load(f)
    summary = data.get('summary', {})
    print(f\"  Total: {summary.get('total', 0)}\")
    print(f\"  Passed: {summary.get('passed', 0)}\")
    print(f\"  Failed: {summary.get('failed', 0)}\")
    print(f\"  Skipped: {summary.get('skipped', 0)}\")
    "
fi

print_step "Code Quality Checks"

# Ruff linting
echo "Running ruff linting..."
if uv run ruff check . --output-format=concise --extend-exclude="*.ipynb" > /dev/null 2>&1; then
    print_success "No linting issues found"
else
    QUALITY_PASSED=false
    print_warning "Linting issues detected - run 'ruff check .' for details"
fi

# Ruff formatting
echo "Checking code formatting..."
if uv run ruff format --check . > /dev/null 2>&1; then
    print_success "Code formatting is correct"
else
    QUALITY_PASSED=false
    print_warning "Formatting issues found - run 'ruff format .' to fix"
fi

# Type checking (optional - often has many warnings)
echo "Running type checking..."
if command -v mypy &> /dev/null; then
    if uv run mypy src/pipeline_v3 --ignore-missing-imports > /dev/null 2>&1; then
        print_success "No type errors found"
    else
        print_warning "Type errors detected (non-blocking) - run 'mypy src/pipeline_v3' for details"
    fi
else
    print_warning "mypy not installed - skipping type checking"
fi

print_step "Security Scanning"

# Check for security tests specifically
echo "Security test results:"
if [ -f "test-results.json" ]; then
    python3 -c "
import json
with open('test-results.json', 'r') as f:
    data = json.load(f)
    security_tests = [t for t in data.get('tests', []) if 'security' in t.get('nodeid', '').lower()]
    print(f'  Security tests run: {len(security_tests)}')
    failed_security = [t for t in security_tests if t.get('outcome') == 'failed']
    if failed_security:
        print(f'  ⚠️ Failed security tests: {len(failed_security)}')
    else:
        print('  ✅ All security tests passed')
    "
fi

# Optional: Run bandit if installed
if command -v bandit &> /dev/null; then
    echo "Running bandit security scan..."
    if uv run bandit -r src/pipeline_v3 -f json -o bandit-report.json --skip B101,B608 -x "*/tests/*,*/legacy_backup/*" > /dev/null 2>&1; then
        print_success "No security issues found by bandit"
    else
        SECURITY_PASSED=false
        print_warning "Potential security issues detected - check bandit-report.json"
    fi
else
    print_warning "bandit not installed - skipping additional security scan"
fi

print_step "Coverage Report"
if [ -f "coverage.xml" ]; then
    echo "Coverage summary:"
    uv run coverage report | tail -5
else
    print_warning "No coverage report generated"
fi

print_step "Quick CI Summary"
echo "===================="

# Determine overall status
OVERALL_STATUS="PASSED"
if [ "$TESTS_PASSED" = false ] || [ "$QUALITY_PASSED" = false ] || [ "$SECURITY_PASSED" = false ]; then
    OVERALL_STATUS="FAILED"
fi

echo "Test Suite: $(if [ "$TESTS_PASSED" = true ]; then echo "✅ PASSED"; else echo "❌ FAILED"; fi)"
echo "Code Quality: $(if [ "$QUALITY_PASSED" = true ]; then echo "✅ PASSED"; else echo "⚠️ WARNINGS"; fi)"
echo "Security: $(if [ "$SECURITY_PASSED" = true ]; then echo "✅ PASSED"; else echo "⚠️ WARNINGS"; fi)"
echo ""

if [ "$OVERALL_STATUS" = "PASSED" ]; then
    print_success "🎉 Quick CI PASSED! (Total time: $SECONDS seconds)"
    echo ""
    echo "For more thorough testing, run: ./run_local_ci.sh"
    exit 0
else
    print_warning "⚠️ Quick CI completed with issues (Total time: $SECONDS seconds)"
    echo ""
    echo "Fix the issues above and re-run, or use ./run_local_ci.sh for detailed diagnostics"
    exit 1
fi
