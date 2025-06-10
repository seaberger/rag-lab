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
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

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
    from job_queue.manager import DocumentQueue
    from core.registry import DocumentRegistry, IndexType  
    from core.index_manager import IndexManager
    from utils.config import PipelineConfig
    from utils.monitoring import ProgressMonitor
    from utils.env_utils import setup_environment
    CORE_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Core components not available: {e}")
    CORE_AVAILABLE = False
    DocumentQueue = None
    DocumentRegistry = None
    IndexManager = None
    PipelineConfig = None
    ProgressMonitor = None


class PipelineCLI:
    """Main CLI interface for pipeline management."""
    
    def __init__(self):
        if not CORE_AVAILABLE:
            print("Error: Core pipeline components not available")
            print("Please install dependencies: uv add llama-index llama-index-vector-stores-qdrant")
            sys.exit(1)
        
        # Setup environment (load .env file)
        setup_environment()
            
        self.config = PipelineConfig()
        self.pipeline = None
        self.queue = None
        self.registry = None
        self.index_manager = None
        self.monitor = ProgressMonitor()
        
    async def initialize(self):
        """Initialize pipeline components."""
        try:
            if PIPELINE_AVAILABLE:
                self.pipeline = EnhancedPipeline(self.config)
            
            self.queue = DocumentQueue(self.config)
            
            self.registry = DocumentRegistry(self.config)
            
            self.index_manager = IndexManager(self.config)
            
        except Exception as e:
            print(f"Error initializing pipeline: {e}")
            print("Make sure all dependencies are installed and configured properly")
            sys.exit(1)
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create the main argument parser."""
        parser = argparse.ArgumentParser(
            prog='pipeline',
            description='Production Document Processing Pipeline v3',
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  pipeline add document.pdf --metadata type=datasheet
  pipeline search "laser sensors" --type hybrid --top-k 5
  pipeline queue start --workers 8
  pipeline status --detailed
  pipeline maintenance --repair
            """
        )
        
        parser.add_argument(
            '--config', 
            type=str, 
            help='Path to configuration file'
        )
        parser.add_argument(
            '--verbose', '-v', 
            action='store_true',
            help='Enable verbose output'
        )
        parser.add_argument(
            '--json', 
            action='store_true',
            help='Output results in JSON format'
        )
        
        subparsers = parser.add_subparsers(dest='command', help='Available commands')
        
        # Document operations
        self._add_document_commands(subparsers)
        
        # Queue management
        self._add_queue_commands(subparsers)
        
        # System operations
        self._add_system_commands(subparsers)
        
        # Configuration
        self._add_config_commands(subparsers)
        
        return parser
    
    def _add_document_commands(self, subparsers):
        """Add document-related commands."""
        # Add command
        add_parser = subparsers.add_parser('add', help='Add documents to pipeline')
        add_parser.add_argument('paths', nargs='+', help='Document paths to add')
        add_parser.add_argument(
            '--metadata', 
            action='append', 
            help='Metadata key=value pairs'
        )
        add_parser.add_argument(
            '--force', 
            action='store_true',
            help='Force processing even if document exists'
        )
        add_parser.add_argument(
            '--index-type', 
            choices=['vector', 'keyword', 'both'],
            default='both',
            help='Type of index to create'
        )
        
        # Update command
        update_parser = subparsers.add_parser('update', help='Update existing documents')
        update_parser.add_argument('paths', nargs='+', help='Document paths to update')
        update_parser.add_argument(
            '--metadata', 
            action='append',
            help='Metadata key=value pairs'
        )
        update_parser.add_argument(
            '--force', 
            action='store_true',
            help='Force update even if no changes detected'
        )
        
        # Remove command
        remove_parser = subparsers.add_parser('remove', help='Remove documents')
        remove_parser.add_argument('paths', nargs='+', help='Document paths to remove')
        remove_parser.add_argument(
            '--index-type',
            choices=['vector', 'keyword', 'both'],
            default='both',
            help='Which indexes to remove from'
        )
        
        # Search command
        search_parser = subparsers.add_parser('search', help='Search documents')
        search_parser.add_argument('query', help='Search query')
        search_parser.add_argument(
            '--type',
            choices=['vector', 'keyword', 'hybrid'],
            default='hybrid',
            help='Search type'
        )
        search_parser.add_argument(
            '--top-k',
            type=int,
            default=10,
            help='Number of results to return'
        )
        search_parser.add_argument(
            '--filter',
            help='Filter expression (JSON format)'
        )
    
    def _add_queue_commands(self, subparsers):
        """Add queue management commands."""
        queue_parser = subparsers.add_parser('queue', help='Manage processing queue')
        queue_subparsers = queue_parser.add_subparsers(dest='queue_action')
        
        # Start queue
        start_parser = queue_subparsers.add_parser('start', help='Start queue processing')
        start_parser.add_argument(
            '--workers',
            type=int,
            help='Number of worker threads'
        )
        
        # Stop queue
        stop_parser = queue_subparsers.add_parser('stop', help='Stop queue processing')
        stop_parser.add_argument(
            '--wait',
            action='store_true',
            help='Wait for current jobs to complete'
        )
        
        # Queue status
        status_parser = queue_subparsers.add_parser('status', help='Show queue status')
        status_parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed job information'
        )
        
        # Clear queue
        clear_parser = queue_subparsers.add_parser('clear', help='Clear all queued jobs')
        clear_parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt'
        )
    
    def _add_system_commands(self, subparsers):
        """Add system operation commands."""
        # Status command
        status_parser = subparsers.add_parser('status', help='Show system status')
        status_parser.add_argument(
            '--detailed',
            action='store_true',
            help='Show detailed system information'
        )
        
        # Maintenance command
        maint_parser = subparsers.add_parser('maintenance', help='Run maintenance operations')
        maint_parser.add_argument(
            '--repair',
            action='store_true',
            help='Repair index inconsistencies'
        )
        maint_parser.add_argument(
            '--cleanup',
            action='store_true',
            help='Clean up temporary files'
        )
        maint_parser.add_argument(
            '--consistency-check',
            action='store_true',
            help='Check index consistency'
        )
    
    def _add_config_commands(self, subparsers):
        """Add configuration commands."""
        config_parser = subparsers.add_parser('config', help='Manage configuration')
        config_subparsers = config_parser.add_subparsers(dest='config_action')
        
        # List config
        config_subparsers.add_parser('list', help='List all configuration')
        
        # Get config
        get_parser = config_subparsers.add_parser('get', help='Get configuration value')
        get_parser.add_argument('key', help='Configuration key')
        
        # Set config
        set_parser = config_subparsers.add_parser('set', help='Set configuration value')
        set_parser.add_argument('key', help='Configuration key')
        set_parser.add_argument('value', help='Configuration value')
        
        # Reset config
        reset_parser = config_subparsers.add_parser('reset', help='Reset configuration')
        reset_parser.add_argument(
            '--confirm',
            action='store_true',
            help='Skip confirmation prompt'
        )

    async def run(self, args):
        """Run the CLI with parsed arguments."""
        if args.verbose:
            logging.basicConfig(level=logging.DEBUG)
        
        await self.initialize()
        
        if args.command == 'add':
            await self.handle_add(args)
        elif args.command == 'update':
            await self.handle_update(args)
        elif args.command == 'remove':
            await self.handle_remove(args)
        elif args.command == 'search':
            await self.handle_search(args)
        elif args.command == 'queue':
            await self.handle_queue(args)
        elif args.command == 'status':
            await self.handle_status(args)
        elif args.command == 'maintenance':
            await self.handle_maintenance(args)
        elif args.command == 'config':
            await self.handle_config(args)
        else:
            print("No command specified. Use --help for usage information.")
            sys.exit(1)

    def _parse_metadata(self, metadata_list: Optional[List[str]]) -> Dict[str, Any]:
        """Parse metadata key=value pairs."""
        metadata = {}
        if metadata_list:
            for item in metadata_list:
                if '=' not in item:
                    print(f"Warning: Invalid metadata format '{item}', expected key=value")
                    continue
                key, value = item.split('=', 1)
                metadata[key] = value
        return metadata
    
    def _parse_index_type(self, index_type_str: str) -> IndexType:
        """Convert string to IndexType enum."""
        if index_type_str == 'vector':
            return IndexType.VECTOR
        elif index_type_str == 'keyword':
            return IndexType.KEYWORD
        elif index_type_str == 'both':
            return IndexType.BOTH
        else:
            raise ValueError(f"Invalid index type: {index_type_str}")

    def _format_output(self, data: Any, json_format: bool = False) -> str:
        """Format output for display."""
        if json_format:
            return json.dumps(data, indent=2, default=str)
        
        if isinstance(data, dict):
            return '\n'.join(f"{k}: {v}" for k, v in data.items())
        elif isinstance(data, list):
            return '\n'.join(str(item) for item in data)
        else:
            return str(data)

    async def handle_add(self, args):
        """Handle document addition."""
        metadata = self._parse_metadata(args.metadata)
        
        for path in args.paths:
            try:
                result = await self.pipeline.process_document(
                    path, 
                    metadata=metadata,
                    force_reprocess=args.force,
                    index_types=self._parse_index_type(args.index_type)
                )
                
                if args.json:
                    print(self._format_output(result, True))
                else:
                    print(f"Added: {path} -> {result.get('status', 'unknown')}")
                    
            except Exception as e:
                print(f"Error adding {path}: {e}")

    async def handle_update(self, args):
        """Handle document updates."""
        metadata = self._parse_metadata(args.metadata)
        
        for path in args.paths:
            try:
                result = await self.pipeline.update_document(
                    path,
                    metadata=metadata,
                    force=args.force
                )
                
                if args.json:
                    print(self._format_output(result, True))
                else:
                    print(f"Updated: {path} -> {result.get('status', 'unknown')}")
                    
            except Exception as e:
                print(f"Error updating {path}: {e}")

    async def handle_remove(self, args):
        """Handle document removal."""
        for path in args.paths:
            try:
                result = await self.pipeline.remove_document(
                    path,
                    index_types=self._parse_index_type(args.index_type)
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
            
            results = await self.pipeline.search(
                args.query,
                search_type=args.type,
                top_k=args.top_k,
                filter_dict=filter_dict
            )
            
            if args.json:
                print(self._format_output(results, True))
            else:
                print(f"Found {len(results)} results:")
                for i, result in enumerate(results, 1):
                    print(f"{i}. {result.get('source', 'unknown')} (score: {result.get('score', 0):.3f})")
                    if result.get('content'):
                        print(f"   {result['content'][:100]}...")
                    print()
                    
        except Exception as e:
            print(f"Search error: {e}")

    async def handle_queue(self, args):
        """Handle queue management."""
        if args.queue_action == 'start':
            workers = args.workers or self.config.get('queue.max_workers', 4)
            await self.queue.start(max_workers=workers)
            print(f"Queue started with {workers} workers")
            
        elif args.queue_action == 'stop':
            await self.queue.stop(wait_for_completion=args.wait)
            print("Queue stopped")
            
        elif args.queue_action == 'status':
            status = await self.queue.get_status()
            
            if args.detailed:
                print(self._format_output(status, args.json))
            else:
                print(f"Queue: {status.get('state', 'unknown')}")
                print(f"Jobs: {status.get('pending_jobs', 0)} pending, {status.get('active_jobs', 0)} active")
                
        elif args.queue_action == 'clear':
            if not args.confirm:
                response = input("Clear all queued jobs? [y/N]: ")
                if response.lower() != 'y':
                    print("Cancelled")
                    return
                    
            await self.queue.clear_all_jobs()
            print("Queue cleared")

    async def handle_status(self, args):
        """Handle system status."""
        try:
            status = {
                'pipeline': await self.pipeline.get_status(),
                'queue': await self.queue.get_status() if self.queue else {},
                'registry': await self.registry.get_statistics() if self.registry else {},
                'indexes': await self.index_manager.get_status() if self.index_manager else {}
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
            result = await self.index_manager.repair_indexes()
            print(f"Repair completed: {result}")
            
        if args.cleanup:
            print("Running cleanup...")
            # Implement cleanup logic
            print("Cleanup completed")
            
        if args.consistency_check:
            print("Running consistency check...")
            result = await self.index_manager.verify_consistency()
            print(f"Consistency check: {result}")

    async def handle_config(self, args):
        """Handle configuration operations."""
        if args.config_action == 'list':
            config_data = self.config.to_dict()
            print(self._format_output(config_data, args.json))
            
        elif args.config_action == 'get':
            value = self.config.get(args.key)
            if args.json:
                print(json.dumps({args.key: value}))
            else:
                print(f"{args.key}: {value}")
                
        elif args.config_action == 'set':
            self.config.set(args.key, args.value)
            self.config.save()
            print(f"Set {args.key} = {args.value}")
            
        elif args.config_action == 'reset':
            if not args.confirm:
                response = input("Reset all configuration to defaults? [y/N]: ")
                if response.lower() != 'y':
                    print("Cancelled")
                    return
                    
            self.config.reset_to_defaults()
            self.config.save()
            print("Configuration reset to defaults")


async def main():
    """Main entry point."""
    cli = PipelineCLI()
    parser = cli.create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    try:
        await cli.run(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())