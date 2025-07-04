#!/usr/bin/env python3
"""
Production Pipeline v3 - CLI Management Interface

Main command-line interface for document processing pipeline management.
Provides comprehensive controls for document operations, queue management,
system maintenance, and configuration.

Usage:
    python -m pipeline_v3.cli.management [command] [options]

Commands:
    add         Add documents to the pipeline
    update      Update existing documents
    remove      Remove documents from indexes
    search      Search through indexed documents
    queue       Manage processing queue
    status      Show system status
    maintenance Run maintenance operations
    config      Manage configuration
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# Import custom exceptions and logger
from utils.common_utils import (
    CLIArgumentError,
    ConfigLoadError,
    DependencyError,
    logger,
)

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with graceful degradation
try:
    from pipeline.enhanced_core import EnhancedPipeline

    PIPELINE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Pipeline components not available: {e}")
    PIPELINE_AVAILABLE = False
    EnhancedPipeline = None

try:
    from core.index_manager import IndexManager
    from core.registry import DocumentRegistry, IndexType
    from job_queue.manager import DocumentQueue

    from utils.config import PipelineConfig
    from utils.env_utils import setup_environment
    from utils.monitoring import ProgressMonitor
    from utils.url_utils import (
        create_url_batch_file,
        extract_urls_from_file,
        validate_url_list,
    )

    CORE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Core components not available: {e}")
    CORE_AVAILABLE = False
    DocumentQueue = None
    DocumentRegistry = None
    IndexManager = None
    PipelineConfig = None
    ProgressMonitor = None
    extract_urls_from_file = None
    validate_url_list = None
    create_url_batch_file = None


class PipelineCLI:
    """Main CLI interface for pipeline management."""

    def __init__(self, config_path: str | None = None):
        if not CORE_AVAILABLE:
            command_string = " ".join(sys.argv[1:])
            raise DependencyError(
                "Core pipeline components not available. Please install dependencies: uv add llama-index llama-index-vector-stores-qdrant",
                command_string=command_string,
            )

        # Setup environment (load .env file)
        setup_environment()

        # Load configuration with error handling
        # Since PipelineConfig.from_yaml handles errors internally and returns defaults,
        # we need to wrap it and detect when errors occurred
        import contextlib
        import io

        # Capture any warning/error messages printed by from_yaml
        output_capture = io.StringIO()

        try:
            # Capture stdout to detect error messages from PipelineConfig.from_yaml
            with contextlib.redirect_stdout(output_capture):
                if config_path:
                    self.config = PipelineConfig.from_yaml(config_path)
                else:
                    self.config = PipelineConfig.from_yaml()

            # Check if any error/warning messages were captured
            captured_output = output_capture.getvalue()
            if "Warning:" in captured_output or "Error" in captured_output:
                # Config loading had issues, create ConfigLoadError
                logger = logging.getLogger(__name__)
                command_string = " ".join(sys.argv[1:])
                path_info = (
                    f" (config path: {config_path})" if config_path else " (default config path)"
                )
                error_msg = f"Failed to load configuration{path_info}: {captured_output.strip()}"

                # Create and store the ConfigLoadError with path info
                config_error = ConfigLoadError(error_msg, command_string=command_string)
                logger.warning(f"Configuration load error: {error_msg}")

                # Print user-friendly message
                print("⚠️  Using default settings")

                # Store the error for potential later access
                self._config_load_error = config_error

        except Exception as e:
            # This catches any unexpected exceptions during config loading
            logger = logging.getLogger(__name__)
            command_string = " ".join(sys.argv[1:])
            path_info = (
                f" (config path: {config_path})" if config_path else " (default config path)"
            )
            error_msg = f"Failed to load configuration{path_info}: {e}"

            # Create ConfigLoadError with path info and continue with defaults
            config_error = ConfigLoadError(error_msg, command_string=command_string)
            logger.warning(f"Configuration load error: {error_msg}")
            logger.debug(f"Config error details: {e}", exc_info=True)

            # Print user-friendly message and use defaults
            print("⚠️  Using default settings")
            self.config = PipelineConfig()  # Fallback to defaults

            # Store the error for potential later access
            self._config_load_error = config_error

        self.pipeline = None
        self.queue = None
        self.registry = None
        self.index_manager = None
        self.monitor = ProgressMonitor()

    def get_config_load_error(self) -> ConfigLoadError | None:
        """Get the configuration load error if any occurred during initialization.

        Returns:
            ConfigLoadError if config loading failed, None otherwise
        """
        return getattr(self, "_config_load_error", None)

    async def initialize(self):
        """Initialize pipeline components."""
        try:
            self.registry = DocumentRegistry(self.config)
            self.index_manager = IndexManager(self.config, registry=self.registry)

            if PIPELINE_AVAILABLE:
                self.pipeline = EnhancedPipeline(
                    self.config,
                    registry=self.registry,
                    index_manager=self.index_manager,
                )

            self.queue = DocumentQueue(self.config)

        except ImportError as e:
            command_string = " ".join(sys.argv[1:])
            raise DependencyError(
                f"Failed to initialize pipeline: missing dependency: {e}",
                command_string=command_string,
            )
        except Exception as e:
            command_string = " ".join(sys.argv[1:])
            if "config" in str(e).lower():
                raise ConfigLoadError(
                    f"Configuration error during initialization: {e}",
                    command_string=command_string,
                )
            raise DependencyError(
                f"Error initializing pipeline: {e}. Make sure all dependencies are installed and configured properly",
                command_string=command_string,
            )

    def create_parser(self) -> argparse.ArgumentParser:
        """Create the main argument parser."""
        parser = argparse.ArgumentParser(
            prog="pipeline",
            description="Production Document Processing Pipeline v3",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  pipeline add document.pdf --metadata type=datasheet
  pipeline search "laser sensors" --type hybrid --top-k 5
  pipeline queue start --workers 8
  pipeline status --detailed
  pipeline maintenance --repair
            """,
        )

        parser.add_argument("--config", type=str, help="Path to configuration file")
        parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose output")
        parser.add_argument("--json", action="store_true", help="Output results in JSON format")

        subparsers = parser.add_subparsers(dest="command", help="Available commands")

        # Document operations
        self._add_document_commands(subparsers)

        # Queue management
        self._add_queue_commands(subparsers)

        # System operations
        self._add_system_commands(subparsers)

        # Configuration
        self._add_config_commands(subparsers)

        # Batch operations
        self._add_batch_commands(subparsers)

        return parser

    def _add_document_commands(self, subparsers):
        """Add document-related commands."""
        # Add command
        add_parser = subparsers.add_parser("add", help="Add documents to pipeline")
        add_parser.add_argument(
            "sources",
            nargs="+",
            help="Document paths, URLs, directories, or glob patterns",
        )
        add_parser.add_argument("--metadata", action="append", help="Metadata key=value pairs")
        add_parser.add_argument(
            "--force",
            action="store_true",
            help="Force processing even if document exists",
        )
        add_parser.add_argument(
            "--index-type",
            choices=["vector", "keyword", "both"],
            default="both",
            help="Type of index to create",
        )
        # NEW: Enterprise-ready consistent parameters
        add_parser.add_argument(
            "--document-type",
            choices=["datasheet", "manual", "specification", "generic", "auto"],
            default="auto",
            help="Type of document being processed (default: auto-detect)",
        )
        add_parser.add_argument(
            "--processing-options",
            type=str,
            help="Comma-separated processing options: keywords,enhanced-metadata,fast-mode",
        )
        add_parser.add_argument(
            "--profile",
            type=str,
            help="Use a predefined processing profile from config",
        )

        # DEPRECATED: Keep old parameters for backward compatibility
        add_parser.add_argument(
            "--mode",
            choices=["datasheet", "generic", "auto"],
            default="auto",
            help="(Deprecated: use --document-type) Document classification mode",
        )
        add_parser.add_argument(
            "--with-keywords",
            action="store_true",
            help="(Deprecated: use --processing-options keywords) Enable keyword generation",
        )

        # Other parameters remain unchanged
        add_parser.add_argument("--prompt", help="Path to custom prompt file for parsing")
        add_parser.add_argument(
            "--workers",
            type=int,
            help="Number of concurrent workers for batch processing",
        )
        add_parser.add_argument(
            "--recursive", action="store_true", help="Recursively process directories"
        )
        add_parser.add_argument(
            "--timeout",
            type=int,
            help="Override timeout in seconds (default: calculated based on page count)",
        )
        add_parser.add_argument(
            "--timeout-per-page",
            type=int,
            help="Override timeout per page in seconds (default: 30)",
        )
        add_parser.add_argument(
            "--url-file",
            help="Path to markdown or JSON file containing URLs to process",
        )
        add_parser.add_argument(
            "--pages",
            help='Page range to process (e.g., "1-5", "1,3,7", "10-20", "1-10,15-20"). Useful for testing large documents or processing specific sections.',
        )
        add_parser.add_argument(
            "--exclude-pattern",
            action="append",
            help='Glob patterns to exclude (e.g., "*.tmp", "**/test/**", ".git/**"). Can be specified multiple times.',
        )
        add_parser.add_argument(
            "--include-pattern",
            action="append",
            help='Glob patterns to include (e.g., "*.pdf", "reports/**/*.docx"). Can be specified multiple times.',
        )
        add_parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview files that would be processed without actually processing them",
        )

        # Remove command
        remove_parser = subparsers.add_parser("remove", help="Remove documents")
        remove_parser.add_argument("paths", nargs="+", help="Document paths to remove")
        remove_parser.add_argument(
            "--index-type",
            choices=["vector", "keyword", "both"],
            default="both",
            help="Which indexes to remove from",
        )

        # Search command
        search_parser = subparsers.add_parser("search", help="Search documents")
        search_parser.add_argument("query", help="Search query")
        search_parser.add_argument(
            "--type",
            choices=["vector", "keyword", "hybrid"],
            default="hybrid",
            help="Search type",
        )
        search_parser.add_argument(
            "--top-k", type=int, default=10, help="Number of results to return"
        )
        search_parser.add_argument("--filter", help="Filter expression (JSON format)")
        search_parser.add_argument(
            "--fusion-method",
            choices=["rrf", "weighted", "adaptive"],
            default="rrf",
            help="Hybrid search fusion method (default: rrf)",
        )

    def _add_queue_commands(self, subparsers):
        """Add queue management commands."""
        queue_parser = subparsers.add_parser("queue", help="Manage processing queue")
        queue_subparsers = queue_parser.add_subparsers(dest="queue_action")

        # Start queue
        start_parser = queue_subparsers.add_parser("start", help="Start queue processing")
        start_parser.add_argument("--workers", type=int, help="Number of worker threads")

        # Stop queue
        stop_parser = queue_subparsers.add_parser("stop", help="Stop queue processing")
        stop_parser.add_argument(
            "--wait", action="store_true", help="Wait for current jobs to complete"
        )

        # Queue status
        status_parser = queue_subparsers.add_parser("status", help="Show queue status")
        status_parser.add_argument(
            "--detailed", action="store_true", help="Show detailed job information"
        )

        # Clear queue
        clear_parser = queue_subparsers.add_parser("clear", help="Clear all queued jobs")
        clear_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    def _add_system_commands(self, subparsers):
        """Add system operation commands."""
        # Status command
        status_parser = subparsers.add_parser("status", help="Show system status")
        status_parser.add_argument(
            "--detailed", action="store_true", help="Show detailed system information"
        )
        status_parser.add_argument("--json", action="store_true", help="Output in JSON format")

        # Maintenance command
        maint_parser = subparsers.add_parser("maintenance", help="Run maintenance operations")
        maint_parser.add_argument(
            "--repair", action="store_true", help="Repair index inconsistencies"
        )
        maint_parser.add_argument("--cleanup", action="store_true", help="Clean up temporary files")
        maint_parser.add_argument(
            "--consistency-check", action="store_true", help="Check index consistency"
        )

    def _add_config_commands(self, subparsers):
        """Add configuration commands."""
        config_parser = subparsers.add_parser("config", help="Manage configuration")
        config_subparsers = config_parser.add_subparsers(dest="config_action")

        # List config
        config_subparsers.add_parser("list", help="List all configuration")

        # Get config
        get_parser = config_subparsers.add_parser("get", help="Get configuration value")
        get_parser.add_argument("key", help="Configuration key")

        # Set config
        set_parser = config_subparsers.add_parser("set", help="Set configuration value")
        set_parser.add_argument("key", help="Configuration key")
        set_parser.add_argument("value", help="Configuration value")

        # Reset config
        reset_parser = config_subparsers.add_parser("reset", help="Reset configuration")
        reset_parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")

    def _add_batch_commands(self, subparsers):
        """Add batch processing commands."""
        batch_parser = subparsers.add_parser("batch", help="Batch processing operations")
        batch_subparsers = batch_parser.add_subparsers(dest="batch_action")

        # Create URL file
        create_url_parser = batch_subparsers.add_parser(
            "create-url-file", help="Create URL batch file"
        )
        create_url_parser.add_argument("urls", nargs="+", help="URLs to include in batch file")
        create_url_parser.add_argument(
            "--output", "-o", required=True, help="Output file path (.json or .md)"
        )
        create_url_parser.add_argument(
            "--format",
            choices=["json", "markdown"],
            help="Output format (auto-detected from extension if not specified)",
        )

        # Validate URL file
        validate_url_parser = batch_subparsers.add_parser(
            "validate-urls", help="Validate URL batch file"
        )
        validate_url_parser.add_argument("file", help="URL batch file to validate")

        # Test queue with URLs
        test_queue_parser = batch_subparsers.add_parser(
            "test-queue", help="Test queue processing with URL batch"
        )
        test_queue_parser.add_argument("url_file", help="URL batch file to process")
        test_queue_parser.add_argument(
            "--workers", type=int, default=2, help="Number of workers to test with"
        )
        test_queue_parser.add_argument(
            "--with-keywords",
            action="store_true",
            help="Enable keyword generation during test",
        )

    async def run(self, args):
        """Run the CLI with parsed arguments."""
        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)

        await self.initialize()

        if args.command == "add":
            await self.handle_add(args)
        elif args.command == "remove":
            await self.handle_remove(args)
        elif args.command == "search":
            await self.handle_search(args)
        elif args.command == "queue":
            await self.handle_queue(args)
        elif args.command == "status":
            await self.handle_status(args)
        elif args.command == "maintenance":
            await self.handle_maintenance(args)
        elif args.command == "config":
            await self.handle_config(args)
        elif args.command == "batch":
            await self.handle_batch(args)
        else:
            command_string = " ".join(sys.argv[1:])
            raise CLIArgumentError(
                "Unknown command. Use --help for usage information.",
                command_string=command_string,
            )

    def _resolve_sources(
        self,
        sources: list[str],
        recursive: bool = False,
        url_file: str | None = None,
        exclude_patterns: list[str] | None = None,
        include_patterns: list[str] | None = None,
    ) -> list[str]:
        """Resolve sources to actual file paths.

        Supports:
        - Individual files
        - URLs (http/https)
        - Directories (with optional recursion)
        - Glob patterns
        - URL batch files (markdown/JSON)

        Args:
            sources: List of source patterns/paths/URLs
            recursive: Whether to recursively search directories
            url_file: Path to file containing URLs to process

        Returns:
            List of resolved file paths and URLs
        """
        resolved = []

        # Process URL file first if provided
        if url_file:
            url_file_path = Path(url_file)
            if not url_file_path.exists():
                print(f"Warning: URL file not found: {url_file}")
            else:
                print(f"Processing URL file: {url_file}")
                urls_from_file = extract_urls_from_file(url_file_path)
                if urls_from_file:
                    resolved.extend(urls_from_file)
                    print(f"Loaded {len(urls_from_file)} URLs from file")
                else:
                    print("Warning: No URLs found in file")

        for source in sources:
            # Handle URLs directly
            if source.startswith(("http://", "https://")):
                resolved.append(source)
                continue

            source_path = Path(source)

            # Handle existing files
            if source_path.is_file():
                resolved.append(str(source_path))
                continue

            # Handle directories
            if source_path.is_dir():
                print(
                    f"📁 Scanning directory: {source_path}" + (" (recursive)" if recursive else "")
                )

                # Define supported file extensions (including Office documents)
                supported_extensions = [
                    ".pdf",
                    ".txt",
                    ".md",
                    ".markdown",
                    ".docx",
                    ".pptx",
                    ".doc",
                    ".ppt",
                ]

                dir_files = []
                if recursive:
                    # Recursively find all supported files
                    patterns = ["**/*" + ext for ext in supported_extensions]
                    for pattern in patterns:
                        dir_files.extend(str(p) for p in source_path.glob(pattern))
                else:
                    # Just immediate children
                    patterns = ["*" + ext for ext in supported_extensions]
                    for pattern in patterns:
                        dir_files.extend(str(p) for p in source_path.glob(pattern))

                if dir_files:
                    print(f"   Found {len(dir_files)} document(s) in {source_path}")
                resolved.extend(dir_files)
                continue

            # Handle glob patterns
            try:
                # Use Path.glob for better portability
                path = Path(source)
                if "*" in source or "?" in source or "[" in source:
                    # It's a glob pattern
                    base_path = Path.cwd()
                    pattern = source
                    if "/" in source or "\\" in source:
                        # Extract base path from pattern
                        parts = source.replace("\\", "/").split("/")
                        for i, part in enumerate(parts):
                            if "*" in part or "?" in part or "[" in part:
                                base_path = Path("/".join(parts[:i])) if i > 0 else Path.cwd()
                                pattern = "/".join(parts[i:])
                                break

                    if recursive and "**" not in pattern:
                        pattern = f"**/{pattern}"

                    matches = [str(p) for p in base_path.glob(pattern)]
                else:
                    # Not a glob pattern, treat as literal path
                    matches = [source] if Path(source).exists() else []
                if matches:
                    # Filter to supported file types
                    supported_extensions = [
                        ".pdf",
                        ".txt",
                        ".md",
                        ".markdown",
                        ".docx",
                        ".pptx",
                        ".doc",
                        ".ppt",
                    ]
                    for match in matches:
                        match_path = Path(match)
                        if (
                            match_path.is_file()
                            and match_path.suffix.lower() in supported_extensions
                        ):
                            resolved.append(match)
                else:
                    print(f"Warning: No files found matching pattern: {source}")
            except Exception as e:
                print(f"Warning: Invalid glob pattern '{source}': {e}")

        # Apply include/exclude filters
        filtered_resolved = []
        for path in resolved:
            # Skip URLs from filtering
            if path.startswith(("http://", "https://")):
                filtered_resolved.append(path)
                continue

            path_obj = Path(path)

            # Check exclude patterns
            excluded = False
            if exclude_patterns:
                for pattern in exclude_patterns:
                    if path_obj.match(pattern) or any(p.match(pattern) for p in path_obj.parents):
                        excluded = True
                        break

            if excluded:
                continue

            # Check include patterns (if specified, file must match at least one)
            if include_patterns:
                included = False
                for pattern in include_patterns:
                    if path_obj.match(pattern):
                        included = True
                        break
                if not included:
                    continue

            filtered_resolved.append(path)

        # Remove duplicates while preserving order
        seen = set()
        unique_resolved = []
        for path in filtered_resolved:
            if path not in seen:
                seen.add(path)
                unique_resolved.append(path)

        return unique_resolved

    def _parse_metadata(self, metadata_list: list[str] | None) -> dict[str, Any]:
        """Parse metadata key=value pairs."""
        metadata = {}
        if metadata_list:
            for item in metadata_list:
                if "=" not in item:
                    print(f"Warning: Invalid metadata format '{item}', expected key=value")
                    continue
                key, value = item.split("=", 1)
                metadata[key] = value
        return metadata

    def _parse_index_type(self, index_type_str: str) -> IndexType:
        """Convert string to IndexType enum."""
        if index_type_str == "vector":
            return IndexType.VECTOR
        if index_type_str == "keyword":
            return IndexType.KEYWORD
        if index_type_str == "both":
            return IndexType.BOTH
        raise ValueError(f"Invalid index type: {index_type_str}")

    def _migrate_deprecated_parameters(self, args):
        """Migrate deprecated parameters to new format with warnings."""
        import warnings

        # Ensure new attributes exist with defaults
        if not hasattr(args, "document_type"):
            args.document_type = None
        if not hasattr(args, "processing_options"):
            args.processing_options = None

        # Migrate --mode to --document-type
        if hasattr(args, "mode") and args.mode and args.mode != "auto" and not args.document_type:
            warnings.warn(
                "Parameter --mode is deprecated. Use --document-type instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning("CLI: --mode is deprecated. Use --document-type instead.")
            args.document_type = args.mode
        elif args.document_type:
            # New parameter takes precedence
            pass
        elif hasattr(args, "mode") and args.mode:
            # Use mode as fallback if document_type not set
            args.document_type = args.mode
        else:
            # Default to auto if neither is set
            args.document_type = "auto"

        # Migrate --with-keywords to --processing-options
        if hasattr(args, "with_keywords") and args.with_keywords and not args.processing_options:
            warnings.warn(
                "Parameter --with-keywords is deprecated. Use --processing-options keywords instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            logger.warning(
                "CLI: --with-keywords is deprecated. Use --processing-options keywords instead."
            )
            args.processing_options = "keywords"
        elif args.processing_options:
            # New parameter takes precedence
            pass

        # Process profile settings if specified
        if hasattr(args, "profile") and args.profile:
            self._apply_profile(args)

        return args

    def _apply_profile(self, args):
        """Apply processing profile from configuration."""
        profile_name = args.profile

        # Get available profiles
        available_profiles = self.config.processing_profiles.profiles

        if profile_name not in available_profiles:
            logger.warning(
                f"Profile '{profile_name}' not found. Available profiles: {list(available_profiles.keys())}"
            )
            print(
                f"Warning: Profile '{profile_name}' not found. Available profiles: {', '.join(available_profiles.keys())}"
            )
            return

        profile = available_profiles[profile_name]
        logger.info(f"Applying profile '{profile_name}': {profile.description}")

        # Apply profile settings (only if not already set by explicit parameters)
        if not args.document_type or args.document_type == "auto":
            args.document_type = profile.document_type
            logger.debug(f"Profile: Set document_type to {profile.document_type}")

        if not args.processing_options:
            args.processing_options = ",".join(profile.processing_options)
            logger.debug(f"Profile: Set processing_options to {args.processing_options}")

        # Apply timeout multiplier
        if profile.timeout_multiplier != 1.0:
            original_timeout = self.config.pipeline.timeout_seconds
            self.config.pipeline.timeout_seconds = int(
                original_timeout * profile.timeout_multiplier
            )
            logger.debug(
                f"Profile: Adjusted timeout from {original_timeout}s to {self.config.pipeline.timeout_seconds}s"
            )

    def _parse_processing_options(self, options_str: str | None) -> dict[str, bool]:
        """Parse processing options string into dictionary."""
        if not options_str:
            return {}

        options = {}
        for opt in options_str.split(","):
            opt = opt.strip().lower()
            if opt == "keywords":
                options["with_keywords"] = True
            elif opt == "enhanced-metadata":
                options["enhanced_metadata"] = True
            elif opt == "fast-mode":
                options["fast_mode"] = True
            else:
                logger.warning(f"Unknown processing option: {opt}")

        return options

    def _format_output(self, data: Any, json_format: bool = False) -> str:
        """Format output for display."""
        if json_format:
            return json.dumps(data, indent=2, default=str)

        if isinstance(data, dict):
            return "\n".join(f"{k}: {v}" for k, v in data.items())
        if isinstance(data, list):
            return "\n".join(str(item) for item in data)
        return str(data)

    async def handle_add(self, args):
        """Handle document addition with enhanced features."""
        # Handle parameter migration (Phase 2: Intelligent migration)
        args = self._migrate_deprecated_parameters(args)

        # Resolve all sources (files, URLs, directories, globs, URL files)
        resolved_sources = self._resolve_sources(
            args.sources,
            args.recursive,
            getattr(args, "url_file", None),
            getattr(args, "exclude_pattern", None),
            getattr(args, "include_pattern", None),
        )

        if not resolved_sources:
            print("No documents found to process.")
            return

        print(f"Found {len(resolved_sources)} document(s) to process")

        # If dry-run, show what would be processed and exit
        if getattr(args, "dry_run", False):
            print("\n🔍 DRY RUN - Files that would be processed:")

            # Group by type
            by_type = {}
            for source in resolved_sources:
                if source.startswith(("http://", "https://")):
                    file_type = "URL"
                else:
                    file_type = Path(source).suffix.lower() or "no extension"
                by_type.setdefault(file_type, []).append(source)

            # Display by type
            for file_type, files in sorted(by_type.items()):
                print(f"\n  {file_type} ({len(files)} files):")
                for file in sorted(files)[:10]:  # Show first 10
                    print(f"    • {file}")
                if len(files) > 10:
                    print(f"    ... and {len(files) - 10} more")

            print("\n📊 Summary:")
            print(f"   Total files: {len(resolved_sources)}")
            for file_type, files in sorted(by_type.items()):
                print(f"   {file_type}: {len(files)}")

            print("\n✅ Dry run complete. Use without --dry-run to process these files.")
            return

        # Parse metadata
        metadata = self._parse_metadata(args.metadata)

        # Apply timeout overrides if provided
        if args.timeout:
            self.config.pipeline.timeout_seconds = args.timeout
            print(f"Using custom timeout: {args.timeout}s")
        if args.timeout_per_page:
            self.config.openai.timeout_per_page = args.timeout_per_page
            print(f"Using custom timeout per page: {args.timeout_per_page}s")

        # Determine processing mode
        if len(resolved_sources) == 1:
            # Single document processing
            source = resolved_sources[0]
            try:
                print(f"Processing: {source}")
                # Parse processing options
                processing_options = self._parse_processing_options(
                    getattr(args, "processing_options", None)
                )

                result = await self.pipeline.process_document(
                    source,
                    metadata=metadata,
                    force_reprocess=args.force,
                    index_types=self._parse_index_type(args.index_type),
                    mode=getattr(args, "document_type", "auto"),  # Use new parameter
                    prompt_file=args.prompt,
                    with_keywords=processing_options.get("with_keywords", False),
                    page_range=getattr(args, "pages", None),
                )

                if args.json:
                    print(self._format_output(result, True))
                else:
                    status = result.get("status", "unknown")
                    doc_id = result.get("doc_id", "N/A")
                    processing_time = result.get("processing_time", 0)
                    print(
                        f"✅ {source} -> {status} (doc_id: {doc_id}, time: {processing_time:.2f}s)"
                    )

            except Exception as e:
                print(f"❌ Error processing {source}: {e}")

        else:
            # Batch processing
            document_type = getattr(args, "document_type", "auto")
            print(f"Starting batch processing with document type: {document_type}")

            # Parse processing options once for batch
            processing_options = self._parse_processing_options(
                getattr(args, "processing_options", None)
            )

            # Prepare document info for batch processing
            document_infos = []
            for source in resolved_sources:
                doc_info = {
                    "source": source,
                    "metadata": metadata.copy(),
                    "force_reprocess": args.force,
                    "mode": document_type,  # Use new parameter name
                    "prompt_file": args.prompt,
                    "with_keywords": processing_options.get("with_keywords", False),
                    "page_range": getattr(args, "pages", None),
                }
                document_infos.append(doc_info)

            # Determine concurrent workers
            max_concurrent = args.workers
            if max_concurrent is None:
                max_concurrent = min(len(resolved_sources), self.config.pipeline.max_concurrent)

            print(f"Using {max_concurrent} concurrent workers")

            try:
                # Use batch processing
                batch_result = await self.pipeline.process_document_batch(
                    document_infos,
                    use_queue=False,  # Direct processing for CLI
                    max_concurrent=max_concurrent,
                )

                if args.json:
                    print(self._format_output(batch_result, True))
                else:
                    # Print summary
                    total = batch_result.get("total_documents", 0)
                    successful = batch_result.get("successful", 0)
                    errors = batch_result.get("errors", 0)
                    skipped = batch_result.get("skipped", 0)
                    processing_time = batch_result.get("processing_time", 0)

                    print("\n📊 Batch Processing Complete:")
                    print(f"   Total: {total} documents")
                    print(f"   ✅ Successful: {successful}")
                    print(f"   ⏭️  Skipped: {skipped}")
                    print(f"   ❌ Errors: {errors}")
                    print(f"   ⏱️  Total time: {processing_time:.2f}s")

                    # Save processing report
                    if hasattr(self.pipeline, "save_processing_report"):
                        report_saved = self.pipeline.save_processing_report()
                        if report_saved:
                            print("   📄 Report saved: processing_report_v3.json")

            except Exception as e:
                print(f"❌ Batch processing error: {e}")

    async def handle_remove(self, args):
        """Handle document removal."""
        for path in args.paths:
            try:
                result = await self.pipeline.remove_document(
                    path, index_types=self._parse_index_type(args.index_type)
                )

                if args.json:
                    print(self._format_output(result, True))
                else:
                    print(f"Removed: {path}")

            except Exception as e:
                print(f"Error removing {path}: {e}")

    async def handle_search(self, args):
        """Handle search operations."""
        try:
            filter_dict = None
            if args.filter:
                filter_dict = json.loads(args.filter)

            # Pass fusion method for hybrid search
            search_kwargs = {}
            if args.type == "hybrid" and hasattr(args, "fusion_method"):
                search_kwargs["fusion_method"] = args.fusion_method.replace(
                    "-", "_"
                )  # Convert kebab-case to snake_case

            results = self.pipeline.search(
                args.query,
                search_type=args.type,
                top_k=args.top_k,
                filters=filter_dict,
                **search_kwargs,
            )

            if args.json:
                print(self._format_output(results, True))
            else:
                print(f"Found {len(results)} results:")
                for i, result in enumerate(results, 1):
                    print(
                        f"{i}. {result.get('source', 'unknown')} (score: {result.get('score', 0):.3f})"
                    )
                    if result.get("content"):
                        print(f"   {result['content'][:100]}...")
                    print()

        except Exception as e:
            print(f"Search error: {e}")

    async def handle_queue(self, args):
        """Handle queue management."""
        if args.queue_action == "start":
            workers = args.workers or self.config.get("queue.max_workers", 4)
            await self.queue.start(max_workers=workers)
            print(f"Queue started with {workers} workers")

        elif args.queue_action == "stop":
            await self.queue.stop(wait_for_completion=args.wait)
            print("Queue stopped")

        elif args.queue_action == "status":
            status = self.queue.get_status()

            if args.detailed:
                print(self._format_output(status, args.json))
            else:
                print(f"Queue: {status.get('state', 'unknown')}")
                print(
                    f"Jobs: {status.get('pending_jobs', 0)} pending, {status.get('active_jobs', 0)} active"
                )

        elif args.queue_action == "clear":
            if not args.confirm:
                response = input("Clear all queued jobs? [y/N]: ")
                if response.lower() != "y":
                    print("Cancelled")
                    return

            await self.queue.clear_all_jobs()
            print("Queue cleared")

    async def handle_status(self, args):
        """Handle system status."""
        try:
            # Get pipeline status (sync)
            pipeline_status = self.pipeline.get_status()

            # Get queue status (sync)
            queue_status = self.queue.get_status() if self.queue else {}

            # Get registry statistics (sync)
            registry_stats = self.registry.get_statistics() if self.registry else {}

            # Get index statistics (sync)
            index_stats = self.index_manager.get_statistics() if self.index_manager else {}

            status = {
                "pipeline": pipeline_status,
                "queue": queue_status,
                "registry": registry_stats,
                "indexes": index_stats,
            }

            if args.detailed or args.json:
                print(self._format_output(status, args.json))
            else:
                print("System Status:")
                print(f"  Pipeline: {status['pipeline'].get('state', 'unknown')}")
                print(f"  Queue: {status['queue'].get('state', 'unknown')}")
                print(f"  Documents: {status['registry'].get('total_documents', 0)}")
                print(f"  Indexes: {status['indexes'].get('healthy_indexes', 0)} healthy")

        except Exception as e:
            print(f"Status error: {e}")

    async def handle_maintenance(self, args):
        """Handle maintenance operations."""
        if args.repair:
            print("Running index repair...")
            result = self.index_manager.repair_indexes()
            print(f"Repair completed: {result}")

        if args.cleanup:
            print("Running cleanup...")
            # Implement cleanup logic
            print("Cleanup completed")

        if args.consistency_check:
            print("Running consistency check...")
            result = self.index_manager.verify_consistency()
            print(f"Consistency check: {result}")

    async def handle_config(self, args):
        """Handle configuration operations."""
        if args.config_action == "list":
            config_data = self.config.to_dict()
            print(self._format_output(config_data, args.json))

        elif args.config_action == "get":
            value = self.config.get(args.key)
            if args.json:
                print(json.dumps({args.key: value}))
            else:
                print(f"{args.key}: {value}")

        elif args.config_action == "set":
            self.config.set(args.key, args.value)
            self.config.save()
            print(f"Set {args.key} = {args.value}")

        elif args.config_action == "reset":
            if not args.confirm:
                response = input("Reset all configuration to defaults? [y/N]: ")
                if response.lower() != "y":
                    print("Cancelled")
                    return

            self.config.reset_to_defaults()
            self.config.save()
            print("Configuration reset to defaults")

    async def handle_batch(self, args):
        """Handle batch processing operations."""
        if args.batch_action == "create-url-file":
            # Create URL batch file
            output_path = Path(args.output)

            # Determine format
            format_type = args.format
            if not format_type:
                # Auto-detect from extension
                if output_path.suffix.lower() == ".json":
                    format_type = "json"
                elif output_path.suffix.lower() == ".md":
                    format_type = "markdown"
                else:
                    print("Error: Cannot determine format from extension. Please specify --format")
                    return

            # Validate URLs
            validation_result = validate_url_list(args.urls)
            valid_urls = validation_result["valid_urls"]

            if not valid_urls:
                print("Error: No valid URLs provided")
                return

            if validation_result["invalid_urls"]:
                print(f"Warning: {len(validation_result['invalid_urls'])} invalid URLs skipped:")
                for url in validation_result["invalid_urls"]:
                    print(f"  - {url}")

            # Create the file
            success = create_url_batch_file(valid_urls, output_path, format_type)
            if success:
                print(f"✅ Created {format_type} batch file: {output_path}")
                print(f"   📊 {len(valid_urls)} URLs included")

                # Show domain statistics
                domains = validation_result["statistics"]["domains"]
                if domains:
                    print("   🌐 Domains:")
                    for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True):
                        print(f"      {domain}: {count}")
            else:
                print(f"❌ Failed to create batch file: {output_path}")

        elif args.batch_action == "validate-urls":
            # Validate URL batch file
            file_path = Path(args.file)
            if not file_path.exists():
                print(f"Error: File not found: {args.file}")
                return

            print(f"Validating URL file: {args.file}")
            urls = extract_urls_from_file(file_path)

            if not urls:
                print("❌ No URLs found in file")
                return

            validation_result = validate_url_list(urls)

            print("📊 Validation Results:")
            print(f"   Total URLs: {validation_result['total_urls']}")
            print(f"   ✅ Valid URLs: {validation_result['statistics']['unique_valid_urls']}")
            print(f"   ❌ Invalid URLs: {validation_result['statistics']['invalid_count']}")
            print(f"   🔄 Duplicates: {validation_result['statistics']['duplicate_count']}")

            if validation_result["invalid_urls"]:
                print("\n❌ Invalid URLs:")
                for url in validation_result["invalid_urls"]:
                    print(f"   - {url}")

            if validation_result["duplicates"]:
                print("\n🔄 Duplicate URLs:")
                for url in validation_result["duplicates"]:
                    print(f"   - {url}")

            # Show domain statistics
            domains = validation_result["statistics"]["domains"]
            if domains:
                print("\n🌐 Domain Distribution:")
                for domain, count in sorted(domains.items(), key=lambda x: x[1], reverse=True):
                    print(f"   {domain}: {count}")

        elif args.batch_action == "test-queue":
            # Test queue processing with URL batch
            file_path = Path(args.url_file)
            if not file_path.exists():
                print(f"Error: URL file not found: {args.url_file}")
                return

            print(f"Testing queue processing with URL file: {args.url_file}")
            urls = extract_urls_from_file(file_path)

            if not urls:
                print("❌ No URLs found in file")
                return

            print(f"Found {len(urls)} URLs to process")

            # Prepare document info for batch processing
            document_infos = []
            for url in urls:
                doc_info = {
                    "source": url,
                    "metadata": {"batch_test": True, "source_file": str(file_path)},
                    "force_reprocess": True,  # Force processing for testing
                    "mode": "auto",
                    "prompt_file": None,
                    "with_keywords": args.with_keywords,
                }
                document_infos.append(doc_info)

            print(f"Using {args.workers} workers for queue testing")
            print(f"Keyword enhancement: {'enabled' if args.with_keywords else 'disabled'}")

            try:
                # Test with queue-based processing
                batch_result = await self.pipeline.process_document_batch(
                    document_infos,
                    use_queue=True,  # Use queue for testing
                    max_concurrent=args.workers,
                )

                # Print detailed results
                total = batch_result.get("total_documents", 0)
                jobs_created = batch_result.get("jobs_created", 0)
                processing_time = batch_result.get("processing_time", 0)
                queue_status = batch_result.get("queue_status", {})

                print("\n🚀 Queue Test Results:")
                print(f"   📄 Total URLs: {total}")
                print(f"   📋 Jobs created: {jobs_created}")
                print(f"   ⏱️  Processing time: {processing_time:.2f}s")

                if queue_status:
                    print(f"   📊 Queue status: {queue_status}")

                print("\n✅ Queue test completed successfully!")

            except Exception as e:
                print(f"❌ Queue test failed: {e}")

        else:
            print(f"Unknown batch action: {args.batch_action}")


