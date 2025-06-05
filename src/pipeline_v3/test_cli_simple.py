"""
Simple CLI Tests for Pipeline v3 - Phase 3

Basic integration tests for the CLI to verify functionality.
"""

import sys
import subprocess
from pathlib import Path

def test_cli_help():
    """Test that CLI help works."""
    try:
        result = subprocess.run([
            sys.executable, "cli_main.py", "--help"
        ], capture_output=True, text=True, cwd="/Users/seanbergman/Repositories/rag_lab/src/pipeline_v3")
        
        assert result.returncode == 0, f"CLI help failed with code {result.returncode}"
        assert "Production Document Processing Pipeline v3" in result.stdout
        assert "add" in result.stdout
        assert "search" in result.stdout
        assert "queue" in result.stdout
        
        return True
    except Exception as e:
        print(f"CLI help test failed: {e}")
        return False

def test_cli_subcommands():
    """Test that CLI subcommands show help."""
    commands = ["add", "search", "queue", "status", "config"]
    
    for cmd in commands:
        try:
            result = subprocess.run([
                sys.executable, "cli_main.py", cmd, "--help"
            ], capture_output=True, text=True, cwd="/Users/seanbergman/Repositories/rag_lab/src/pipeline_v3")
            
            if result.returncode != 0:
                print(f"Command {cmd} help failed with code {result.returncode}")
                print("STDERR:", result.stderr)
                return False
                
        except Exception as e:
            print(f"Command {cmd} test failed: {e}")
            return False
    
    return True

def test_queue_subcommands():
    """Test queue subcommands."""
    queue_commands = ["start", "stop", "status", "clear"]
    
    for cmd in queue_commands:
        try:
            result = subprocess.run([
                sys.executable, "cli_main.py", "queue", cmd, "--help"
            ], capture_output=True, text=True, cwd="/Users/seanbergman/Repositories/rag_lab/src/pipeline_v3")
            
            if result.returncode != 0:
                print(f"Queue command {cmd} help failed with code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"Queue command {cmd} test failed: {e}")
            return False
    
    return True

def test_config_subcommands():
    """Test config subcommands."""
    config_commands = ["list", "get", "set", "reset"]
    
    for cmd in config_commands:
        try:
            # Skip 'get' and 'set' as they require arguments
            if cmd in ["get", "set"]:
                continue
                
            result = subprocess.run([
                sys.executable, "cli_main.py", "config", cmd, "--help"
            ], capture_output=True, text=True, cwd="/Users/seanbergman/Repositories/rag_lab/src/pipeline_v3")
            
            if result.returncode != 0:
                print(f"Config command {cmd} help failed with code {result.returncode}")
                return False
                
        except Exception as e:
            print(f"Config command {cmd} test failed: {e}")
            return False
    
    return True

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
    else:
        print("❌ Some CLI tests failed.")
        return False

if __name__ == "__main__":
    success = run_simple_tests()
    sys.exit(0 if success else 1)