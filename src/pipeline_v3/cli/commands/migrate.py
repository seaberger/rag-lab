"""
Migration command for Pipeline v3 CLI.

Provides commands to migrate data between different backends.
"""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add the pipeline_v3 root to Python path
pipeline_root = Path(__file__).parent.parent.parent
if str(pipeline_root) not in sys.path:
    sys.path.insert(0, str(pipeline_root))

from tools.sqlite_to_postgres import SQLiteToPostgresMigrator

from utils.config import PipelineConfig

app = typer.Typer(help="Database migration commands")
console = Console()


@app.command()
def to_postgres(
    registry_db: Path | None = typer.Option(
        Path("./document_registry_v3.db"),
        "--registry",
        "-r",
        help="Path to SQLite registry database",
    ),
    keyword_db: Path | None = typer.Option(
        Path("./keyword_index_v3.db"),
        "--keyword",
        "-k",
        help="Path to SQLite keyword index database",
    ),
    jobs_db: Path | None = typer.Option(
        Path("./jobs_v3.db"),
        "--jobs",
        "-j",
        help="Path to SQLite jobs database",
    ),
    fingerprints_db: Path | None = typer.Option(
        Path("./fingerprints_v3.db"),
        "--fingerprints",
        "-f",
        help="Path to SQLite fingerprints database",
    ),
    tenant_id: str | None = typer.Option(
        None,
        "--tenant-id",
        "-t",
        help="Target tenant ID (defaults to config)",
    ),
    batch_size: int = typer.Option(
        1000,
        "--batch-size",
        "-b",
        help="Number of records to process per batch",
    ),
    skip_existing: bool = typer.Option(
        True,
        "--skip-existing/--overwrite",
        help="Skip records that already exist in PostgreSQL",
    ),
    verify: bool = typer.Option(
        True,
        "--verify/--no-verify",
        help="Verify migration after completion",
    ),
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
):
    """Migrate data from SQLite to PostgreSQL."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        # Check if PostgreSQL is configured
        if config.database.backend != "postgresql":
            console.print(
                "[red]❌ PostgreSQL not configured. Set database.backend = 'postgresql' in config.[/red]"
            )
            raise typer.Exit(1)

        # Build paths dictionary
        sqlite_paths = {}

        # Check which databases exist
        found_dbs = []
        missing_dbs = []

        if registry_db and registry_db.exists():
            sqlite_paths["registry"] = registry_db
            found_dbs.append(("Registry", registry_db))
        else:
            missing_dbs.append(("Registry", registry_db))

        if keyword_db and keyword_db.exists():
            sqlite_paths["keyword"] = keyword_db
            found_dbs.append(("Keyword Index", keyword_db))
        else:
            missing_dbs.append(("Keyword Index", keyword_db))

        if jobs_db and jobs_db.exists():
            sqlite_paths["jobs"] = jobs_db
            found_dbs.append(("Jobs", jobs_db))
        else:
            missing_dbs.append(("Jobs", jobs_db))

        if fingerprints_db and fingerprints_db.exists():
            sqlite_paths["fingerprints"] = fingerprints_db
            found_dbs.append(("Fingerprints", fingerprints_db))
        else:
            missing_dbs.append(("Fingerprints", fingerprints_db))

        # Display migration plan
        table = Table(title="Migration Plan")
        table.add_column("Database", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Path")

        for db_name, db_path in found_dbs:
            table.add_row(db_name, "✓ Found", str(db_path))

        for db_name, db_path in missing_dbs:
            table.add_row(db_name, "✗ Missing", str(db_path), style="dim")

        console.print(table)

        if not sqlite_paths:
            console.print("[red]❌ No SQLite databases found to migrate[/red]")
            raise typer.Exit(1)

        # Show PostgreSQL target
        pg_settings = config.database.postgresql
        target_panel = Panel(
            f"""[bold]PostgreSQL Target[/bold]
