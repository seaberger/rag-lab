"""
Pool monitoring commands for Pipeline v3 CLI.

Provides commands to monitor and manage PostgreSQL connection pools.
"""

import time
from pathlib import Path

import typer
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.pipeline_v3.core.tenant_connection_manager import get_tenant_connection_manager
from src.pipeline_v3.core.tenant_pool_monitor import get_pool_monitor
from src.pipeline_v3.utils.config import PipelineConfig

app = typer.Typer(help="Connection pool monitoring commands")
console = Console()


@app.command()
def status(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    watch: bool = typer.Option(
        False, "--watch", "-w", help="Watch mode - continuously update status"
    ),
    interval: int = typer.Option(
        5, "--interval", "-i", help="Update interval in seconds (watch mode only)"
    ),
):
    """Show connection pool status and metrics."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Pool monitoring requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get connection manager and monitor
        connection_manager = get_tenant_connection_manager(config)
        monitor = get_pool_monitor(connection_manager, config)

        def generate_status_display():
            """Generate status display for current state."""
            summary = monitor.get_monitoring_summary()

            # Overall status panel
            overall = summary["overall_metrics"]
            status_color = "green"
            if overall["critical_pools"] > 0:
                status_color = "red"
            elif overall["degraded_pools"] > 0:
                status_color = "yellow"

            status_text = f"""[bold]Connection Pool Status[/bold]
Total Pools: {overall["total_pools"]}
Healthy: [green]{overall["healthy_pools"]}[/green] | Degraded: [yellow]{overall["degraded_pools"]}[/yellow] | Critical: [red]{overall["critical_pools"]}[/red]
Connection Utilization: {overall["connection_utilization"]:.1f}%
Average Pool Age: {overall["average_pool_age_hours"]:.1f} hours"""

            status_panel = Panel(
                status_text,
                title="System Status",
                border_style=status_color,
            )

            # Tenant metrics table
            tenant_table = Table(title="Tenant Metrics")
            tenant_table.add_column("Tenant ID", style="cyan")
            tenant_table.add_column("Pools", justify="right")
            tenant_table.add_column("Utilization", justify="right")
            tenant_table.add_column("Health", justify="center")

            for tenant_metric in summary["tenant_metrics"]:
                health_style = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(
                    tenant_metric["health_status"], "white"
                )

                tenant_table.add_row(
                    tenant_metric["tenant_id"],
                    str(tenant_metric["pool_count"]),
                    f"{tenant_metric['utilization_percent']:.1f}%",
                    Text(tenant_metric["health_status"].upper(), style=health_style),
                )

            # Alerts summary
            alert_summary = summary["alert_summary"]
            alerts_text = f"""Active Alerts: {alert_summary["active_alerts"]}
Recent Alerts (4h): {alert_summary["recent_alerts"]}
Critical: {alert_summary["alert_types"].get("critical", 0)} | Degraded: {alert_summary["alert_types"].get("degraded", 0)}"""

            alerts_panel = Panel(
                alerts_text,
                title="Alert Summary",
                border_style="yellow" if alert_summary["active_alerts"] > 0 else "green",
            )

            # Performance trends (if available)
            trends_content = "No trend data available"
            if summary.get("performance_trends"):
                trends = summary["performance_trends"]
                if "utilization_trend" in trends:
                    util_trend = trends["utilization_trend"]
                    trend_direction = (
                        "↗️"
                        if util_trend["change_percent"] > 5
                        else "↘️"
                        if util_trend["change_percent"] < -5
                        else "➡️"
                    )
                    trends_content = f"""Utilization Trend: {trend_direction} {util_trend["change_percent"]:+.1f}%
