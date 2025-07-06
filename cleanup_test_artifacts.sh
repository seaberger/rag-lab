#!/bin/bash

# Cleanup script for test artifacts and temporary files
# Run this periodically to keep the repository clean

echo "🧹 Cleaning up test artifacts..."

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to safely remove files/directories
safe_remove() {
    if [ -e "$1" ]; then
        rm -rf "$1"
        echo -e "${GREEN}✓${NC} Removed: $1"
    fi
}

# 1. Clean test result files in root
echo -e "\n${YELLOW}Cleaning test result files...${NC}"
safe_remove "test-report.html"
safe_remove "test-results.json"
safe_remove "bandit-report.json"
safe_remove "processing_report.json"
safe_remove "coverage.xml"

# 2. Clean test-results directory but keep .gitkeep if it exists
echo -e "\n${YELLOW}Cleaning test-results directory...${NC}"
if [ -d "test-results" ]; then
    find test-results -type f -name "*.xml" -delete
    echo -e "${GREEN}✓${NC} Cleaned test-results/*.xml files"
fi

# 3. Clean htmlcov directory
echo -e "\n${YELLOW}Cleaning coverage reports...${NC}"
safe_remove "htmlcov"

# 4. Clean test_data directory (be careful here)
echo -e "\n${YELLOW}Cleaning test_data directory...${NC}"
if [ -d "test_data" ]; then
    # Count before cleaning
    count=$(find test_data -type d -name "test_env_*" | wc -l)

    if [ $count -gt 0 ]; then
        echo "Found $count test environment directories"
        read -p "Remove all test_env_* directories? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            find test_data -type d -name "test_env_*" -exec rm -rf {} + 2>/dev/null
            find test_data -type d -name "env*" -exec rm -rf {} + 2>/dev/null
            echo -e "${GREEN}✓${NC} Removed test environment directories"
        else
            echo "Skipped test_data cleanup"
        fi
    fi
fi

# 5. Clean Python cache files
echo -e "\n${YELLOW}Cleaning Python cache files...${NC}"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
find . -type f -name "*.pyo" -delete 2>/dev/null
find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null
echo -e "${GREEN}✓${NC} Cleaned Python cache files"

# 6. Clean other test artifacts
echo -e "\n${YELLOW}Cleaning other test artifacts...${NC}"
safe_remove ".coverage"
safe_remove ".coverage.*"

# 7. Clean up empty directories in test_data
if [ -d "test_data" ]; then
    find test_data -type d -empty -delete 2>/dev/null
    echo -e "${GREEN}✓${NC} Removed empty directories"
fi

echo -e "\n${GREEN}✅ Cleanup complete!${NC}"

# Show disk space saved
if command -v du &> /dev/null; then
    echo -e "\n${YELLOW}Disk space summary:${NC}"
    du -sh . 2>/dev/null | cut -f1 | xargs echo "Current repository size:"
fi
