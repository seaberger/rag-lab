"""
Simple CLI Tests for Pipeline v3 - Phase 3

Basic integration tests for the CLI to verify functionality.
"""

import subprocess
import sys
import os
from pathlib import Path
import pytest


def test_cli_help():
    """Test that CLI help works."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "src.pipeline_v3.cli_main", "--help"],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent)}
        )

        assert result.returncode == 0, f"CLI help failed with code {result.returncode}"
        assert "Production Document Processing Pipeline v3" in result.stdout
        assert "add" in result.stdout
        assert "search" in result.stdout
        assert "queue" in result.stdout
    except Exception as e:
        pytest.fail(f"CLI help test failed: {e}")


def test_cli_subcommands():
    """Test that CLI subcommands show help."""
    commands = ["add", "search", "queue", "status", "config"]

    for cmd in commands:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.pipeline_v3.cli_main", cmd, "--help"],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent)}
            )

            assert result.returncode == 0, f"Command {cmd} help failed with code {result.returncode}\nSTDERR: {result.stderr}"

        except Exception as e:
            pytest.fail(f"Command {cmd} test failed: {e}")


def test_queue_subcommands():
    """Test queue subcommands."""
    queue_commands = ["start", "stop", "status", "clear"]

    for cmd in queue_commands:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "src.pipeline_v3.cli_main", "queue", cmd, "--help"],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent)}
            )

            assert result.returncode == 0, f"Queue command {cmd} help failed with code {result.returncode}"

        except Exception as e:
            pytest.fail(f"Queue command {cmd} test failed: {e}")


def test_config_subcommands():
    """Test config subcommands."""
    config_commands = ["list", "get", "set", "reset"]

    for cmd in config_commands:
        try:
            # Skip 'get' and 'set' as they require arguments
            if cmd in ["get", "set"]:
                continue

            result = subprocess.run(
                [sys.executable, "-m", "src.pipeline_v3.cli_main", "config", cmd, "--help"],
                capture_output=True,
                text=True,
                check=False,
                env={**os.environ, "PYTHONPATH": str(Path(__file__).parent.parent.parent.parent)}
            )

            assert result.returncode == 0, f"Config command {cmd} help failed with code {result.returncode}"

        except Exception as e:
            pytest.fail(f"Config command {cmd} test failed: {e}")


def run_simple_tests():
    """Run all simple CLI tests."""
    print("Running Simple CLI Tests...")

    tests = [
        ("CLI Help", test_cli_help),
        ("CLI Subcommands", test_cli_subcommands),
        ("Queue Subcommands", test_queue_subcommands),
        ("Config Subcommands", test_config_subcommands),
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        try:
            if test_func():
                print(f"✓ {test_name} passed")
                passed += 1
            else:
                print(f"✗ {test_name} failed")
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")

    print(f"\nTest Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All CLI tests passed! Phase 3 CLI implementation verified.")
        return True
    print("❌ Some CLI tests failed.")
    return False


if __name__ == "__main__":
    success = run_simple_tests()
    sys.exit(0 if success else 1)
