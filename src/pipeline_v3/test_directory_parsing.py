#!/usr/bin/env python3
"""
Test script for enhanced directory parsing features (Issue #33).
Demonstrates new CLI options for directory traversal, filtering, and Office document support.
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd):
    """Run a CLI command and display the output."""
    print(f"\n{'='*60}")
    print(f"🚀 Running: {' '.join(cmd)}")
    print('='*60)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def main():
    """Test various directory parsing scenarios."""
    print("🧪 Testing Enhanced Directory Parsing Features (Issue #33)")
    print("=" * 60)
    
    # Base command
    base_cmd = ["uv", "run", "python", "-m", "src.pipeline_v3.cli_main", "add"]
    
    # Test 1: Dry run with recursive directory scanning
    print("\n📋 Test 1: Dry run with recursive directory scanning")
    cmd = base_cmd + ["data/sample_docs", "--recursive", "--dry-run"]
    run_command(cmd)
    
    # Test 2: Include only specific file types
    print("\n📋 Test 2: Include only PDF and DOCX files")
    cmd = base_cmd + ["data/sample_docs", "--recursive", "--include-pattern", "*.pdf", "--include-pattern", "*.docx", "--dry-run"]
    run_command(cmd)
    
    # Test 3: Exclude patterns
    print("\n📋 Test 3: Exclude test directories and temp files")
    cmd = base_cmd + ["data", "--recursive", "--exclude-pattern", "**/test/**", "--exclude-pattern", "*.tmp", "--dry-run"]
    run_command(cmd)
    
    # Test 4: Complex filtering - include PDFs but exclude certain directories
    print("\n📋 Test 4: Include PDFs but exclude lmc_docs directory")
    cmd = base_cmd + ["data", "--recursive", "--include-pattern", "*.pdf", "--exclude-pattern", "**/lmc_docs/**", "--dry-run"]
    run_command(cmd)
    
    # Test 5: Non-recursive directory scan (immediate children only)
    print("\n📋 Test 5: Non-recursive scan of data directory")
    cmd = base_cmd + ["data", "--dry-run"]
    run_command(cmd)
    
    # Test 6: Office document support
    print("\n📋 Test 6: Find all Office documents")
    cmd = base_cmd + ["data", "--recursive", "--include-pattern", "*.docx", "--include-pattern", "*.pptx", "--dry-run"]
    run_command(cmd)
    
    # Test 7: Multiple directories
    print("\n📋 Test 7: Scan multiple directories")
    cmd = base_cmd + ["data/sample_docs", "data/lmc_docs/datasheets", "--dry-run"]
    run_command(cmd)
    
    # Test 8: Glob pattern with filtering
    print("\n📋 Test 8: Glob pattern with exclude")
    cmd = base_cmd + ["data/**/*.pdf", "--exclude-pattern", "*COHR*", "--dry-run"]
    run_command(cmd)
    
    print("\n✅ All tests completed!")
    print("\n💡 Tips:")
    print("  • Use --dry-run to preview files before processing")
    print("  • Combine --include-pattern and --exclude-pattern for precise control")
    print("  • Office documents (.docx, .pptx) are now supported")
    print("  • Use --recursive to scan subdirectories")
    print("  • Multiple patterns can be specified by repeating the option")

if __name__ == "__main__":
    main()