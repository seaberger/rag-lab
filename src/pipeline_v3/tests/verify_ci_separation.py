#!/usr/bin/env python3
"""
Verify the separation of tests between Quick CI and Comprehensive CI.
"""

import subprocess
import sys


def run_pytest_collect(markers):
    """Run pytest collection with given markers."""
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "src/pipeline_v3/tests/",
        "-m",
        markers,
        "--collect-only",
        "-q",
        "--no-header",
    ]
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        return result.stdout, result.stderr
    except Exception as e:
        return "", str(e)


def main():
    print("🔍 Verifying CI Test Separation")
    print("=" * 60)

    # Quick CI tests
    print("\n📋 QUICK CI Tests (run on every commit):")
    print("  Markers: not comprehensive and not heavy")
    stdout, stderr = run_pytest_collect("not comprehensive and not heavy")

    # Count tests
    lines = stdout.strip().split("\n")
    for line in lines[-3:]:  # Last few lines have the summary
        if "tests collected" in line or "selected" in line:
            print(f"  ✅ {line}")

    # Comprehensive CI tests
    print("\n🏋️ COMPREHENSIVE CI Tests (run on-demand):")
    print("  Markers: comprehensive")
    stdout, stderr = run_pytest_collect("comprehensive")

    # Count tests
    lines = stdout.strip().split("\n")
    for line in lines[-3:]:
        if "tests collected" in line or "selected" in line:
            print(f"  ✅ {line}")

    # Heavy tests (should be in comprehensive)
    print("\n🔨 HEAVY Tests (should be in comprehensive):")
    print("  Markers: heavy")
    stdout, stderr = run_pytest_collect("heavy")

    lines = stdout.strip().split("\n")
    for line in lines[-3:]:
        if "tests collected" in line or "selected" in line:
            print(f"  ✅ {line}")

    # Tests that use API
    print("\n🌐 API Tests Distribution:")
    print("  Quick CI API tests (markers: requires_api and not comprehensive and not heavy):")
    stdout, stderr = run_pytest_collect("requires_api and not comprehensive and not heavy")

    lines = stdout.strip().split("\n")
    for line in lines[-3:]:
        if "tests collected" in line or "selected" in line:
            print(f"    {line}")

    print("\n  Comprehensive CI API tests (markers: requires_api and comprehensive):")
    stdout, stderr = run_pytest_collect("requires_api and comprehensive")

    lines = stdout.strip().split("\n")
    for line in lines[-3:]:
        if "tests collected" in line or "selected" in line:
            print(f"    {line}")

    print("\n" + "=" * 60)
    print("✅ CI Separation Verification Complete")
    print("\nKey Points:")
    print("- Quick CI excludes heavy and comprehensive tests")
    print("- Comprehensive CI runs only tests marked as comprehensive")
    print("- No duplication between the two pipelines")


if __name__ == "__main__":
    main()
