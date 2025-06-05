#!/usr/bin/env python3
"""
Pipeline v3 CLI Entry Point

Simple entry point for the pipeline CLI that can be called directly.

Usage:
    python cli_main.py [command] [options]
    
This is a convenience script that imports and runs the main CLI.
"""

import sys
import asyncio
from pathlib import Path

# Add the current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from cli.management import main

if __name__ == "__main__":
    asyncio.run(main())