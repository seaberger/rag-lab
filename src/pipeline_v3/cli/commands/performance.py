"""
Performance optimization commands for Pipeline v3 CLI.

Provides commands to analyze and optimize PostgreSQL performance.
"""

import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from core.postgres_performance import get_performance_optimizer

from utils.config import PipelineConfig

app = typer.Typer(help="PostgreSQL performance optimization commands")
console = Console()


@app.command()
def analyze(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", "-t", help="Analyze performance for specific tenant"
    ),
    output_file: Path | None = typer.Option(
        None, "--output", "-o", help="Save detailed report to file"
    ),
):
    """Analyze PostgreSQL performance and generate recommendations."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Performance analysis requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get performance optimizer
        optimizer = get_performance_optimizer(config)

        console.print("[bold]Running PostgreSQL performance analysis...[/bold]")

        # Perform analysis
        with console.status("Analyzing database performance..."):
            report = optimizer.analyze_performance(tenant_id)

        # Display overview
        overview_text = f"""[bold]Performance Analysis Results[/bold]
Database Size: {report.database_size_mb:.1f} MB
Connections: {report.active_connections}/{report.connection_count}
Cache Hit Ratio: {report.cache_hit_ratio:.1%}
Slow Queries: {len(report.slow_queries)}
Index Recommendations: {len(report.index_recommendations)}"""

        cache_color = (
            "green"
            if report.cache_hit_ratio > 0.95
            else "yellow"
            if report.cache_hit_ratio > 0.90
            else "red"
        )
        overview_panel = Panel(
            overview_text, title="Performance Overview", border_style=cache_color
        )
        console.print(overview_panel)

        # Show slow queries
        if report.slow_queries:
            console.print("\n[bold red]Slow Queries Detected:[/bold red]")

            slow_table = Table()
            slow_table.add_column("Query", style="cyan", max_width=60)
            slow_table.add_column("Avg Time", justify="right")
            slow_table.add_column("Executions", justify="right")
            slow_table.add_column("Total Time", justify="right")
            slow_table.add_column("Suggestions", max_width=40)

            for query in report.slow_queries[:10]:  # Show top 10
                suggestions_text = "; ".join(
                    query.optimization_suggestions[:2]
                )  # First 2 suggestions
                if len(query.optimization_suggestions) > 2:
                    suggestions_text += f" (+{len(query.optimization_suggestions) - 2} more)"

                slow_table.add_row(
                    query.query_signature,
                    f"{query.average_time_ms:.1f}ms",
                    f"{query.execution_count:,}",
                    f"{query.total_time_ms:.1f}ms",
                    suggestions_text,
                )

            console.print(slow_table)

        # Show index recommendations
        if report.index_recommendations:
            console.print("\n[bold blue]Index Recommendations:[/bold blue]")

            index_table = Table()
            index_table.add_column("Table", style="cyan")
            index_table.add_column("Columns")
            index_table.add_column("Type", justify="center")
            index_table.add_column("Benefit", justify="center")
            index_table.add_column("Size", justify="right")
            index_table.add_column("Reason", max_width=50)

            for rec in report.index_recommendations:
                benefit_style = {"high": "green", "medium": "yellow", "low": "blue"}.get(
                    rec.estimated_benefit, "white"
                )

                index_table.add_row(
                    rec.table_name,
                    ", ".join(rec.columns),
                    rec.index_type.upper(),
                    Text(rec.estimated_benefit.upper(), style=benefit_style),
                    f"{rec.estimated_size_mb:.1f}MB",
                    rec.reason,
                )

            console.print(index_table)

        # Show configuration suggestions
        if report.configuration_suggestions:
            console.print("\n[bold yellow]Configuration Suggestions:[/bold yellow]")
            for suggestion in report.configuration_suggestions:
                console.print(f"[yellow]• {suggestion}[/yellow]")

        # Show maintenance recommendations
        if report.maintenance_recommendations:
            console.print("\n[bold magenta]Maintenance Recommendations:[/bold magenta]")
            for suggestion in report.maintenance_recommendations:
                console.print(f"[magenta]• {suggestion}[/magenta]")

        # Save detailed report if requested
        if output_file:
            _save_detailed_report(report, output_file, tenant_id)
            console.print(f"\n[green]✅ Detailed report saved to: {output_file}[/green]")

        # Summary and next steps
        console.print("\n[bold]Next Steps:[/bold]")
        if report.slow_queries:
            console.print("[red]1. Address slow queries using the optimization suggestions[/red]")
        if report.index_recommendations:
            console.print("[blue]2. Create recommended indexes during low-traffic periods[/blue]")
            console.print("[blue]   Use: performance create-indexes --help[/blue]")
        if report.configuration_suggestions:
            console.print("[yellow]3. Review and apply configuration changes[/yellow]")
        if report.maintenance_recommendations:
            console.print("[magenta]4. Schedule recommended maintenance tasks[/magenta]")

        if not any(
            [
                report.slow_queries,
                report.index_recommendations,
                report.configuration_suggestions,
                report.maintenance_recommendations,
            ]
        ):
            console.print("[green]✅ No major performance issues detected![/green]")

    except Exception as e:
        console.print(f"[red]❌ Performance analysis failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def create_indexes(
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", "-t", help="Generate indexes for specific tenant"
    ),
    benefit_filter: str = typer.Option(
        "all", "--benefit", "-b", help="Filter by benefit level (high/medium/low/all)"
    ),
    output_file: Path | None = typer.Option(
        None, "--output", "-o", help="Save SQL statements to file"
    ),
    execute: bool = typer.Option(
        False, "--execute", help="Execute index creation (DANGEROUS - use with caution)"
    ),
):
    """Generate SQL statements to create recommended indexes."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Index creation requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get performance optimizer and run analysis
        optimizer = get_performance_optimizer(config)

        console.print("[bold]Analyzing database for index recommendations...[/bold]")

        with console.status("Generating index recommendations..."):
            report = optimizer.analyze_performance(tenant_id)

        # Filter recommendations by benefit level
        recommendations = report.index_recommendations
        if benefit_filter != "all":
            recommendations = [r for r in recommendations if r.estimated_benefit == benefit_filter]

        if not recommendations:
            filter_msg = f" with {benefit_filter} benefit" if benefit_filter != "all" else ""
            console.print(f"[green]✅ No index recommendations found{filter_msg}[/green]")
            return

        # Generate SQL statements
        sql_statements = optimizer.create_performance_indexes(recommendations)

        # Display recommendations
        console.print(f"\n[bold]Found {len(recommendations)} index recommendations:[/bold]")

        rec_table = Table()
        rec_table.add_column("Table", style="cyan")
        rec_table.add_column("Columns")
        rec_table.add_column("Benefit", justify="center")
        rec_table.add_column("Size", justify="right")
        rec_table.add_column("SQL Statement", max_width=60)

        for rec in recommendations:
            benefit_style = {"high": "green", "medium": "yellow", "low": "blue"}.get(
                rec.estimated_benefit, "white"
            )

            rec_table.add_row(
                rec.table_name,
                ", ".join(rec.columns),
                Text(rec.estimated_benefit.upper(), style=benefit_style),
                f"{rec.estimated_size_mb:.1f}MB",
                rec.create_statement,
            )

        console.print(rec_table)

        # Show SQL statements
        console.print("\n[bold]Generated SQL Statements:[/bold]")
        sql_text = "\\n".join(sql_statements)
        console.print(Panel(sql_text, title="Index Creation SQL", expand=False))

        # Save to file if requested
        if output_file:
            output_file.write_text("\\n".join(sql_statements))
            console.print(f"\\n[green]✅ SQL statements saved to: {output_file}[/green]")

        # Execute warning
        if execute:
            if not typer.confirm(
                "\\n[red]WARNING: This will execute index creation statements. "
                "This can take significant time and resources. Continue?[/red]"
            ):
                console.print("[yellow]Index creation cancelled[/yellow]")
                return

            console.print(
                "[red]Index execution not implemented for safety. "
                "Please review and execute SQL statements manually.[/red]"
            )
        else:
            console.print(
                "\\n[yellow]⚠️  Review these statements carefully before execution.[/yellow]"
            )
            console.print(
                "[yellow]   Index creation can take significant time and resources.[/yellow]"
            )
            console.print("[yellow]   Execute during low-traffic periods.[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Index generation failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def query_plan(
    query: str = typer.Argument(help="SQL query to analyze"),
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
    tenant_id: str | None = typer.Option(
        None, "--tenant-id", "-t", help="Analyze query in context of specific tenant"
    ),
):
    """Analyze execution plan for a specific query."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Query plan analysis requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get performance optimizer
        optimizer = get_performance_optimizer(config)

        console.print("[bold]Analyzing query execution plan...[/bold]")
        console.print(f"[dim]Query: {query[:100]}{'...' if len(query) > 100 else ''}[/dim]")

        # Analyze query plan
        with console.status("Getting query execution plan..."):
            analysis = optimizer.get_query_plan_analysis(query, tenant_id)

        if "error" in analysis:
            console.print(f"[red]❌ Query analysis failed: {analysis['error']}[/red]")
            raise typer.Exit(1)

        # Display results
        timing_text = f"""[bold]Query Execution Analysis[/bold]
