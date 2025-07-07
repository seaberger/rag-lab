"""
Tenant Management CLI Commands.

This module provides command-line interface for tenant management operations
including creation, configuration, monitoring, and data cleanup.
"""

import json
import sys

from src.pipeline_v3.core.tenant_manager import (
    TenantError,
    TenantManager,
    TenantNotFoundError,
    TenantQuotaExceededError,
)
from src.pipeline_v3.utils.common_utils import logger
from src.pipeline_v3.utils.config import PipelineConfig


class TenantCLI:
    """Command-line interface for tenant management."""

    def __init__(self, config: PipelineConfig):
        """Initialize tenant CLI with configuration."""
        self.config = config

        # Validate PostgreSQL backend
        if self.config.database.backend != "postgresql":
            raise ValueError("Tenant management requires PostgreSQL backend")

    def handle_tenant_command(self, args) -> None:
        """
        Handle tenant management commands.

        Args:
            args: Parsed command line arguments
        """
        try:
            if args.tenant_action == "create":
                self._create_tenant(args)
            elif args.tenant_action == "list":
                self._list_tenants(args)
            elif args.tenant_action == "info":
                self._get_tenant_info(args)
            elif args.tenant_action == "update":
                self._update_tenant(args)
            elif args.tenant_action == "disable":
                self._disable_tenant(args)
            elif args.tenant_action == "stats":
                self._get_tenant_stats(args)
            elif args.tenant_action == "cleanup":
                self._cleanup_tenant(args)
            elif args.tenant_action == "context":
                self._manage_context(args)
            else:
                print(f"Unknown tenant action: {args.tenant_action}")
                return

        except TenantNotFoundError as e:
            logger.error(f"Tenant not found: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        except TenantQuotaExceededError as e:
            logger.error(f"Quota exceeded: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        except TenantError as e:
            logger.error(f"Tenant operation failed: {e}")
            print(f"Error: {e}")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Unexpected error in tenant command: {e}")
            print(f"Unexpected error: {e}")
            sys.exit(1)

    def _create_tenant(self, args) -> None:
        """Create a new tenant."""
        if not args.name:
            print("Error: Tenant name is required")
            sys.exit(1)

        # Parse optional settings from JSON string
        settings = {}
        if hasattr(args, "settings") and args.settings:
            try:
                settings = json.loads(args.settings)
            except json.JSONDecodeError as e:
                print(f"Error: Invalid settings JSON: {e}")
                sys.exit(1)

        with TenantManager(self.config) as manager:
            tenant_id = manager.create_tenant(
                name=args.name,
                display_name=getattr(args, "display_name", None),
                max_documents=getattr(args, "max_documents", 10000),
                max_storage_gb=getattr(args, "max_storage_gb", 100),
                settings=settings if settings else None,
            )

            print(f"✅ Created tenant: {args.name}")
            print(f"   Tenant ID: {tenant_id}")
            print(f"   Display Name: {getattr(args, 'display_name', args.name)}")
            print(f"   Max Documents: {getattr(args, 'max_documents', 10000)}")
            print(f"   Max Storage: {getattr(args, 'max_storage_gb', 100)} GB")

    def _list_tenants(self, args) -> None:
        """List all tenants."""
        with TenantManager(self.config) as manager:
            tenants = manager.list_tenants()

            if not tenants:
                print("No tenants found.")
                return

            # Format output
            if getattr(args, "json", False):
                print(json.dumps(tenants, indent=2, default=str))
            else:
                print(
                    f"{'Name':<20} {'Display Name':<25} {'Status':<12} {'Documents':<10} {'Created'}"
                )
                print("-" * 85)

                for tenant in tenants:
                    print(
                        f"{tenant['name']:<20} "
                        f"{tenant['display_name']:<25} "
                        f"{tenant['status']:<12} "
                        f"{tenant['document_count']:<10} "
                        f"{tenant['created_at'].strftime('%Y-%m-%d')}"
                    )

    def _get_tenant_info(self, args) -> None:
        """Get detailed tenant information."""
        if not args.tenant_id:
            print("Error: Tenant ID is required")
            sys.exit(1)

        with TenantManager(self.config) as manager:
            info = manager.get_tenant_info(args.tenant_id)

            if getattr(args, "json", False):
                print(json.dumps(info, indent=2, default=str))
            else:
                print("Tenant Information:")
                print(f"  ID: {info['tenant_id']}")
                print(f"  Name: {info['name']}")
                print(f"  Display Name: {info['display_name']}")
                print(f"  Status: {info['status']}")
                print(f"  Documents: {info['current_documents']}/{info['max_documents']}")
                print(f"  Storage Limit: {info['max_storage_gb']} GB")
                print(f"  Created: {info['created_at']}")

    def _update_tenant(self, args) -> None:
        """Update tenant settings."""
        if not args.tenant_id:
            print("Error: Tenant ID is required")
            sys.exit(1)

        if not args.settings:
            print("Error: Settings JSON is required")
            sys.exit(1)

        try:
            settings = json.loads(args.settings)
        except json.JSONDecodeError as e:
            print(f"Error: Invalid settings JSON: {e}")
            sys.exit(1)

        with TenantManager(self.config) as manager:
            manager.update_tenant_settings(args.tenant_id, settings)
            print(f"✅ Updated tenant settings for: {args.tenant_id}")

    def _disable_tenant(self, args) -> None:
        """Disable a tenant."""
        if not args.tenant_id:
            print("Error: Tenant ID is required")
            sys.exit(1)

        # Confirmation for safety
        if not getattr(args, "force", False):
            response = input(f"Are you sure you want to disable tenant {args.tenant_id}? (y/N): ")
            if response.lower() != "y":
                print("Operation cancelled.")
                return

        with TenantManager(self.config) as manager:
            manager.disable_tenant(args.tenant_id)
            print(f"✅ Disabled tenant: {args.tenant_id}")

    def _get_tenant_stats(self, args) -> None:
        """Get tenant statistics."""
        if not args.tenant_id:
            print("Error: Tenant ID is required")
            sys.exit(1)

        with TenantManager(self.config) as manager:
            stats = manager.get_tenant_statistics(args.tenant_id)

            if getattr(args, "json", False):
                print(json.dumps(stats, indent=2, default=str))
            else:
                print(f"Tenant Statistics for: {stats['tenant_info']['name']}")
                print(f"  Documents: {stats['tenant_info']['current_documents']}")

                print("\n  Index Statistics:")
                for idx_stat in stats["index_statistics"]:
                    print(
                        f"    {idx_stat['index_type'].title()}: "
                        f"{idx_stat['total_entries']} entries, "
                        f"{idx_stat['unique_documents']} documents, "
                        f"{idx_stat['avg_chunks_per_doc']:.1f} avg chunks/doc"
                    )

                print("\n  Job Queue:")
                job_stats = stats["job_statistics"]
                print(f"    Total: {job_stats['total_jobs']}")
                print(f"    Pending: {job_stats['pending_jobs']}")
                print(f"    Processing: {job_stats['processing_jobs']}")
                print(f"    Completed: {job_stats['completed_jobs']}")
                print(f"    Failed: {job_stats['failed_jobs']}")

    def _cleanup_tenant(self, args) -> None:
        """Clean up tenant data."""
        if not args.tenant_id:
            print("Error: Tenant ID is required")
            sys.exit(1)

        dry_run = not getattr(args, "execute", False)

        if not dry_run:
            # Confirmation for actual cleanup
            response = input(
                f"Are you sure you want to cleanup data for tenant {args.tenant_id}? (y/N): "
            )
            if response.lower() != "y":
                print("Operation cancelled.")
                return

        with TenantManager(self.config) as manager:
            report = manager.cleanup_tenant_data(args.tenant_id, dry_run=dry_run)

            if getattr(args, "json", False):
                print(json.dumps(report, indent=2, default=str))
            else:
                print(f"Tenant Cleanup {'Report' if dry_run else 'Results'}: {args.tenant_id}")
                print(f"  Mode: {'Dry Run' if dry_run else 'Execute'}")

                for operation in report["operations"]:
                    if dry_run:
                        if "would_delete" in operation:
                            print(
                                f"  Would delete {operation['would_delete']} orphaned index entries"
                            )
                    elif "deleted_count" in operation:
                        print(f"  Deleted {operation['deleted_count']} orphaned index entries")

    def _manage_context(self, args) -> None:
        """Manage tenant context."""
        with TenantManager(self.config) as manager:
            if hasattr(args, "set_tenant") and args.set_tenant:
                manager.set_tenant_context(args.set_tenant)
                print(f"✅ Set tenant context to: {args.set_tenant}")
            elif hasattr(args, "clear") and args.clear:
                manager.clear_tenant_context()
                print("✅ Cleared tenant context")
            else:
                # Show current context
                current = manager.get_current_tenant_id()
                if current:
                    print(f"Current tenant context: {current}")
                else:
                    print("No tenant context set (using default tenant)")


def add_tenant_subcommands(subparsers):
    """Add tenant management subcommands to argument parser."""
    tenant_parser = subparsers.add_parser("tenant", help="Tenant management commands")
    tenant_subparsers = tenant_parser.add_subparsers(dest="tenant_action", help="Tenant actions")

    # Create tenant
    create_parser = tenant_subparsers.add_parser("create", help="Create a new tenant")
    create_parser.add_argument("name", help="Tenant name (unique identifier)")
    create_parser.add_argument("--display-name", help="Human-readable display name")
    create_parser.add_argument(
        "--max-documents", type=int, default=10000, help="Maximum documents allowed"
    )
    create_parser.add_argument(
        "--max-storage-gb", type=int, default=100, help="Maximum storage in GB"
    )
    create_parser.add_argument("--settings", help="Additional settings as JSON string")

    # List tenants
    list_parser = tenant_subparsers.add_parser("list", help="List all tenants")
    list_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Get tenant info
    info_parser = tenant_subparsers.add_parser("info", help="Get tenant information")
    info_parser.add_argument("tenant_id", help="Tenant ID")
    info_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Update tenant
    update_parser = tenant_subparsers.add_parser("update", help="Update tenant settings")
    update_parser.add_argument("tenant_id", help="Tenant ID")
    update_parser.add_argument("settings", help="Settings to update as JSON string")

    # Disable tenant
    disable_parser = tenant_subparsers.add_parser("disable", help="Disable a tenant")
    disable_parser.add_argument("tenant_id", help="Tenant ID")
    disable_parser.add_argument("--force", action="store_true", help="Skip confirmation")

    # Get tenant statistics
    stats_parser = tenant_subparsers.add_parser("stats", help="Get tenant statistics")
    stats_parser.add_argument("tenant_id", help="Tenant ID")
    stats_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Cleanup tenant
    cleanup_parser = tenant_subparsers.add_parser("cleanup", help="Clean up tenant data")
    cleanup_parser.add_argument("tenant_id", help="Tenant ID")
    cleanup_parser.add_argument(
        "--execute", action="store_true", help="Actually perform cleanup (default is dry run)"
    )
    cleanup_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # Manage context
    context_parser = tenant_subparsers.add_parser("context", help="Manage tenant context")
    context_group = context_parser.add_mutually_exclusive_group()
    context_group.add_argument("--set", dest="set_tenant", help="Set tenant context")
    context_group.add_argument("--clear", action="store_true", help="Clear tenant context")

    return tenant_parser
