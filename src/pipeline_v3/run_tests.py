#!/usr/bin/env python3
"""
Test Runner for Pipeline v3

This script runs all test suites in the organized test structure.
Usage:
    python run_tests.py                 # Run all tests
    python run_tests.py --unit          # Run only unit tests
    python run_tests.py --integration   # Run only integration tests
    python run_tests.py --regression    # Run only regression tests
    python run_tests.py --quick         # Run quick verification
"""

import argparse
import subprocess
import sys
from pathlib import Path


def run_test_file(test_file_path: Path, args: list | None = None) -> bool:
    """Run a single test file and return success status."""
    # Use UV to run tests in the proper environment
    cmd = ["uv", "run", "python", str(test_file_path)]
    if args:
        cmd.extend(args)

    print(f"\n🧪 Running: {test_file_path.name}")
    print("-" * 50)

    try:
        result = subprocess.run(
            cmd,
            cwd=str(test_file_path.parent.parent.parent),  # Run from project root
            capture_output=False,  # Show output directly
            text=True,
            check=False,
        )

        if result.returncode == 0:
            print(f"✅ {test_file_path.name} PASSED")
            return True
        print(f"❌ {test_file_path.name} FAILED (exit code: {result.returncode})")
        return False

    except Exception as e:
        print(f"❌ {test_file_path.name} FAILED with exception: {e}")
        return False


def run_tests_in_directory(test_dir: Path, test_type: str) -> tuple[int, int]:
    """Run all test files in a directory."""
    test_files = list(test_dir.glob("test_*.py"))

    if not test_files:
        print(f"📂 No test files found in {test_type} directory")
        return 0, 0

    print(f"\n📂 Running {test_type} tests...")
    print("=" * 60)

    passed = 0
    total = len(test_files)

    for test_file in test_files:
        if run_test_file(test_file):
            passed += 1

    print(f"\n📊 {test_type.title()} Tests Summary: {passed}/{total} passed")
    return passed, total


def main():
    parser = argparse.ArgumentParser(description="Run Pipeline v3 tests")
    parser.add_argument("--unit", action="store_true", help="Run only unit tests")
    parser.add_argument("--integration", action="store_true", help="Run only integration tests")
    parser.add_argument("--regression", action="store_true", help="Run only regression tests")
    parser.add_argument("--quick", action="store_true", help="Run quick verification only")

    args = parser.parse_args()

    # Get test directories
    base_dir = Path(__file__).parent
    tests_dir = base_dir / "tests"

    total_passed = 0
    total_tests = 0

    print("🚀 Pipeline v3 Test Suite")
    print("=" * 60)

    if args.quick:
        # Run quick verification from regression tests
        regression_test = tests_dir / "regression" / "test_cli_simple_regression.py"
        if regression_test.exists():
            print("🏃‍♂️ Running Quick Verification...")
            success = run_test_file(regression_test, ["--quick"])
            sys.exit(0 if success else 1)
        else:
            print("❌ Quick test file not found")
            sys.exit(1)

    # Determine which test types to run
    run_unit = args.unit or not (args.integration or args.regression)
    run_integration = args.integration or not (args.unit or args.regression)
    run_regression = args.regression or not (args.unit or args.integration)

    # Run unit tests
    if run_unit:
        unit_dir = tests_dir / "unit"
        if unit_dir.exists():
            passed, total = run_tests_in_directory(unit_dir, "unit")
            total_passed += passed
            total_tests += total

    # Run integration tests
    if run_integration:
        integration_dir = tests_dir / "integration"
        if integration_dir.exists():
            passed, total = run_tests_in_directory(integration_dir, "integration")
            total_passed += passed
            total_tests += total

    # Run regression tests
    if run_regression:
        regression_dir = tests_dir / "regression"
        if regression_dir.exists():
            passed, total = run_tests_in_directory(regression_dir, "regression")
            total_passed += passed
            total_tests += total

    # Final summary
    print("\n" + "=" * 60)
    print("🎯 FINAL TEST RESULTS")
    print("=" * 60)

    if total_tests > 0:
        success_rate = total_passed / total_tests
        print(f"Total tests: {total_passed}/{total_tests} passed ({success_rate:.1%})")

        if success_rate >= 0.8:
            print("\n🎉 TEST SUITE PASSED!")
            print("✅ Pipeline v3 is ready for production use")
            sys.exit(0)
        else:
            print("\n❌ TEST SUITE FAILED")
            print(f"⚠️  Success rate ({success_rate:.1%}) below acceptable threshold (80%)")
            sys.exit(1)
    else:
        print("⚠️  No tests were run")
        sys.exit(1)


if __name__ == "__main__":
    main()