Execution Time: {analysis["execution_time_ms"]:.1f}ms
Planning Time: {analysis["planning_time_ms"]:.1f}ms
Total Cost: {analysis["total_cost"]:.1f}
Estimated Rows: {analysis["rows_estimated"]:,}
Actual Rows: {analysis["rows_actual"]:,}"""

        # Color based on execution time
        timing_color = (
            "green"
            if analysis["execution_time_ms"] < 100
            else "yellow"
            if analysis["execution_time_ms"] < 1000
            else "red"
        )
        timing_panel = Panel(timing_text, title="Execution Metrics", border_style=timing_color)
        console.print(timing_panel)

        # Show optimization opportunities
        if analysis["optimization_opportunities"]:
            console.print("\\n[bold red]Optimization Opportunities:[/bold red]")
            for opportunity in analysis["optimization_opportunities"]:
                console.print(f"[red]• {opportunity}[/red]")
        else:
            console.print("\\n[green]✅ No obvious optimization opportunities detected[/green]")

        # Buffer analysis (if available)
        if analysis["buffers_hit"] or analysis["buffers_read"]:
            buffer_hit_ratio = analysis["buffers_hit"] / (
                analysis["buffers_hit"] + analysis["buffers_read"]
            )
            buffer_text = f"Buffer Hit Ratio: {buffer_hit_ratio:.1%}"
            buffer_color = (
                "green"
                if buffer_hit_ratio > 0.95
                else "yellow"
                if buffer_hit_ratio > 0.90
                else "red"
            )
            console.print(f"\\n[{buffer_color}]{buffer_text}[/{buffer_color}]")

        # Recommendations
        console.print("\\n[bold]Recommendations:[/bold]")
        if analysis["execution_time_ms"] > 1000:
            console.print("[red]• Query is slow (>1s) - consider optimization[/red]")

        if analysis["rows_estimated"] != analysis["rows_actual"] and analysis["rows_estimated"] > 0:
            estimation_ratio = analysis["rows_actual"] / analysis["rows_estimated"]
            if estimation_ratio < 0.1 or estimation_ratio > 10:
                console.print(
                    "[yellow]• Row estimation is poor - consider running ANALYZE[/yellow]"
                )

        if analysis["total_cost"] > 10000:
            console.print("[yellow]• High query cost - review for efficiency[/yellow]")

        console.print(
            "[blue]• Use EXPLAIN (ANALYZE, BUFFERS, VERBOSE) for more detailed analysis[/blue]"
        )

    except Exception as e:
        console.print(f"[red]❌ Query plan analysis failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def optimize_query(
    query: str = typer.Argument(help="SQL query to optimize"),
    config_file: Path | None = typer.Option(
        None, "--config", "-c", help="Path to configuration file"
    ),
):
    """Get optimization suggestions for a specific query."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        if config.database.backend != "postgresql":
            console.print("[red]❌ Query optimization requires PostgreSQL backend[/red]")
            raise typer.Exit(1)

        # Get performance optimizer
        optimizer = get_performance_optimizer(config)

        console.print("[bold]Analyzing query for optimization opportunities...[/bold]")
        console.print(f"[dim]Query: {query}[/dim]")

        # Optimize query
        optimizations = optimizer.optimize_queries([query])
        suggestions = optimizations.get(query, [])

        if suggestions:
            console.print("\\n[bold green]Optimization Suggestions:[/bold green]")
            for i, suggestion in enumerate(suggestions, 1):
                console.print(f"[green]{i}. {suggestion}[/green]")
        else:
            console.print("\\n[green]✅ No specific optimization suggestions found[/green]")

        # General best practices
        console.print("\\n[bold blue]General Best Practices:[/bold blue]")
        console.print("[blue]• Use EXPLAIN ANALYZE to understand query execution[/blue]")
        console.print("[blue]• Ensure appropriate indexes exist for WHERE clauses[/blue]")
        console.print("[blue]• Consider query rewriting for better performance[/blue]")
        console.print("[blue]• Use LIMIT when possible to reduce result set size[/blue]")
        console.print("[blue]• Avoid functions in WHERE clauses when possible[/blue]")

    except Exception as e:
        console.print(f"[red]❌ Query optimization failed: {e!s}[/red]")
        raise typer.Exit(1)


