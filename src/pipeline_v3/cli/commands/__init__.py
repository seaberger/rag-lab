"""
CLI command modules for Pipeline v3.
"""

# Import only existing modules - avoid importing non-existent functions
try:
    from .migrate import add_migrate_subcommands
    from .tenant import TenantCLI, add_tenant_subcommands

    __all__ = ["TenantCLI", "add_migrate_subcommands", "add_tenant_subcommands"]
except ImportError:
    __all__ = []
