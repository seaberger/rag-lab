#!/usr/bin/env python3
"""
Pipeline v3 CLI Entry Point

Simple entry point for the pipeline CLI that can be called directly.

Usage:
    python cli_main.py [command] [options]

This is a convenience script that imports and runs the main CLI.
"""

import asyncio
import logging
import sys

# Import using absolute imports
from src.pipeline_v3.cli.management import main
from src.pipeline_v3.utils.cleanup import cleanup_temp_resources, get_resource_manager
from src.pipeline_v3.utils.common_utils import (
    CLIArgumentError,
    ConfigLoadError,
    DependencyError,
    init_cli_logging,
)

# Initialize logging first
init_cli_logging()

logger = logging.getLogger(__name__)


def run_cli():
    resource_manager = get_resource_manager()
    try:
        asyncio.run(main())
        sys.exit(0)
    except KeyboardInterrupt:
        logger.warning("Operation cancelled by user")
        sys.exit(130)
    except CLIArgumentError as e:
        if hasattr(e, "command_string") and e.command_string:
            logger.exception("CLI argument error | Command: %s", e.command_string)
        else:
            logger.exception("CLI argument error")
        print("❌ Invalid arguments:", e)
        sys.exit(128)
    except DependencyError as e:
        if hasattr(e, "command_string") and e.command_string:
            logger.critical("Dependency error: %s | Command: %s", e, e.command_string)
        else:
            logger.critical("Dependency error: %s", e)
        print("❌ Dependency error:", e)
        sys.exit(126)
    except ConfigLoadError as e:
        if hasattr(e, "command_string") and e.command_string:
            logger.exception("Configuration error: %s | Command: %s", e, e.command_string)
        else:
            logger.exception("Configuration error")
        print("❌ Configuration error:", e)
        sys.exit(127)
    except FileNotFoundError as e:
        logger.exception("File not found")
        print("❌ File not found:", e)
        sys.exit(127)
    except ImportError as e:
        logger.critical("Missing dependency: %s", e)
        print("❌ Required dependency not installed. See log for details.")
        sys.exit(126)
    except ConnectionError as e:
        logger.exception("Network error")
        print("❌ Network error:", e)
        sys.exit(1)
    except ValueError as e:
        logger.exception("Invalid argument")
        print("❌ Invalid argument:", e)
        sys.exit(128)
    except Exception:
        logger.exception("Unhandled exception")
        print("❌ Unexpected error. Run with -v for details.")
        sys.exit(1)
    finally:
        # Ensure cleanup happens on exit
        try:
            resource_manager.cleanup()
            cleanup_temp_resources()
        except Exception as e:
            logger.warning(f"Error during cleanup: {e}")


if __name__ == "__main__":
    run_cli()