Current Hour: {util_trend["current_hour_avg"]:.1f}%
Previous Hour: {util_trend["previous_hour_avg"]:.1f}%"""

            trends_panel = Panel(
                trends_content,
                title="Performance Trends",
                border_style="blue",
            )

            # Combine all displays
            from rich.columns import Columns
            from rich.console import Group

            display = Group(
                status_panel,
                "",
                Columns([tenant_table, alerts_panel], equal=True),
                "",
                trends_panel,
                "",
                Text(f"Last updated: {time.strftime('%Y-%m-%d %H:%M:%S')}", style="dim"),
            )

            return display

        if watch:
            # Watch mode - continuous updates
            with Live(generate_status_display(), refresh_per_second=4, console=console) as live:
                try:
                    while True:
                        time.sleep(interval)
                        live.update(generate_status_display())
                except KeyboardInterrupt:
                    console.print("\n[yellow]Monitoring stopped[/yellow]")
        else:
            # Single status display
            console.print(generate_status_display())

    except Exception as e:
        console.print(f"[red]❌ Status command failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def health(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    detailed: bool = typer.Option(
        False, "--detailed", "-d", help="Show detailed health check results"
    ),
):
    """Perform health check on all connection pools."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Pool monitoring requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get connection manager and monitor
        connection_manager = get_tenant_connection_manager(config)
        monitor = get_pool_monitor(connection_manager, config)

        console.print("[bold]Running connection pool health check...[/bold]")

        # Perform health check
        health_results = monitor.check_pool_health()

        # Display overall status
        overall_status = health_results["overall_status"]
        status_color = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(
            overall_status, "white"
        )

        status_text = f"Overall Status: [{status_color}]{overall_status.upper()}[/{status_color}]"
        console.print(Panel(status_text, title="Health Check Results"))

        # Show monitoring metrics
        monitoring = health_results["monitoring_metrics"]
        metrics_table = Table(title="Pool Metrics")
        metrics_table.add_column("Metric", style="cyan")
        metrics_table.add_column("Value", justify="right")

        metrics_table.add_row("Total Pools", str(monitoring["total_pools"]))
        metrics_table.add_row("Healthy Pools", f"[green]{monitoring['healthy_pools']}[/green]")
        metrics_table.add_row(
            "Connection Utilization", f"{monitoring['connection_utilization']:.1f}%"
        )
        metrics_table.add_row(
            "Active Alerts",
            f"[red]{monitoring['active_alerts']}[/red]" if monitoring["active_alerts"] > 0 else "0",
        )

        console.print(metrics_table)

        # Show detailed results if requested
        if detailed and "pool_details" in health_results:
            details_table = Table(title="Pool Details")
            details_table.add_column("Tenant", style="cyan")
            details_table.add_column("Schema", style="cyan")
            details_table.add_column("Status", justify="center")
            details_table.add_column("Connectivity", justify="center")
            details_table.add_column("Response Time", justify="right")
            details_table.add_column("Age", justify="right")

            for pool in health_results["pool_details"]:
                status_style = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(
                    pool["status"], "white"
                )

                connectivity_style = {"ok": "green", "failed": "red", "pool_missing": "yellow"}.get(
                    pool.get("connectivity", "unknown"), "white"
                )

                response_time = pool.get("response_time")
                response_str = f"{response_time * 1000:.1f}ms" if response_time else "N/A"

                age_hours = pool.get("age_seconds", 0) / 3600
                age_str = f"{age_hours:.1f}h"

                details_table.add_row(
                    pool["tenant_id"],
                    pool["schema"],
                    Text(pool["status"].upper(), style=status_style),
                    Text(pool.get("connectivity", "unknown").upper(), style=connectivity_style),
                    response_str,
                    age_str,
                )

            console.print(details_table)

        # Show recommendations
        if health_results.get("recommendations"):
            console.print("\n[bold]Recommendations:[/bold]")
            for rec in health_results["recommendations"]:
                if rec.startswith("CRITICAL"):
                    console.print(f"[red]• {rec}[/red]")
                elif rec.startswith("WARNING"):
                    console.print(f"[yellow]• {rec}[/yellow]")
                else:
                    console.print(f"[blue]• {rec}[/blue]")

        # Show issues
        if health_results.get("issues"):
            console.print("\n[red]Issues detected:[/red]")
            for issue in health_results["issues"]:
                console.print(f"[red]• {issue}[/red]")

        # Exit with appropriate code
        if overall_status == "critical":
            raise typer.Exit(2)
        if overall_status == "degraded":
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]❌ Health check failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def alerts(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    active_only: bool = typer.Option(
        False, "--active-only", "-a", help="Show only active (unresolved) alerts"
    ),
    last_hours: int = typer.Option(24, "--last-hours", "-h", help="Show alerts from last N hours"),
):
    """Show connection pool alerts."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Pool monitoring requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get connection manager and monitor
        connection_manager = get_tenant_connection_manager(config)
        monitor = get_pool_monitor(connection_manager, config)

        # Filter alerts
        cutoff_time = time.time() - (last_hours * 3600)
        alerts = [
            alert
            for alert in monitor.alerts
            if alert.timestamp > cutoff_time and (not active_only or not alert.resolved)
        ]

        if not alerts:
            filter_desc = "active " if active_only else f"from last {last_hours} hours "
            console.print(f"[green]✅ No {filter_desc}alerts found[/green]")
            return

        # Display alerts table
        alerts_table = Table(title=f"Connection Pool Alerts ({len(alerts)} found)")
        alerts_table.add_column("Time", style="dim")
        alerts_table.add_column("Tenant", style="cyan")
        alerts_table.add_column("Schema", style="cyan")
        alerts_table.add_column("Type", justify="center")
        alerts_table.add_column("Message")
        alerts_table.add_column("Status", justify="center")
        alerts_table.add_column("Duration", justify="right")

        for alert in sorted(alerts, key=lambda a: a.timestamp, reverse=True):
            alert_time = time.strftime("%H:%M:%S", time.localtime(alert.timestamp))

            type_style = {"critical": "red", "degraded": "yellow", "recovery": "green"}.get(
                alert.alert_type, "white"
            )

            status_text = "Resolved" if alert.resolved else "Active"
            status_style = "green" if alert.resolved else "red"

            # Calculate duration
            end_time = alert.resolution_time if alert.resolved else time.time()
            duration_seconds = end_time - alert.timestamp

            if duration_seconds < 60:
                duration_str = f"{duration_seconds:.0f}s"
            elif duration_seconds < 3600:
                duration_str = f"{duration_seconds / 60:.1f}m"
            else:
                duration_str = f"{duration_seconds / 3600:.1f}h"

            alerts_table.add_row(
                alert_time,
                alert.tenant_id,
                alert.schema,
                Text(alert.alert_type.upper(), style=type_style),
                alert.message,
                Text(status_text, style=status_style),
                duration_str,
            )

        console.print(alerts_table)

        # Summary
        active_count = sum(1 for a in alerts if not a.resolved)
        resolved_count = sum(1 for a in alerts if a.resolved)

        summary_text = (
            f"Active: [red]{active_count}[/red] | Resolved: [green]{resolved_count}[/green]"
        )
        console.print(Panel(summary_text, title="Alert Summary"))

    except Exception as e:
        console.print(f"[red]❌ Alerts command failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def tenant(
    tenant_id: str = typer.Argument(help="Tenant ID to monitor"),
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
):
    """Show detailed metrics for a specific tenant."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Pool monitoring requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get connection manager and monitor
        connection_manager = get_tenant_connection_manager(config)
        monitor = get_pool_monitor(connection_manager, config)

        # Get tenant metrics
        tenant_metrics = monitor.get_tenant_metrics(tenant_id)

        if not tenant_metrics:
            console.print(f"[red]❌ No pools found for tenant: {tenant_id}[/red]")
            raise typer.Exit(1)

        tenant_metric = tenant_metrics[0]  # Should be only one for specific tenant

        # Display tenant overview
        overview_text = f"""[bold]Tenant: {tenant_metric.tenant_id}[/bold]
Total Pools: {tenant_metric.pool_count}
Total Connections: {tenant_metric.total_connections}
Active Connections: {tenant_metric.active_connections}
Utilization: {tenant_metric.utilization_percent:.1f}%

Pool Health:
  Healthy: [green]{tenant_metric.healthy_pools}[/green]
  Degraded: [yellow]{tenant_metric.degraded_pools}[/yellow]
  Critical: [red]{tenant_metric.critical_pools}[/red]

Pool Ages:
  Oldest: {tenant_metric.oldest_pool_age / 3600:.1f} hours
  Newest: {tenant_metric.newest_pool_age / 3600:.1f} hours"""

        console.print(Panel(overview_text, title=f"Tenant Overview: {tenant_id}"))

        # Show individual pool details
        pool_metrics = connection_manager.get_pool_metrics(tenant_id)

        if pool_metrics:
            details_table = Table(title="Individual Pool Details")
            details_table.add_column("Schema", style="cyan")
            details_table.add_column("Health", justify="center")
            details_table.add_column("Total Conn.", justify="right")
            details_table.add_column("Active Conn.", justify="right")
            details_table.add_column("Idle Conn.", justify="right")
            details_table.add_column("Utilization", justify="right")
            details_table.add_column("Age", justify="right")
            details_table.add_column("Last Activity", justify="right")

            current_time = time.time()
            for pool in pool_metrics:
                health_style = {"healthy": "green", "degraded": "yellow", "critical": "red"}.get(
                    pool.pool_health, "white"
                )

                utilization = (
                    (pool.active_connections / pool.total_connections * 100)
                    if pool.total_connections > 0
                    else 0
                )
                age_hours = (current_time - pool.created_at) / 3600
                last_activity_mins = (current_time - pool.last_activity) / 60

                details_table.add_row(
                    pool.pool_name,
                    Text(pool.pool_health.upper(), style=health_style),
                    str(pool.total_connections),
                    str(pool.active_connections),
                    str(pool.idle_connections),
                    f"{utilization:.1f}%",
                    f"{age_hours:.1f}h",
                    f"{last_activity_mins:.1f}m",
                )

            console.print(details_table)

    except Exception as e:
        console.print(f"[red]❌ Tenant command failed: {e!s}[/red]")
        raise typer.Exit(1)


