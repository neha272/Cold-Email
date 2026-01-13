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
    manifest: Annotated[
        Path,
        typer.Option(
            "--manifest",
            "-m",
            help="Path to resume manifest CSV file",
        ),
    ] = Path("data/resume_manifest.csv"),
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
    reset_state: Annotated[
        bool,
        typer.Option(
            "--reset-state",
            help="Reset prospect state for existing prospects",
        ),
    ] = False,
) -> None:
    """Ingest prospects from CSV/Excel file."""
    logger.info("Ingesting prospects", file=str(file), command="ingest")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(
            db_path=settings.database.path, echo=settings.database.echo
        )

        # Load resume manifest
        manifest_path = Path(settings.paths.resumes_dir).parent / manifest.name
        if not manifest_path.exists():
            manifest_path = manifest
        resume_manifest = ResumeManifest(manifest_path, base_path=Path("."))

        with get_session(engine) as session:
            repo = ProspectRepository(session)
            created, updated, errors = ingest_prospects(
                file_path=file,
                manifest=resume_manifest,
                repo=repo,
                reset_state=reset_state,
            )

            typer.echo(f"\n✓ Ingestion complete:")
            typer.echo(f"  Created: {created}")
            typer.echo(f"  Updated: {updated}")
            if errors:
                typer.echo(f"  Errors: {len(errors)}")
                for error in errors[:5]:  # Show first 5 errors
                    typer.echo(f"    - {error.get('email', 'unknown')}: {error.get('error')}")
                if len(errors) > 5:
                    typer.echo(f"    ... and {len(errors) - 5} more errors")

    except Exception as e:
        logger.error("Failed to ingest prospects", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


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
    manifest: Annotated[
        Path,
        typer.Option(
            "--manifest",
            "-m",
            help="Path to resume manifest CSV file",
        ),
    ] = Path("data/resume_manifest.csv"),
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to config file",
        ),
    ] = Path("config/settings.yaml"),
) -> None:
    """Run the cold-email automation workflow."""
    logger.info(
        "Running automation",
        file=str(file),
        dry_run=dry_run,
        confirm_send=confirm_send,
        command="run",
    )

    try:
        # Load configuration
        settings = load_config(str(config))
        sequences = load_sequences()
        env_settings = EnvSettings()

        # Safety check
        if not dry_run and settings.safety.require_confirm_send and not confirm_send:
            typer.echo("✗ Error: --confirm-send required for live runs", err=True)
            raise typer.Exit(1)

        # Load resume manifest
        manifest_path = Path(settings.paths.resumes_dir).parent / manifest.name
        if not manifest_path.exists():
            manifest_path = manifest
        resume_manifest = ResumeManifest(manifest_path, base_path=Path("."))

        # Create orchestrator
        orchestrator = Orchestrator(
            settings=settings,
            env_settings=env_settings,
            sequences=sequences,
            dry_run=dry_run,
        )

        # Run daily workflow
        summary = orchestrator.run_daily(prospects_file=file, manifest=resume_manifest)

        # Display summary
        typer.echo("\n" + "=" * 60)
        typer.echo("Run Summary")
        typer.echo("=" * 60)
        typer.echo(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
        typer.echo(f"\nIngestion:")
        typer.echo(f"  Created: {summary['ingested']['created']}")
        typer.echo(f"  Updated: {summary['ingested']['updated']}")
        if summary["ingested"]["errors"]:
            typer.echo(f"  Errors: {len(summary['ingested']['errors'])}")

        typer.echo(f"\nReplies Detected: {summary['replies_detected']}")
        typer.echo(f"\nEmails:")
        typer.echo(f"  Sent: {summary['emails_sent']}")
        typer.echo(f"  Failed: {summary['emails_failed']}")
        if summary["throttled"] > 0:
            typer.echo(f"  Throttled: {summary['throttled']}")

        typer.echo("=" * 60)

    except Exception as e:
        logger.error("Failed to run automation", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1)


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
