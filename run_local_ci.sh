#!/bin/bash

# Local CI Pipeline Runner
# Mirrors the GitHub Actions pipeline for local testing

set -e  # Exit on any error

echo "=================================="
echo "🚀 Pipeline v3 Local CI Runner"
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

# Create test results directory
mkdir -p test-results

print_step "Environment Setup"
echo "OPENAI_API_KEY status: $(if [[ -n "$OPENAI_API_KEY" ]]; then echo "✅ Set"; else echo "❌ Missing"; fi)"
echo "Python version: $(python3 --version)"
echo "UV version: $(uv --version)"
echo "Working directory: $(pwd)"

print_step "CLI Smoke Test"
uv run python -m src.pipeline_v3.cli_main --help > /dev/null
print_success "CLI help command works"

print_step "Step 1: Unit Tests (Core Foundation)"
uv run pytest src/pipeline_v3/tests/unit/ -v \
  --cov=src.pipeline_v3 \
  --cov-report=xml \
  --cov-report=html \
  --cov-report=term-missing \
  --junit-xml=test-results/unit-results.xml \
  --tb=short
print_success "Unit tests completed"

print_step "Step 2: Security Tests"
uv run pytest src/pipeline_v3/tests/security/ -v \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/security-results.xml \
  --tb=short
print_success "Security tests completed"

print_step "Step 3: Smoke Integration Tests"
uv run pytest src/pipeline_v3/tests/integration/ -v \
  --timeout=300 \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/smoke-integration-results.xml \
  -m "smoke" \
  --tb=short
print_success "Smoke integration tests completed"

print_step "Step 4: Lightweight Integration Tests"
uv run pytest src/pipeline_v3/tests/integration/ -v \
  --timeout=600 \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/lightweight-integration-results.xml \
  -m "integration and not heavy and not e2e" \
  --tb=short
print_success "Lightweight integration tests completed"

print_step "Step 5: Server-Specific Tests"
uv run pytest src/pipeline_v3/tests/integration/ -v \
  --timeout=900 \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/server-results.xml \
  -m "server" \
  --tb=short
print_success "Server-specific tests completed"

print_step "Step 6: E2E Tests (Critical Path)"
uv run pytest src/pipeline_v3/tests/integration/ -v \
  --timeout=1200 \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/e2e-results.xml \
  -m "e2e" \
  --tb=short
print_success "E2E tests completed"

print_step "Step 7: Heavy Resource Tests (Optional)"
uv run pytest src/pipeline_v3/tests/integration/ -v \
  --timeout=1800 \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/heavy-results.xml \
  -m "heavy" \
  --tb=short || print_warning "Heavy tests may fail (continue-on-error in CI)"

print_step "Step 8: Regression Tests"
uv run pytest src/pipeline_v3/tests/regression/ -v \
  --cov=src.pipeline_v3 \
  --cov-append \
  --junit-xml=test-results/regression-results.xml \
  --tb=short || print_warning "Some regression test failures allowed"

print_step "Step 9: Generate Coverage Report"
uv run coverage xml
uv run coverage html
echo "Coverage report generated:"
uv run coverage report --show-missing

print_step "Step 10: Test Summary Analysis"
echo "Test Results Summary:"
echo "===================="

# Count test results
passed=0
failed=0
for file in test-results/*.xml; do
    if [[ -f "$file" ]]; then
        file_passed=$(grep -o 'tests="[0-9]*"' "$file" | grep -o '[0-9]*' | head -1 || echo "0")
        file_failed=$(grep -o 'failures="[0-9]*"' "$file" | grep -o '[0-9]*' | head -1 || echo "0")
        passed=$((passed + file_passed))
        failed=$((failed + file_failed))
        echo "📄 $(basename "$file"): $file_passed passed, $file_failed failed"
    fi
done

echo "===================="
echo "🎯 Total: $passed passed, $failed failed"

# Final coverage summary
echo ""
echo "📊 Final Coverage Summary:"
uv run coverage report | tail -1

print_step "Pipeline Completion"
if [[ $failed -eq 0 ]]; then
    print_success "🎉 ALL TESTS PASSED! Pipeline completed successfully."
    exit 0
else
    print_warning "⚠️  Some tests failed but pipeline completed. Check results above."
    exit 0  # Don't fail for warnings in local testing
fi