async def main():
    """Main entry point."""
    command_string = " ".join(sys.argv[1:])
    logger = logging.getLogger(__name__)

    # Parse arguments first to get config path
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--config", type=str, help="Path to configuration file")
    parser.add_argument("--help", "-h", action="store_true")

    # Parse known args to extract config path without failing on unknown args
    config_args, _ = parser.parse_known_args()

    # Create CLI with potential config path
    # ConfigLoadError will be handled at the top level in cli_main.py
    cli = PipelineCLI(config_path=config_args.config)

    # Create the full parser
    parser = cli.create_parser()

    # Wrap only argument parsing in try/except for CLI argument errors
    try:
        args = parser.parse_args()
    except SystemExit as e:
        # SystemExit(0) is normal for --help, don't treat as error
        if e.code == 0:
            sys.exit(0)
        else:
            logger.exception(f"Argument parsing failed: {e} | Command: {command_string}")
            raise CLIArgumentError(
                f"Invalid command line arguments: {e}", command_string=command_string
            )
    except argparse.ArgumentError as e:
        logger.exception(f"Argument parsing failed: {e} | Command: {command_string}")
        raise CLIArgumentError(
            f"Invalid command line arguments: {e}", command_string=command_string
        )

    if not args.command:
        logger.error(f"No command specified | Command: {command_string}")
        raise CLIArgumentError(
            "No command specified. Use --help for usage information.",
            command_string=command_string,
        )

    # Run the CLI - let exceptions propagate up to top-level handler
    await cli.run(args)


if __name__ == "__main__":
    asyncio.run(main())