def _save_detailed_report(report, output_file: Path, tenant_id: str | None):
    """Save detailed performance report to file."""
    content = []
    content.append("# PostgreSQL Performance Analysis Report")
    content.append(f"Generated: {report.timestamp}")
    if tenant_id:
        content.append(f"Tenant: {tenant_id}")
    content.append("")

    content.append("## Overview")
    content.append(f"- Database Size: {report.database_size_mb:.1f} MB")
    content.append(f"- Connections: {report.active_connections}/{report.connection_count}")
    content.append(f"- Cache Hit Ratio: {report.cache_hit_ratio:.1%}")
    content.append("")

    if report.slow_queries:
        content.append("## Slow Queries")
        for query in report.slow_queries:
            content.append(f"### Query: {query.query_signature}")
            content.append(f"- Average Time: {query.average_time_ms:.1f}ms")
            content.append(f"- Executions: {query.execution_count:,}")
            content.append(f"- Total Time: {query.total_time_ms:.1f}ms")
            content.append("- Suggestions:")
            for suggestion in query.optimization_suggestions:
                content.append(f"  - {suggestion}")
            content.append("")

    if report.index_recommendations:
        content.append("## Index Recommendations")
        for rec in report.index_recommendations:
            content.append(f"### {rec.table_name} - {', '.join(rec.columns)}")
            content.append(f"- Type: {rec.index_type}")
            content.append(f"- Benefit: {rec.estimated_benefit}")
            content.append(f"- Size: {rec.estimated_size_mb:.1f}MB")
            content.append(f"- Reason: {rec.reason}")
            content.append(f"- SQL: `{rec.create_statement}`")
            content.append("")

    if report.configuration_suggestions:
        content.append("## Configuration Suggestions")
        for suggestion in report.configuration_suggestions:
            content.append(f"- {suggestion}")
        content.append("")

    if report.maintenance_recommendations:
        content.append("## Maintenance Recommendations")
        for suggestion in report.maintenance_recommendations:
            content.append(f"- {suggestion}")
        content.append("")

    output_file.write_text("\\n".join(content))