def add_pool_monitor_subcommands(subparsers):
    """Add pool monitoring commands to argument parser."""
    monitor_parser = subparsers.add_parser(
        "pool-monitor", help="Connection pool monitoring commands"
    )
    monitor_subparsers = monitor_parser.add_subparsers(
        dest="monitor_action", help="Monitoring actions"
    )

    # Status command
    status_parser = monitor_subparsers.add_parser("status", help="Show pool status")
    status_parser.add_argument("--config-file", help="Path to configuration file")
    status_parser.add_argument("--watch", action="store_true", help="Watch mode")
    status_parser.add_argument(
        "--interval", type=int, default=5, help="Update interval for watch mode"
    )

    # Health command
    health_parser = monitor_subparsers.add_parser("health", help="Perform health check")
    health_parser.add_argument("--config-file", help="Path to configuration file")
    health_parser.add_argument("--detailed", action="store_true", help="Show detailed results")

    # Alerts command
    alerts_parser = monitor_subparsers.add_parser("alerts", help="Show alerts")
    alerts_parser.add_argument("--config-file", help="Path to configuration file")
    alerts_parser.add_argument("--active-only", action="store_true", help="Show only active alerts")
    alerts_parser.add_argument(
        "--last-hours", type=int, default=24, help="Show alerts from last N hours"
    )

    # Tenant command
    tenant_parser = monitor_subparsers.add_parser("tenant", help="Show tenant metrics")
    tenant_parser.add_argument("tenant_id", help="Tenant ID to monitor")
    tenant_parser.add_argument("--config-file", help="Path to configuration file")

    return monitor_parser


if __name__ == "__main__":
    app()
