#!/usr/bin/env python3
"""
Production Pipeline v3 - Main CLI Entry Point

A temporary CLI to test the v3 foundation before implementing full queue management.
This provides basic functionality while we build the enterprise features.
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

try:
    from core.pipeline import ingest_sources
    from utils.config import PipelineConfig
    from utils.common_utils import logger, DependencyError, CLIArgumentError, ConfigLoadError
    from utils.env_utils import setup_environment
except ImportError as e:
    raise DependencyError(f"Import error: {e}. Make sure you're running from the pipeline_v3 directory")


def main():
    """Main CLI entry point for Pipeline v3."""
    parser = argparse.ArgumentParser(
        description="Production Document Pipeline v3 - Development Version",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli_v3.py --src document.pdf --mode datasheet --with-keywords
  python cli_v3.py --src "docs/*.pdf" --mode auto
  python cli_v3.py --src folder/ --mode generic

Note: This is the development CLI for Pipeline v3. Full queue management
      and enterprise features are under development.
        """
    )
    
    parser.add_argument(
        "--src", 
        required=True,
        help="Source document(s) to process (file, directory, or glob pattern)"
    )
    
    parser.add_argument(
        "--mode",
        choices=["auto", "datasheet", "generic", "markdown"],
        default="auto",
        help="Processing mode (default: auto)"
    )
    
    parser.add_argument(
        "--with-keywords",
        action="store_true",
        help="Generate keywords for better search (increases processing time)"
    )
    
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Configuration file path (default: config.yaml)"
    )
    
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=5,
        help="Maximum concurrent processing workers (default: 5)"
    )
    
    parser.add_argument(
        "--force-reprocess",
        action="store_true", 
        help="Force reprocessing even if document appears unchanged"
    )
    
    args = parser.parse_args()
    
    # Setup environment
    setup_environment()
    
    # Load configuration
    try:
        config = PipelineConfig.from_yaml(args.config)
        logger.info(f"✅ Loaded configuration from: {args.config}")
        logger.info(f"🚀 Pipeline v3 starting with mode: {args.mode}")
    except Exception as e:
        logger.error(f"❌ Failed to load configuration: {e}")
        raise ConfigLoadError(f"Failed to load configuration: {e}")
    
    # Determine sources
    sources = []
    src_path = Path(args.src)
    
    if src_path.is_file():
        sources = [str(src_path)]
    elif src_path.is_dir():
        # Find all PDF and MD files in directory
        sources = [
            str(f) for f in src_path.rglob("*") 
            if f.suffix.lower() in [".pdf", ".md", ".txt"]
        ]
    else:
        # Try glob pattern
        import glob
        sources = glob.glob(args.src)
    
    if not sources:
        logger.error(f"❌ No valid sources found for: {args.src}")
        raise CLIArgumentError(f"No valid sources found for: {args.src}")
    
    logger.info(f"📁 Found {len(sources)} source(s) to process")
    
    # Run pipeline
    try:
        asyncio.run(run_pipeline(
            sources=sources,
            mode=args.mode,
            with_keywords=args.with_keywords,
            max_concurrent=args.max_concurrent,
            force_reprocess=args.force_reprocess,
            config_file=args.config
        ))
    except KeyboardInterrupt:
        logger.info("🛑 Processing interrupted by user")
        raise DependencyError("Processing interrupted by user")
    except Exception as e:
        logger.error(f"❌ Pipeline failed: {e}")
        raise DependencyError(f"Pipeline failed: {e}")


async def run_pipeline(
    sources: List[str],
    mode: str,
    with_keywords: bool,
    max_concurrent: int,
    force_reprocess: bool,
    config_file: str
):
    """Run the v3 pipeline with the provided parameters."""
    
    # Convert mode to datasheet_mode flag for compatibility
    is_datasheet_mode = mode in ["datasheet", "auto"]
    
    # For now, use the v2.1 pipeline function as foundation
    # This will be replaced with v3 queue-based processing
    logger.info("🔧 Using v2.1 pipeline foundation (v3 queue system under development)")
    
    await ingest_sources(
        sources=sources,
        prompt_file=None,
        with_keywords=with_keywords,
        is_datasheet_mode=is_datasheet_mode,
        config_file=config_file
    )
    
    logger.info("✅ Pipeline v3 processing completed!")
    logger.info("📊 Check processing_report.json for detailed metrics")


if __name__ == "__main__":
    main()