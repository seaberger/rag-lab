"""
Connection Pool Monitoring and Health Checks for PostgreSQL.

This module provides comprehensive monitoring capabilities for tenant connection pools,
including real-time metrics collection, alerting, and automated health checks.
"""

import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.tenant_connection_manager import TenantConnectionManager

from utils.common_utils import logger
from utils.config import PipelineConfig


@dataclass
class PoolAlert:
    """Represents a pool health alert."""

    tenant_id: str
    schema: str
    alert_type: str  # 'degraded', 'critical', 'recovery'
    message: str
    timestamp: float
    resolved: bool = False
    resolution_time: float | None = None


@dataclass
class MonitoringMetrics:
    """Aggregated monitoring metrics."""

    timestamp: float
    total_pools: int
    healthy_pools: int
    degraded_pools: int
    critical_pools: int
    total_connections: int
    active_connections: int
    average_pool_age: float
    connection_utilization: float
    alerts_active: int
    alerts_resolved_last_hour: int
    tenant_pool_distribution: Dict[str, int] = field(default_factory=dict)


@dataclass
class TenantMetrics:
    """Per-tenant aggregated metrics."""

    tenant_id: str
    pool_count: int
    total_connections: int
    active_connections: int
    healthy_pools: int
    degraded_pools: int
    critical_pools: int
    utilization_percent: float
    oldest_pool_age: float
    newest_pool_age: float


