"""
Per-Tenant Connection Pool Manager for PostgreSQL.

This module provides advanced connection pooling with per-tenant isolation,
connection pool monitoring, and automatic pool management for enterprise
multi-tenant PostgreSQL deployments.
"""

import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.postgres_base import PostgreSQLBase, PostgreSQLConnectionError

from utils.common_utils import logger
from utils.config import PipelineConfig, PostgreSQLSettings


@dataclass
class PoolMetrics:
    """Metrics for a connection pool."""

    tenant_id: str
    pool_name: str
    created_at: float
    total_connections: int
    active_connections: int
    idle_connections: int
    total_queries: int
    failed_queries: int
    avg_query_time: float
    last_activity: float
    pool_health: str  # 'healthy', 'degraded', 'critical'


@dataclass
class TenantPoolConfig:
    """Configuration for tenant-specific connection pools."""

    tenant_id: str
    min_connections: int = 2
    max_connections: int = 10
    connection_timeout: int = 30
    idle_timeout: int = 300
    max_idle_time: int = 1800  # Auto-close pools idle for 30 minutes
    enable_monitoring: bool = True


class TenantConnectionManager:
    """
    Manages per-tenant connection pools with monitoring and health checks.

    Provides advanced connection pooling features:
    - Per-tenant isolated connection pools
    - Automatic pool creation and cleanup
    - Connection pool monitoring and health checks
    - Resource optimization and scaling
    """

    def __init__(self, config: PipelineConfig):
        """
        Initialize tenant connection manager.

        Args:
            config: Pipeline configuration with PostgreSQL settings
        """
        self.config = config

        if not hasattr(config, "database") or config.database.backend != "postgresql":
            raise ValueError("TenantConnectionManager requires PostgreSQL backend")

        self.pg_settings = config.database.postgresql

        # Pool management
        self._pools: Dict[str, Dict[str, PostgreSQLBase]] = defaultdict(dict)
        self._pool_configs: Dict[str, TenantPoolConfig] = {}
        self._pool_metrics: Dict[str, PoolMetrics] = {}
        self._lock = threading.RLock()

        # Monitoring
        self._monitoring_enabled = True
        self._cleanup_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()

        # Default pool configuration
        self._default_pool_config = TenantPoolConfig(
            tenant_id="default",
            min_connections=self.pg_settings.min_connections,
            max_connections=self.pg_settings.max_connections,
            connection_timeout=self.pg_settings.connection_timeout,
            idle_timeout=self.pg_settings.idle_timeout,
        )

        logger.info("TenantConnectionManager initialized")
        self._start_background_tasks()

    def _start_background_tasks(self):
        """Start background monitoring and cleanup tasks."""
        if self._monitoring_enabled:
            self._cleanup_thread = threading.Thread(
                target=self._background_cleanup, daemon=True, name="TenantPoolCleanup"
            )
            self._cleanup_thread.start()
            logger.info("Started background pool cleanup task")

    def _background_cleanup(self):
        """Background task to cleanup idle pools and update metrics."""
        while not self._shutdown_event.wait(60):  # Check every minute
            try:
                self._cleanup_idle_pools()
                self._update_pool_metrics()
            except Exception as e:
                logger.error(f"Error in background cleanup: {e}")

    def get_pool(
        self, tenant_id: str, schema: str, pool_config: TenantPoolConfig | None = None
    ) -> PostgreSQLBase:
        """
        Get or create a connection pool for a tenant and schema.

        Args:
            tenant_id: Tenant ID
            schema: Database schema name
            pool_config: Optional custom pool configuration

        Returns:
            PostgreSQL base instance with dedicated pool
        """
        pool_key = f"{tenant_id}:{schema}"

        with self._lock:
            # Check if pool already exists
            if tenant_id in self._pools and schema in self._pools[tenant_id]:
                pool = self._pools[tenant_id][schema]
                self._update_last_activity(tenant_id, schema)
                return pool

            # Create new pool
            if not pool_config:
                pool_config = self._get_tenant_config(tenant_id)

            try:
                # Create custom settings for this tenant
                tenant_settings = self._create_tenant_settings(pool_config)

                # Create PostgreSQL base with tenant-specific pool
                pool = PostgreSQLBase(tenant_settings, schema, self.config.database.log_queries)
                pool.initialize()

                # Store pool and configuration
                self._pools[tenant_id][schema] = pool
                self._pool_configs[pool_key] = pool_config

                # Initialize metrics
                self._initialize_pool_metrics(tenant_id, schema, pool_config)

                logger.info(f"Created connection pool for tenant {tenant_id}, schema {schema}")
                return pool

            except Exception as e:
                logger.error(f"Failed to create pool for tenant {tenant_id}: {e}")
                raise PostgreSQLConnectionError(f"Pool creation failed: {e}")

    def _get_tenant_config(self, tenant_id: str) -> TenantPoolConfig:
        """Get configuration for a tenant, with fallback to default."""
        pool_key = f"{tenant_id}:*"  # Wildcard for tenant-level config

        if pool_key in self._pool_configs:
            return self._pool_configs[pool_key]

        # Return default config with tenant ID
        config = TenantPoolConfig(
            tenant_id=tenant_id,
            min_connections=self._default_pool_config.min_connections,
            max_connections=self._default_pool_config.max_connections,
            connection_timeout=self._default_pool_config.connection_timeout,
            idle_timeout=self._default_pool_config.idle_timeout,
        )

        return config

    def _create_tenant_settings(self, pool_config: TenantPoolConfig) -> PostgreSQLSettings:
        """Create PostgreSQL settings for a tenant."""
        # Copy base settings
        settings = PostgreSQLSettings(
            host=self.pg_settings.host,
            port=self.pg_settings.port,
            database=self.pg_settings.database,
            user=self.pg_settings.user,
            password=self.pg_settings.password,
            ssl_mode=self.pg_settings.ssl_mode,
            # Tenant-specific pool settings
            min_connections=pool_config.min_connections,
            max_connections=pool_config.max_connections,
            connection_timeout=pool_config.connection_timeout,
            idle_timeout=pool_config.idle_timeout,
        )

        # Copy schema settings if they exist
        if hasattr(self.pg_settings, "registry_schema"):
            settings.registry_schema = self.pg_settings.registry_schema
        if hasattr(self.pg_settings, "search_schema"):
            settings.search_schema = self.pg_settings.search_schema
        if hasattr(self.pg_settings, "jobs_schema"):
            settings.jobs_schema = self.pg_settings.jobs_schema
        if hasattr(self.pg_settings, "fingerprints_schema"):
            settings.fingerprints_schema = self.pg_settings.fingerprints_schema
        if hasattr(self.pg_settings, "default_tenant_id"):
            settings.default_tenant_id = self.pg_settings.default_tenant_id

        return settings

    def _initialize_pool_metrics(self, tenant_id: str, schema: str, config: TenantPoolConfig):
        """Initialize metrics for a new pool."""
        pool_key = f"{tenant_id}:{schema}"

        self._pool_metrics[pool_key] = PoolMetrics(
            tenant_id=tenant_id,
            pool_name=schema,
            created_at=time.time(),
            total_connections=config.max_connections,
            active_connections=0,
            idle_connections=config.min_connections,
            total_queries=0,
            failed_queries=0,
            avg_query_time=0.0,
            last_activity=time.time(),
            pool_health="healthy",
        )

    def _update_last_activity(self, tenant_id: str, schema: str):
        """Update last activity timestamp for a pool."""
        pool_key = f"{tenant_id}:{schema}"
        if pool_key in self._pool_metrics:
            self._pool_metrics[pool_key].last_activity = time.time()

    def configure_tenant_pool(self, tenant_id: str, pool_config: TenantPoolConfig) -> None:
        """
        Configure connection pool settings for a tenant.

        Args:
            tenant_id: Tenant ID
            pool_config: Pool configuration
        """
        with self._lock:
            pool_key = f"{tenant_id}:*"
            self._pool_configs[pool_key] = pool_config

            # If tenant has existing pools, we might need to recreate them
            # For now, log that new config will apply to new pools
            if tenant_id in self._pools:
                logger.info(
                    f"Pool configuration updated for tenant {tenant_id}. "
                    f"New settings will apply to new pools."
                )

            logger.info(
                f"Configured tenant pool for {tenant_id}: "
                f"min={pool_config.min_connections}, max={pool_config.max_connections}"
            )

    def close_tenant_pools(self, tenant_id: str) -> int:
        """
        Close all pools for a specific tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Number of pools closed
        """
        with self._lock:
            if tenant_id not in self._pools:
                return 0

            closed_count = 0
            schemas = list(self._pools[tenant_id].keys())

            for schema in schemas:
                try:
                    pool = self._pools[tenant_id][schema]
                    pool.close()

                    # Remove from tracking
                    del self._pools[tenant_id][schema]

                    pool_key = f"{tenant_id}:{schema}"
                    if pool_key in self._pool_metrics:
                        del self._pool_metrics[pool_key]

                    closed_count += 1
                    logger.info(f"Closed pool for tenant {tenant_id}, schema {schema}")

                except Exception as e:
                    logger.error(f"Error closing pool for tenant {tenant_id}, schema {schema}: {e}")

            # Clean up tenant entry if empty
            if not self._pools[tenant_id]:
                del self._pools[tenant_id]

            logger.info(f"Closed {closed_count} pools for tenant {tenant_id}")
            return closed_count

    def _cleanup_idle_pools(self):
        """Clean up pools that have been idle for too long."""
        current_time = time.time()
        pools_to_close = []

        with self._lock:
            for pool_key, metrics in self._pool_metrics.items():
                tenant_id, schema = pool_key.split(":", 1)

                # Get idle threshold for this tenant
                config = self._get_tenant_config(tenant_id)
                idle_threshold = config.max_idle_time

                # Check if pool is idle
                idle_time = current_time - metrics.last_activity
                if idle_time > idle_threshold:
                    pools_to_close.append((tenant_id, schema, idle_time))

        # Close idle pools outside the lock
        for tenant_id, schema, idle_time in pools_to_close:
            try:
                with self._lock:
                    if tenant_id in self._pools and schema in self._pools[tenant_id]:
                        pool = self._pools[tenant_id][schema]
                        pool.close()

                        del self._pools[tenant_id][schema]
                        if not self._pools[tenant_id]:
                            del self._pools[tenant_id]

                        pool_key = f"{tenant_id}:{schema}"
                        if pool_key in self._pool_metrics:
                            del self._pool_metrics[pool_key]

                logger.info(
                    f"Closed idle pool for tenant {tenant_id}, schema {schema} "
                    f"(idle for {idle_time:.1f}s)"
                )

            except Exception as e:
                logger.error(f"Error during idle pool cleanup: {e}")

    def _update_pool_metrics(self):
        """Update metrics for all active pools."""
        with self._lock:
            for pool_key, metrics in self._pool_metrics.items():
                tenant_id, schema = pool_key.split(":", 1)

                if tenant_id in self._pools and schema in self._pools[tenant_id]:
                    try:
                        pool = self._pools[tenant_id][schema]

                        # Update basic health status
                        if hasattr(pool, "_sync_pool") and pool._sync_pool:
                            # Pool is healthy if it's initialized and responding
                            try:
                                with pool._sync_pool.connection() as conn:
                                    conn.execute("SELECT 1")
                                metrics.pool_health = "healthy"
                            except Exception:
                                metrics.pool_health = "degraded"
                        else:
                            metrics.pool_health = "critical"

                    except Exception as e:
                        logger.warning(f"Error updating metrics for {pool_key}: {e}")
                        metrics.pool_health = "critical"

    def get_pool_metrics(self, tenant_id: str | None = None) -> List[PoolMetrics]:
        """
        Get metrics for connection pools.

        Args:
            tenant_id: Optional tenant ID to filter by

        Returns:
            List of pool metrics
        """
        with self._lock:
            if tenant_id:
                return [
                    metrics
                    for pool_key, metrics in self._pool_metrics.items()
                    if metrics.tenant_id == tenant_id
                ]
            else:
                return list(self._pool_metrics.values())

    def get_pool_summary(self) -> Dict[str, Any]:
        """
        Get summary of all connection pools.

        Returns:
            Summary statistics
        """
        with self._lock:
            total_pools = len(self._pool_metrics)
            healthy_pools = sum(
                1 for m in self._pool_metrics.values() if m.pool_health == "healthy"
            )
            tenants = len({m.tenant_id for m in self._pool_metrics.values()})

            total_connections = sum(m.total_connections for m in self._pool_metrics.values())
            active_connections = sum(m.active_connections for m in self._pool_metrics.values())

            return {
                "total_pools": total_pools,
                "healthy_pools": healthy_pools,
                "degraded_pools": total_pools - healthy_pools,
                "total_tenants": tenants,
                "total_connections": total_connections,
                "active_connections": active_connections,
                "pool_utilization": (active_connections / total_connections * 100)
                if total_connections > 0
                else 0,
                "pools_by_tenant": {
                    tenant_id: len(
                        [m for m in self._pool_metrics.values() if m.tenant_id == tenant_id]
                    )
                    for tenant_id in {m.tenant_id for m in self._pool_metrics.values()}
                },
            }

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on all pools.

        Returns:
            Health check results
        """
        results = {
            "overall_status": "healthy",
            "timestamp": time.time(),
            "pool_details": [],
            "issues": [],
        }

        with self._lock:
            for pool_key, metrics in self._pool_metrics.items():
                tenant_id, schema = pool_key.split(":", 1)

                pool_result = {
                    "tenant_id": tenant_id,
                    "schema": schema,
                    "status": metrics.pool_health,
                    "last_activity": metrics.last_activity,
                    "age_seconds": time.time() - metrics.created_at,
                }

                # Test pool connectivity
                try:
                    if tenant_id in self._pools and schema in self._pools[tenant_id]:
                        pool = self._pools[tenant_id][schema]
                        start_time = time.time()

                        with pool._sync_pool.connection() as conn:
                            conn.execute("SELECT 1")

                        pool_result["response_time"] = time.time() - start_time
                        pool_result["connectivity"] = "ok"
                    else:
                        pool_result["connectivity"] = "pool_missing"
                        results["issues"].append(f"Pool missing for {tenant_id}:{schema}")

                except Exception as e:
                    pool_result["connectivity"] = "failed"
                    pool_result["error"] = str(e)
                    results["issues"].append(f"Connection failed for {tenant_id}:{schema}: {e}")

                    if results["overall_status"] == "healthy":
                        results["overall_status"] = "degraded"

                results["pool_details"].append(pool_result)

        # Determine overall status
        if results["issues"]:
            critical_issues = [issue for issue in results["issues"] if "failed" in issue.lower()]
            if critical_issues:
                results["overall_status"] = "critical"
            elif results["overall_status"] == "healthy":
                results["overall_status"] = "degraded"

        return results

    def close_all(self):
        """Close all connection pools and stop background tasks."""
        logger.info("Closing all tenant connection pools...")

        # Stop background tasks
        if self._cleanup_thread:
            self._shutdown_event.set()
            self._cleanup_thread.join(timeout=5)

        # Close all pools
        with self._lock:
            total_closed = 0
            for tenant_id in list(self._pools.keys()):
                closed_count = self.close_tenant_pools(tenant_id)
                total_closed += closed_count

            # Clear all tracking
            self._pools.clear()
            self._pool_metrics.clear()
            self._pool_configs.clear()

        logger.info(f"Closed {total_closed} connection pools")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close_all()


# Singleton instance for global access
_tenant_connection_manager: TenantConnectionManager | None = None
_manager_lock = threading.Lock()


def get_tenant_connection_manager(config: PipelineConfig | None = None) -> TenantConnectionManager:
    """
    Get the global tenant connection manager instance.

    Args:
        config: Pipeline configuration (required for first call)

    Returns:
        TenantConnectionManager instance
    """
    global _tenant_connection_manager

    with _manager_lock:
        if _tenant_connection_manager is None:
            if config is None:
                config = PipelineConfig()
            _tenant_connection_manager = TenantConnectionManager(config)

        return _tenant_connection_manager


def close_global_connection_manager():
    """Close the global connection manager."""
    global _tenant_connection_manager

    with _manager_lock:
        if _tenant_connection_manager:
            _tenant_connection_manager.close_all()
            _tenant_connection_manager = None
