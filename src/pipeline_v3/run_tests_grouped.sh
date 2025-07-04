#!/bin/bash
# Run tests in groups to avoid resource conflicts

echo "Running Pipeline v3 tests in groups to avoid resource conflicts..."
echo "=============================================================="

# Exit on any failure
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to run a test group
run_test_group() {
    local group_name=$1
    local test_command=$2

    echo -e "\n${YELLOW}Running $group_name tests...${NC}"
    if eval "$test_command"; then
        echo -e "${GREEN}✓ $group_name tests passed${NC}"
    else
        echo -e "${RED}✗ $group_name tests failed${NC}"
        exit 1
    fi

    # Delay between groups
    echo "Waiting for resources to clean up..."
    sleep 2
}

# Change to script directory
cd "$(dirname "$0")"

# 1. Run unit tests (no external resources)
run_test_group "Unit" \
    "uv run pytest tests/unit/ -v -m 'unit or not integration' --cov=src.pipeline_v3"

# 2. Run integration tests WITHOUT Qdrant
run_test_group "Integration (non-Qdrant)" \
    "uv run pytest tests/integration/ -v -k 'not search and not vector and not e2e' --cov-append"

# 3. Run search/Qdrant tests serially
run_test_group "Search/Qdrant" \
    "uv run pytest tests/integration/test_search_integration.py -v --cov-append"

# 4. Run E2E tests serially with longer timeout
run_test_group "E2E" \
    "uv run pytest tests/integration/test_e2e_integration.py -v --timeout=600 --cov-append"

# 5. Run regression tests
run_test_group "Regression" \
    "uv run pytest tests/regression/ -v --cov-append"

# 6. Run security tests
run_test_group "Security" \
    "uv run pytest tests/security/ -v -m security --cov-append"

# Show combined coverage report
echo -e "\n${YELLOW}Combined Coverage Report:${NC}"
uv run coverage report --show-missing

echo -e "\n${GREEN}All test groups completed successfully!${NC}"
