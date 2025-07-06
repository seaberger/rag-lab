"""
CLI command modules for Pipeline v3.
"""

# Import only existing modules - avoid importing non-existent functions
try:
    from .migrate import add_migrate_subcommands
    from .performance import add_performance_subcommands
    from .pool_monitor import add_pool_monitor_subcommands
    from .tenant import TenantCLI, add_tenant_subcommands

    __all__ = [
        "TenantCLI",
        "add_migrate_subcommands",
        "add_performance_subcommands",
        "add_pool_monitor_subcommands",
        "add_tenant_subcommands",
    ]
except ImportError:
    __all__ = []