def add_performance_subcommands(subparsers):
    """Add performance commands to argument parser."""
    perf_parser = subparsers.add_parser(
        "performance", help="PostgreSQL performance optimization commands"
    )
    perf_subparsers = perf_parser.add_subparsers(
        dest="performance_action", help="Performance actions"
    )

    # Analyze command
    analyze_parser = perf_subparsers.add_parser("analyze", help="Analyze database performance")
    analyze_parser.add_argument("--config-file", help="Path to configuration file")
    analyze_parser.add_argument("--tenant-id", help="Analyze specific tenant")
    analyze_parser.add_argument("--output-file", help="Save report to file")

    # Create indexes command
    indexes_parser = perf_subparsers.add_parser(
        "create-indexes", help="Generate index creation SQL"
    )
    indexes_parser.add_argument("--config-file", help="Path to configuration file")
    indexes_parser.add_argument("--tenant-id", help="Generate for specific tenant")
    indexes_parser.add_argument(
        "--benefit",
        choices=["high", "medium", "low", "all"],
        default="all",
        help="Filter by benefit level",
    )
    indexes_parser.add_argument("--output-file", help="Save SQL to file")
    indexes_parser.add_argument("--execute", action="store_true", help="Execute index creation")

    # Query plan command
    plan_parser = perf_subparsers.add_parser("query-plan", help="Analyze query execution plan")
    plan_parser.add_argument("query", help="SQL query to analyze")
    plan_parser.add_argument("--config-file", help="Path to configuration file")
    plan_parser.add_argument("--tenant-id", help="Analyze in tenant context")

    # Optimize query command
    optimize_parser = perf_subparsers.add_parser(
        "optimize-query", help="Get query optimization suggestions"
    )
    optimize_parser.add_argument("query", help="SQL query to optimize")
    optimize_parser.add_argument("--config-file", help="Path to configuration file")

    return perf_parser


if __name__ == "__main__":
    app()
