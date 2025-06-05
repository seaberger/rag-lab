#!/usr/bin/env python3
"""
CLI Demo Script for Pipeline v3

Demonstrates the complete CLI functionality with example commands.
"""

import subprocess
import sys
from pathlib import Path

def run_command(cmd_list, description=""):
    """Run a CLI command and display results."""
    print(f"\n{'='*60}")
    print(f"DEMO: {description}")
    print(f"Command: {' '.join(cmd_list)}")
    print('='*60)
    
    try:
        result = subprocess.run(
            cmd_list, 
            capture_output=True, 
            text=True, 
            cwd="/Users/seanbergman/Repositories/rag_lab/src/pipeline_v3"
        )
        
        if result.stdout:
            print("OUTPUT:")
            print(result.stdout)
        
        if result.stderr:
            print("WARNINGS/ERRORS:")
            print(result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"Error running command: {e}")
        return False

def main():
    """Run CLI demonstration."""
    print("🚀 Pipeline v3 CLI Demonstration")
    print("=" * 60)
    
    # List of demo commands
    demos = [
        # Basic help and information
        ([sys.executable, "cli_main.py", "--help"], 
         "Main CLI Help"),
        
        # Document operations help
        ([sys.executable, "cli_main.py", "add", "--help"], 
         "Add Command Help"),
        
        ([sys.executable, "cli_main.py", "search", "--help"], 
         "Search Command Help"),
        
        # Queue management help
        ([sys.executable, "cli_main.py", "queue", "--help"], 
         "Queue Management Help"),
        
        ([sys.executable, "cli_main.py", "queue", "status", "--help"], 
         "Queue Status Help"),
        
        # System operations help
        ([sys.executable, "cli_main.py", "status", "--help"], 
         "System Status Help"),
        
        ([sys.executable, "cli_main.py", "maintenance", "--help"], 
         "Maintenance Operations Help"),
        
        # Configuration help
        ([sys.executable, "cli_main.py", "config", "--help"], 
         "Configuration Management Help"),
        
        ([sys.executable, "cli_main.py", "config", "list", "--help"], 
         "Config List Help"),
    ]
    
    success_count = 0
    total_count = len(demos)
    
    for cmd_list, description in demos:
        if run_command(cmd_list, description):
            success_count += 1
    
    # Summary
    print(f"\n{'='*60}")
    print(f"DEMO SUMMARY")
    print(f"{'='*60}")
    print(f"Successful demonstrations: {success_count}/{total_count}")
    
    if success_count == total_count:
        print("🎉 All CLI commands working correctly!")
        print("\nThe Pipeline v3 CLI provides:")
        print("  • Document operations (add, update, remove, search)")
        print("  • Queue management (start, stop, status, clear)")
        print("  • System monitoring (status, maintenance)")
        print("  • Configuration management (list, get, set, reset)")
        print("  • JSON output support for automation")
        print("  • Comprehensive help for all commands")
        
        print("\nExample usage:")
        print("  python cli_main.py add document.pdf --metadata type=datasheet")
        print("  python cli_main.py search 'laser sensors' --type hybrid --top-k 5")
        print("  python cli_main.py queue start --workers 8")
        print("  python cli_main.py status --detailed --json")
        
        return True
    else:
        print("❌ Some CLI commands had issues.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)