#!/usr/bin/env python3
"""
Main CLI for the datasheet ingestion pipeline.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Use try/except for more robust imports
try:
    from pipeline.core import ingest_sources
    from utils.common_utils import logger
    from utils.env_utils import setup_environment
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running from the correct directory")
    sys.exit(1)

async def main():
    """Main CLI function."""
    parser = argparse.ArgumentParser(
        description="Datasheet Ingestion Pipeline - Process PDFs and Markdown into searchable database"
    )
    parser.add_argument(
        "--src", 
        nargs="+", 
        required=True,
        help="Source files or URLs to process (PDFs, Markdown files)"
    )
    parser.add_argument(
        "--prompt", 
        help="Path to custom prompt file for document parsing"
    )
    parser.add_argument(
        "--with_keywords", 
        action="store_true",
        help="Enable keyword generation for enhanced search"
    )
    parser.add_argument(
        "--keyword_model", 
        default="gpt-4o-mini",
        help="Model to use for keyword generation (default: gpt-4o-mini)"
    )
    parser.add_argument(
        "--mode",
        choices=["datasheet", "generic", "auto"],
        default="auto",
        help="Parsing mode: 'datasheet' for pair extraction, 'generic' for simple PDF, 'auto' to detect",
    )
    parser.add_argument(
        "--config", 
        default="config.yaml", 
        help="Configuration file path (default: config.yaml)"
    )

    args = parser.parse_args()

    # Setup environment (find .env, verify API keys)
    if not setup_environment():
        logger.error("❌ Environment setup failed. Please check your configuration.")
        sys.exit(1)

    # Determine parsing behavior
    if args.mode == "auto":
        # Auto-detect based on prompt content or filename patterns
        is_datasheet_mode = "datasheet" in (args.prompt or "").lower()
    else:
        is_datasheet_mode = args.mode == "datasheet"

    logger.info(f"🚀 Starting document ingestion pipeline...")
    logger.info(f"📁 Sources: {args.src}")
    logger.info(f"🎯 Mode: {args.mode} (datasheet_mode: {is_datasheet_mode})")
    logger.info(f"🔍 Keywords enabled: {args.with_keywords}")
    logger.info(f"⚙️ Config file: {args.config}")

    try:
        # Run the ingestion pipeline
        await ingest_sources(
            sources=args.src,
            prompt_file=args.prompt,
            with_keywords=args.with_keywords,
            keyword_model=args.keyword_model,
            is_datasheet_mode=is_datasheet_mode,
            config_file=args.config,
        )
        
        logger.info("✅ Pipeline completed successfully!")
        
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
