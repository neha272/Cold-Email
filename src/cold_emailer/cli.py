"""CLI interface for cold-emailer."""

import json
from datetime import datetime
from pathlib import Path

import typer
from typing_extensions import Annotated

from cold_emailer.config import load_config, load_sequences
from cold_emailer.state_store.db import create_database_engine, get_session, init_database
from cold_emailer.state_store.models import ProspectStatus
from cold_emailer.state_store.repo import MessageEventRepository, ProspectRepository
from cold_emailer.utils import get_logger, setup_logging

app = typer.Typer(
    name="cold-emailer",
    help="Local cold-email automation tool with state tracking and follow-up sequencing",
    add_completion=False,
)

logger = get_logger(__name__)


@app.command()
def init_db(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
) -> None:
    """Initialize the SQLite database."""
    logger.info("Initializing database", command="init-db")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(
            db_path=settings.database.path, echo=settings.database.echo
        )
        init_database(engine)
        typer.echo(f"✓ Database initialized at {settings.database.path}")
        logger.info("Database initialized successfully", path=settings.database.path)
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        typer.echo(f"✗ Error initializing database: {e}", err=True)
        raise typer.Exit(1)


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
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
) -> None:
    """Show status of prospects."""
    logger.info("Showing status", limit=limit, command="status")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(
            db_path=settings.database.path, echo=settings.database.echo
        )

        with get_session(engine) as session:
            repo = ProspectRepository(session)
            prospects = repo.get_all(limit=limit)

            if not prospects:
                typer.echo("No prospects found in database.")
                return

            # Count by status
            status_counts: dict[str, int] = {}
            for prospect in prospects:
                status_counts[prospect.status] = status_counts.get(prospect.status, 0) + 1

            typer.echo(f"\nProspect Status Summary (showing {len(prospects)} of {limit}):")
            typer.echo("-" * 60)
            for status, count in sorted(status_counts.items()):
                typer.echo(f"  {status}: {count}")

            typer.echo("\nRecent Prospects:")
            typer.echo("-" * 60)
            for prospect in prospects[:10]:
                next_action = (
                    prospect.next_action_at.strftime("%Y-%m-%d %H:%M")
                    if prospect.next_action_at
                    else "N/A"
                )
                typer.echo(
                    f"  {prospect.email[:40]:<40} | {prospect.status:<20} | Next: {next_action}"
                )

    except Exception as e:
        logger.error("Failed to show status", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


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
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
    limit: Annotated[
        int | None,
        typer.Option(
            "--limit",
            "-l",
            help="Maximum number of events to export",
        ),
    ] = None,
) -> None:
    """Export message events to JSONL file."""
    logger.info("Exporting events", output=str(out), command="export-events")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(
            db_path=settings.database.path, echo=settings.database.echo
        )

        # Ensure output directory exists
        out.parent.mkdir(parents=True, exist_ok=True)

        with get_session(engine) as session:
            event_repo = MessageEventRepository(session)
            events = event_repo.get_all_events(limit=limit)

            with open(out, "w", encoding="utf-8") as f:
                for event in events:
                    event_dict = {
                        "id": str(event.id),
                        "prospect_id": str(event.prospect_id),
                        "event_type": event.event_type,
                        "occurred_at": event.occurred_at.isoformat(),
                        "subject": event.subject,
                        "template_id": event.template_id,
                        "outbound_message_id": event.outbound_message_id,
                        "provider_message_id": event.provider_message_id,
                        "attachment_sha256": event.attachment_sha256,
                        "meta_json": event.meta_json,
                    }
                    f.write(json.dumps(event_dict) + "\n")

            typer.echo(f"✓ Exported {len(events)} events to {out}")
            logger.info("Events exported successfully", count=len(events), path=str(out))

    except Exception as e:
        logger.error("Failed to export events", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


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
) -> None:
    """Cold Emailer - Local cold-email automation tool."""
    # Basic logging setup (detailed config loaded per-command)
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(level=log_level, format_type="text")
    logger.info("Application started")


if __name__ == "__main__":
    app()