Host: {pg_settings.host}:{pg_settings.port}
Database: {pg_settings.database}
User: {pg_settings.user}
Tenant ID: {tenant_id or pg_settings.default_tenant_id}
Batch Size: {batch_size:,}
Skip Existing: {skip_existing}""",
            title="Target Configuration",
            border_style="blue",
        )
        console.print(target_panel)

        # Confirm migration
        if not typer.confirm("Proceed with migration?"):
            console.print("[yellow]⚠️ Migration cancelled[/yellow]")
            raise typer.Exit(0)

        # Run migration
        console.print("\n[bold]Starting migration...[/bold]")

        async def run_migration():
            # Create migrator
            migrator = SQLiteToPostgresMigrator(
                sqlite_paths,
                pg_settings,
                tenant_id=tenant_id,
            )

            # Run migration with progress
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Migrating data...", total=None)

                try:
                    await migrator.migrate_all(
                        batch_size=batch_size,
                        skip_existing=skip_existing,
                    )
                    progress.update(task, completed=True)
                except Exception:
                    progress.stop()
                    raise

            return migrator.stats

        # Execute migration
        stats = asyncio.run(run_migration())

        # Display results
        results_table = Table(title="Migration Results")
        results_table.add_column("Metric", style="cyan")
        results_table.add_column("Count", justify="right")

        results_table.add_row("Documents", f"{stats.documents_migrated:,}")
        results_table.add_row("Index Entries", f"{stats.index_entries_migrated:,}")
        results_table.add_row("Jobs", f"{stats.jobs_migrated:,}")
        results_table.add_row("Fingerprints", f"{stats.fingerprints_migrated:,}")
        results_table.add_row(
            "Errors", f"{len(stats.errors):,}", style="red" if stats.errors else "green"
        )

        console.print(results_table)

        # Show errors if any
        if stats.errors:
            console.print("\n[red]Migration errors:[/red]")
            for error in stats.errors[-5:]:  # Show last 5 errors
                console.print(f"  • {error}")

        # Run verification if requested
        if verify:
            console.print("\n[bold]Verifying migration...[/bold]")

            async def run_verification():
                migrator = SQLiteToPostgresMigrator(
                    sqlite_paths,
                    pg_settings,
                    tenant_id=tenant_id,
                )
                return await migrator.verify_migration()

            verification = asyncio.run(run_verification())

            # Display verification results
            verify_table = Table(title="Verification Results")
            verify_table.add_column("Data Type", style="cyan")
            verify_table.add_column("SQLite", justify="right")
            verify_table.add_column("PostgreSQL", justify="right")
            verify_table.add_column("Match", justify="center")

            for key in verification["sqlite_counts"]:
                sqlite_count = verification["sqlite_counts"][key]
                pg_count = verification["postgres_counts"].get(key, 0)
                match = verification["matches"].get(key, False)

                verify_table.add_row(
                    key.replace("_", " ").title(),
                    f"{sqlite_count:,}",
                    f"{pg_count:,}",
                    "✓" if match else "✗",
                    style="green" if match else "red",
                )

            console.print(verify_table)

            # Overall status
            all_match = all(verification["matches"].values())
            if all_match:
                console.print("[green]✅ Migration verified successfully![/green]")
            else:
                console.print("[red]❌ Migration verification failed - counts don't match[/red]")

    except Exception as e:
        console.print(f"[red]❌ Migration failed: {e!s}[/red]")
        raise typer.Exit(1)


@app.command()
def status(
    config_file: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Path to configuration file",
    ),
):
    """Check migration readiness and database status."""
    try:
        # Load configuration
        config = PipelineConfig(config_file=config_file)

        # Check current backend
        current_backend = config.database.backend

        status_panel = Panel(
            f"""[bold]Database Configuration[/bold]
Current Backend: {current_backend}
PostgreSQL Ready: {"Yes" if current_backend == "postgresql" else "No"}""",
            title="Migration Status",
            border_style="blue",
        )
        console.print(status_panel)

        # Check SQLite databases
        console.print("\n[bold]SQLite Databases:[/bold]")

        sqlite_dbs = [
            ("Registry", Path("./document_registry_v3.db")),
            ("Keyword Index", Path("./keyword_index_v3.db")),
            ("Jobs", Path("./jobs_v3.db")),
            ("Fingerprints", Path("./fingerprints_v3.db")),
        ]

        table = Table()
        table.add_column("Database", style="cyan")
        table.add_column("Path")
        table.add_column("Exists", justify="center")
        table.add_column("Size", justify="right")

        total_size = 0
        for db_name, db_path in sqlite_dbs:
            exists = db_path.exists()
            size = db_path.stat().st_size if exists else 0
            total_size += size

            table.add_row(
                db_name,
                str(db_path),
                "✓" if exists else "✗",
                f"{size / 1024 / 1024:.1f} MB" if exists else "-",
                style="green" if exists else "dim",
            )

        table.add_row(
            "[bold]Total[/bold]",
            "",
            "",
            f"[bold]{total_size / 1024 / 1024:.1f} MB[/bold]",
        )

        console.print(table)

        # Check PostgreSQL configuration
        if current_backend == "postgresql":
            pg_settings = config.database.postgresql
            console.print("\n[bold]PostgreSQL Configuration:[/bold]")
            pg_table = Table()
            pg_table.add_column("Setting", style="cyan")
            pg_table.add_column("Value")

            pg_table.add_row("Host", f"{pg_settings.host}:{pg_settings.port}")
            pg_table.add_row("Database", pg_settings.database)
            pg_table.add_row("User", pg_settings.user)
            pg_table.add_row("Default Tenant", pg_settings.default_tenant_id)
            pg_table.add_row("Registry Schema", pg_settings.registry_schema)
            pg_table.add_row("Search Schema", pg_settings.search_schema)
            pg_table.add_row("Jobs Schema", pg_settings.jobs_schema)
            pg_table.add_row("Fingerprints Schema", pg_settings.fingerprints_schema)

            console.print(pg_table)

    except Exception as e:
        console.print(f"[red]❌ Status check failed: {e!s}[/red]")
        raise typer.Exit(1)


def add_migrate_subcommands(subparsers):
    """Add migration commands to argument parser."""
    migrate_parser = subparsers.add_parser("migrate", help="Database migration commands")
    migrate_subparsers = migrate_parser.add_subparsers(
        dest="migrate_action", help="Migration actions"
    )

    # To PostgreSQL migration
    to_postgres_parser = migrate_subparsers.add_parser(
        "to-postgres", help="Migrate from SQLite to PostgreSQL"
    )
    to_postgres_parser.add_argument("--config-file", help="Path to configuration file")
    to_postgres_parser.add_argument("--tenant-id", help="Tenant ID for multi-tenant setup")
    to_postgres_parser.add_argument(
        "--batch-size", type=int, default=1000, help="Batch size for migration"
    )
    to_postgres_parser.add_argument(
        "--skip-existing", action="store_true", help="Skip existing records"
    )

    # Migration status
    status_parser = migrate_subparsers.add_parser("status", help="Check migration readiness")
    status_parser.add_argument("--config-file", help="Path to configuration file")

    return migrate_parser


if __name__ == "__main__":
    app()