class TenantPoolMonitor:
    """
    Advanced monitoring system for tenant connection pools.

    Provides real-time monitoring, alerting, and health check capabilities
    for PostgreSQL connection pools across multiple tenants.
    """

    def __init__(self, connection_manager: TenantConnectionManager, config: PipelineConfig):
        """
        Initialize pool monitor.

        Args:
            connection_manager: Tenant connection manager to monitor
            config: Pipeline configuration
        """
        self.connection_manager = connection_manager
        self.config = config

        # Monitoring configuration
        self.monitoring_interval = 30  # seconds
        self.alert_retention_hours = 24
        self.degraded_threshold = 0.8  # 80% utilization
        self.critical_threshold = 0.95  # 95% utilization

        # State tracking
        self.alerts: List[PoolAlert] = []
        self.metrics_history: List[MonitoringMetrics] = []
        self.last_health_check = 0.0
        self.health_check_interval = 60  # seconds

        # Alert tracking by pool
        self.active_alerts: Dict[str, PoolAlert] = {}  # pool_key -> alert

        logger.info("TenantPoolMonitor initialized")

    def collect_metrics(self) -> MonitoringMetrics:
        """
        Collect comprehensive metrics from all pools.

        Returns:
            Aggregated monitoring metrics
        """
        current_time = time.time()
        pool_metrics = self.connection_manager.get_pool_metrics()

        if not pool_metrics:
            return MonitoringMetrics(
                timestamp=current_time,
                total_pools=0,
                healthy_pools=0,
                degraded_pools=0,
                critical_pools=0,
                total_connections=0,
                active_connections=0,
                average_pool_age=0.0,
                connection_utilization=0.0,
                alerts_active=len([a for a in self.alerts if not a.resolved]),
                alerts_resolved_last_hour=self._count_recent_resolutions(),
            )

        # Aggregate metrics
        total_pools = len(pool_metrics)
        healthy_pools = sum(1 for m in pool_metrics if m.pool_health == "healthy")
        degraded_pools = sum(1 for m in pool_metrics if m.pool_health == "degraded")
        critical_pools = sum(1 for m in pool_metrics if m.pool_health == "critical")

        total_connections = sum(m.total_connections for m in pool_metrics)
        active_connections = sum(m.active_connections for m in pool_metrics)

        # Calculate averages
        pool_ages = [current_time - m.created_at for m in pool_metrics]
        average_pool_age = sum(pool_ages) / len(pool_ages) if pool_ages else 0.0

        connection_utilization = (
            (active_connections / total_connections * 100) if total_connections > 0 else 0.0
        )

        # Tenant distribution
        tenant_distribution = defaultdict(int)
        for metric in pool_metrics:
            tenant_distribution[metric.tenant_id] += 1

        metrics = MonitoringMetrics(
            timestamp=current_time,
            total_pools=total_pools,
            healthy_pools=healthy_pools,
            degraded_pools=degraded_pools,
            critical_pools=critical_pools,
            total_connections=total_connections,
            active_connections=active_connections,
            average_pool_age=average_pool_age,
            connection_utilization=connection_utilization,
            alerts_active=len([a for a in self.alerts if not a.resolved]),
            alerts_resolved_last_hour=self._count_recent_resolutions(),
            tenant_pool_distribution=dict(tenant_distribution),
        )

        # Store in history (keep last 24 hours)
        self.metrics_history.append(metrics)
        self._cleanup_old_metrics()

        return metrics

    def get_tenant_metrics(self, tenant_id: str | None = None) -> List[TenantMetrics]:
        """
        Get detailed metrics for specific tenant(s).

        Args:
            tenant_id: Optional tenant ID filter

        Returns:
            List of tenant metrics
        """
        pool_metrics = self.connection_manager.get_pool_metrics(tenant_id)

        # Group by tenant
        tenant_groups = defaultdict(list)
        for metric in pool_metrics:
            tenant_groups[metric.tenant_id].append(metric)

        tenant_metrics = []
        current_time = time.time()

        for tid, metrics in tenant_groups.items():
            total_connections = sum(m.total_connections for m in metrics)
            active_connections = sum(m.active_connections for m in metrics)

            healthy_count = sum(1 for m in metrics if m.pool_health == "healthy")
            degraded_count = sum(1 for m in metrics if m.pool_health == "degraded")
            critical_count = sum(1 for m in metrics if m.pool_health == "critical")

            utilization = (
                (active_connections / total_connections * 100) if total_connections > 0 else 0.0
            )

            pool_ages = [current_time - m.created_at for m in metrics]
            oldest_age = max(pool_ages) if pool_ages else 0.0
            newest_age = min(pool_ages) if pool_ages else 0.0

            tenant_metrics.append(
                TenantMetrics(
                    tenant_id=tid,
                    pool_count=len(metrics),
                    total_connections=total_connections,
                    active_connections=active_connections,
                    healthy_pools=healthy_count,
                    degraded_pools=degraded_count,
                    critical_pools=critical_count,
                    utilization_percent=utilization,
                    oldest_pool_age=oldest_age,
                    newest_pool_age=newest_age,
                )
            )

        return tenant_metrics

    def check_pool_health(self) -> Dict[str, Any]:
        """
        Perform comprehensive health check on all pools.

        Returns:
            Health check results with recommendations
        """
        current_time = time.time()

        # Skip if too soon since last check
        if current_time - self.last_health_check < self.health_check_interval:
            return {"status": "skipped", "reason": "too_soon"}

        self.last_health_check = current_time

        # Get health check from connection manager
        health_results = self.connection_manager.health_check()

        # Analyze results and generate alerts
        self._analyze_health_results(health_results)

        # Add monitoring analysis
        metrics = self.collect_metrics()

        # Generate recommendations
        recommendations = self._generate_recommendations(metrics, health_results)

        health_results.update(
            {
                "monitoring_metrics": {
                    "total_pools": metrics.total_pools,
                    "healthy_pools": metrics.healthy_pools,
                    "connection_utilization": metrics.connection_utilization,
                    "active_alerts": metrics.alerts_active,
                },
                "recommendations": recommendations,
                "last_check": current_time,
            }
        )

        return health_results

    def _analyze_health_results(self, health_results: Dict[str, Any]):
        """Analyze health results and generate alerts."""
        current_time = time.time()

        for pool_detail in health_results.get("pool_details", []):
            tenant_id = pool_detail["tenant_id"]
            schema = pool_detail["schema"]
            pool_key = f"{tenant_id}:{schema}"

            status = pool_detail["status"]
            connectivity = pool_detail.get("connectivity", "unknown")

            # Check for alert conditions
            alert_type = None
            message = ""

            if connectivity == "failed":
                alert_type = "critical"
                message = f"Connection failed: {pool_detail.get('error', 'Unknown error')}"
            elif status == "critical":
                alert_type = "critical"
                message = "Pool health is critical"
            elif status == "degraded":
                alert_type = "degraded"
                message = "Pool health is degraded"
            elif status == "healthy" and pool_key in self.active_alerts:
                # Recovery from previous alert
                self._resolve_alert(pool_key, current_time)
                continue

            if alert_type:
                self._create_or_update_alert(tenant_id, schema, alert_type, message, current_time)

    def _create_or_update_alert(
        self, tenant_id: str, schema: str, alert_type: str, message: str, timestamp: float
    ):
        """Create or update an alert for a pool."""
        pool_key = f"{tenant_id}:{schema}"

        # Check if we already have an active alert for this pool
        if pool_key in self.active_alerts:
            existing_alert = self.active_alerts[pool_key]

            # Update if severity increased
            if alert_type == "critical" and existing_alert.alert_type == "degraded":
                existing_alert.alert_type = "critical"
                existing_alert.message = message
                existing_alert.timestamp = timestamp
                logger.warning(f"Alert escalated for pool {pool_key}: {message}")

            return  # Don't create duplicate alerts

        # Create new alert
        alert = PoolAlert(
            tenant_id=tenant_id,
            schema=schema,
            alert_type=alert_type,
            message=message,
            timestamp=timestamp,
        )

        self.alerts.append(alert)
        self.active_alerts[pool_key] = alert

        log_level = logger.error if alert_type == "critical" else logger.warning
        log_level(f"Pool alert [{alert_type.upper()}] for {pool_key}: {message}")

    def _resolve_alert(self, pool_key: str, resolution_time: float):
        """Resolve an active alert."""
        if pool_key in self.active_alerts:
            alert = self.active_alerts[pool_key]
            alert.resolved = True
            alert.resolution_time = resolution_time

            del self.active_alerts[pool_key]

            logger.info(
                f"Alert resolved for pool {pool_key} after "
                f"{resolution_time - alert.timestamp:.1f} seconds"
            )

    def _generate_recommendations(
        self, metrics: MonitoringMetrics, health_results: Dict[str, Any]
    ) -> List[str]:
        """Generate operational recommendations based on metrics."""
        recommendations = []

        # High utilization warning
        if metrics.connection_utilization > self.critical_threshold * 100:
            recommendations.append(
                f"CRITICAL: Connection utilization at {metrics.connection_utilization:.1f}% - "
                "consider increasing pool sizes or adding more pools"
            )
        elif metrics.connection_utilization > self.degraded_threshold * 100:
            recommendations.append(
                f"WARNING: Connection utilization at {metrics.connection_utilization:.1f}% - "
                "monitor closely and consider scaling"
            )

        # Pool health issues
        if metrics.critical_pools > 0:
            recommendations.append(
                f"CRITICAL: {metrics.critical_pools} pools in critical state - "
                "immediate attention required"
            )

        if metrics.degraded_pools > 0:
            recommendations.append(
                f"WARNING: {metrics.degraded_pools} pools degraded - investigate connection issues"
            )

        # Active alerts
        if metrics.alerts_active > 0:
            recommendations.append(
                f"ATTENTION: {metrics.alerts_active} active alerts - review and resolve issues"
            )

        # Pool distribution imbalance
        if len(metrics.tenant_pool_distribution) > 1:
            pool_counts = list(metrics.tenant_pool_distribution.values())
            max_pools = max(pool_counts)
            min_pools = min(pool_counts)

            if max_pools > min_pools * 3:  # 3x imbalance
                recommendations.append(
                    "INFO: Uneven pool distribution across tenants - "
                    "consider rebalancing for optimal performance"
                )

        # Connection efficiency
        if metrics.total_connections > 0 and metrics.connection_utilization < 10:
            recommendations.append(
                "INFO: Low connection utilization - consider reducing pool sizes to free resources"
            )

        return recommendations

    def _count_recent_resolutions(self) -> int:
        """Count alerts resolved in the last hour."""
        cutoff_time = time.time() - 3600  # 1 hour ago

        return sum(
            1
            for alert in self.alerts
            if alert.resolved and alert.resolution_time and alert.resolution_time > cutoff_time
        )

    def _cleanup_old_metrics(self):
        """Remove old metrics to prevent memory buildup."""
        cutoff_time = time.time() - (24 * 3600)  # 24 hours ago

        self.metrics_history = [m for m in self.metrics_history if m.timestamp > cutoff_time]

    def _cleanup_old_alerts(self):
        """Remove old resolved alerts."""
        cutoff_time = time.time() - (self.alert_retention_hours * 3600)

        self.alerts = [
            alert
            for alert in self.alerts
            if not alert.resolved or (alert.resolution_time and alert.resolution_time > cutoff_time)
        ]

    def get_monitoring_summary(self) -> Dict[str, Any]:
        """Get comprehensive monitoring summary."""
        metrics = self.collect_metrics()
        tenant_metrics = self.get_tenant_metrics()

        # Recent alerts (last 4 hours)
        recent_cutoff = time.time() - (4 * 3600)
        recent_alerts = [alert for alert in self.alerts if alert.timestamp > recent_cutoff]

        return {
            "timestamp": metrics.timestamp,
            "overall_metrics": {
                "total_pools": metrics.total_pools,
                "healthy_pools": metrics.healthy_pools,
                "degraded_pools": metrics.degraded_pools,
                "critical_pools": metrics.critical_pools,
                "connection_utilization": metrics.connection_utilization,
                "average_pool_age_hours": metrics.average_pool_age / 3600,
            },
            "tenant_metrics": [
                {
                    "tenant_id": tm.tenant_id,
                    "pool_count": tm.pool_count,
                    "utilization_percent": tm.utilization_percent,
                    "health_status": "healthy"
                    if tm.critical_pools == 0 and tm.degraded_pools == 0
                    else "critical"
                    if tm.critical_pools > 0
                    else "degraded",
                }
                for tm in tenant_metrics
            ],
            "alert_summary": {
                "active_alerts": len(self.active_alerts),
                "recent_alerts": len(recent_alerts),
                "alert_types": {
                    alert_type: len([a for a in recent_alerts if a.alert_type == alert_type])
                    for alert_type in ["critical", "degraded", "recovery"]
                },
            },
            "performance_trends": self._calculate_trends() if len(self.metrics_history) > 1 else {},
        }

    def _calculate_trends(self) -> Dict[str, Any]:
        """Calculate performance trends from historical data."""
        if len(self.metrics_history) < 2:
            return {}

        # Compare last hour vs previous hour
        current_time = time.time()
        one_hour_ago = current_time - 3600
        two_hours_ago = current_time - 7200

        recent_metrics = [m for m in self.metrics_history if m.timestamp > one_hour_ago]

        previous_metrics = [
            m for m in self.metrics_history if two_hours_ago < m.timestamp <= one_hour_ago
        ]

        if not recent_metrics or not previous_metrics:
            return {}

        # Calculate averages
        recent_avg_util = sum(m.connection_utilization for m in recent_metrics) / len(
            recent_metrics
        )
        previous_avg_util = sum(m.connection_utilization for m in previous_metrics) / len(
            previous_metrics
        )

        recent_avg_pools = sum(m.total_pools for m in recent_metrics) / len(recent_metrics)
        previous_avg_pools = sum(m.total_pools for m in previous_metrics) / len(previous_metrics)

        return {
            "utilization_trend": {
                "current_hour_avg": recent_avg_util,
                "previous_hour_avg": previous_avg_util,
                "change_percent": ((recent_avg_util - previous_avg_util) / previous_avg_util * 100)
                if previous_avg_util > 0
                else 0,
            },
            "pool_count_trend": {
                "current_hour_avg": recent_avg_pools,
                "previous_hour_avg": previous_avg_pools,
                "change_absolute": recent_avg_pools - previous_avg_pools,
            },
        }

    def cleanup(self):
        """Cleanup old data and resolve stale alerts."""
        self._cleanup_old_metrics()
        self._cleanup_old_alerts()

        logger.info(
            f"Monitoring cleanup completed. "
            f"Metrics: {len(self.metrics_history)}, "
            f"Alerts: {len(self.alerts)}, "
            f"Active: {len(self.active_alerts)}"
        )


# Global monitor instance
_pool_monitor: TenantPoolMonitor | None = None


def get_pool_monitor(
    connection_manager: TenantConnectionManager | None = None, config: PipelineConfig | None = None
) -> TenantPoolMonitor:
    """
    Get the global pool monitor instance.

    Args:
        connection_manager: Required for first call
        config: Required for first call

    Returns:
        TenantPoolMonitor instance
    """
    global _pool_monitor

    if _pool_monitor is None:
        if connection_manager is None or config is None:
            raise ValueError("connection_manager and config required for first call")

        _pool_monitor = TenantPoolMonitor(connection_manager, config)

    return _pool_monitor


def close_pool_monitor():
    """Close the global pool monitor."""
    global _pool_monitor

    if _pool_monitor:
        _pool_monitor.cleanup()
        _pool_monitor = None
