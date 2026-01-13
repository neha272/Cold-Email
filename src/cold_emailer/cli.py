"""CLI interface for cold-emailer."""

from pathlib import Path

import typer
from typing_extensions import Annotated

from cold_emailer.config import load_config, load_sequences
from cold_emailer.utils import get_logger, setup_logging

app = typer.Typer(
    name="cold-emailer",
    help="Local cold-email automation tool with state tracking and follow-up sequencing",
    add_completion=False,
)

logger = get_logger(__name__)


@app.command()
def init_db() -> None:
    """Initialize the SQLite database."""
    logger.info("Initializing database", command="init-db")
    typer.echo("Database initialization not yet implemented (Phase 2)")
    # TODO: Phase 2 - Initialize database schema


@app.command()
def ingest(
    file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Path to prospects CSV/Excel file",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
) -> None:
    """Ingest prospects from CSV/Excel file."""
    logger.info("Ingesting prospects", file=str(file), command="ingest")
    typer.echo(f"Ingesting prospects from {file}")
    # TODO: Phase 3 - Implement ingestion


@app.command()
def run(
    file: Annotated[
        Path,
        typer.Option(
            "--file",
            "-f",
            help="Path to prospects CSV/Excel file",
            exists=True,
            file_okay=True,
            dir_okay=False,
        ),
    ],
    dry_run: Annotated[
        bool,
        typer.Option(
            "--dry-run",
            help="Run without sending emails",
        ),
    ] = False,
    confirm_send: Annotated[
        bool,
        typer.Option(
            "--confirm-send",
            help="Require confirmation before sending (safety check)",
        ),
    ] = False,
) -> None:
    """Run the cold-email automation workflow."""
    logger.info(
        "Running automation",
        file=str(file),
        dry_run=dry_run,
        confirm_send=confirm_send,
        command="run",
    )
    typer.echo(f"Running automation (dry_run={dry_run}, confirm_send={confirm_send})")
    # TODO: Phase 7 - Implement orchestrator


@app.command()
def status(
    limit: Annotated[
        int,
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of prospects to show",
        ),
    ] = 50,
) -> None:
    """Show status of prospects."""
    logger.info("Showing status", limit=limit, command="status")
    typer.echo(f"Status (showing up to {limit} prospects)")
    # TODO: Phase 2 - Implement status query


@app.command()
def export_events(
    out: Annotated[
        Path,
        typer.Option(
            "--out",
            "-o",
            help="Output file path",
        ),
    ] = Path("logs/events.jsonl"),
) -> None:
    """Export message events to JSONL file."""
    logger.info("Exporting events", output=str(out), command="export-events")
    typer.echo(f"Exporting events to {out}")
    # TODO: Phase 2 - Implement event export


@app.callback()
def main(
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Enable verbose logging",
        ),
    ] = False,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
) -> None:
    """Cold Emailer - Local cold-email automation tool."""
    # Load configuration
    try:
        settings = load_config(str(config))
        log_level = "DEBUG" if verbose else settings.logging.level
        setup_logging(
            level=log_level,
            format_type=settings.logging.format,
            log_file=settings.logging.file,
        )
        logger.info("Application started", version=settings.app.version)
    except Exception as e:
        typer.echo(f"Error loading configuration: {e}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
