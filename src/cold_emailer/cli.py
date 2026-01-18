"""CLI interface for cold-emailer."""

import json
from pathlib import Path

import typer

from cold_emailer.config import EnvSettings, load_config, load_sequences
from cold_emailer.export import export_prospects_to_excel
from cold_emailer.ingestion import ingest_prospects
from cold_emailer.orchestrator import Orchestrator
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
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
) -> None:
    """Initialize the SQLite database."""
    logger.info("Initializing database", command="init-db")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(db_path=settings.database.path, echo=settings.database.echo)
        init_database(engine)
        typer.echo(f"✓ Database initialized at {settings.database.path}")
        logger.info("Database initialized successfully", path=settings.database.path)
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        typer.echo(f"✗ Error initializing database: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def ingest(
    file: Path = typer.Argument(
        ...,
        help="Path to prospects CSV/Excel file",
    ),
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
    reset_state: bool = typer.Option(
        False,
        "--reset-state",
        help="Reset prospect state for existing prospects",
    ),
) -> None:
    """Ingest prospects from CSV/Excel file."""
    # Validate file exists
    if not file.exists():
        typer.echo(f"✗ Error: File not found: {file}", err=True)
        raise typer.Exit(1)

    logger.info("Ingesting prospects", file=str(file), command="ingest")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(db_path=settings.database.path, echo=settings.database.echo)

        # Get resumes directory from settings
        resumes_dir = Path(settings.paths.resumes_dir)

        with get_session(engine) as session:
            repo = ProspectRepository(session)
            created, updated, errors = ingest_prospects(
                file_path=file,
                resumes_dir=resumes_dir,
                repo=repo,
                reset_state=reset_state,
            )

            typer.echo("\n✓ Ingestion complete:")
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
        raise typer.Exit(1) from e


@app.command()
def run(
    file: Path = typer.Argument(
        ...,
        help="Path to prospects CSV/Excel file",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run without sending emails (no emails will be sent)",
    ),
    confirm_send: bool = typer.Option(
        False,
        "--confirm-send",
        help="Require confirmation before sending (safety check)",
    ),
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
) -> None:
    """Run the cold-email automation workflow."""
    # Validate file exists
    if not file.exists():
        typer.echo(f"✗ Error: File not found: {file}", err=True)
        raise typer.Exit(1)

    # Fix boolean flag handling
    # Typer boolean flags: presence of flag = True, absence = False
    # But sometimes Typer doesn't properly set the value, so we check sys.argv as fallback
    import sys

    # Check if --dry-run flag is explicitly in command line
    has_dry_run_flag = any(arg == "--dry-run" for arg in sys.argv)
    # Use sys.argv check as primary source of truth since Typer flag isn't working reliably
    actual_dry_run = has_dry_run_flag
    actual_confirm_send = bool(confirm_send) if confirm_send is not None else False

    logger.info(
        "Running automation",
        file=str(file),
        dry_run=actual_dry_run,
        confirm_send=actual_confirm_send,
        command="run",
    )

    try:
        # Load configuration
        settings = load_config(str(config))
        sequences = load_sequences()
        env_settings = EnvSettings()

        # Safety check
        if not actual_dry_run and settings.safety.require_confirm_send and not actual_confirm_send:
            typer.echo("✗ Error: --confirm-send required for live runs", err=True)
            raise typer.Exit(1)

        # Create orchestrator
        orchestrator = Orchestrator(
            settings=settings,
            env_settings=env_settings,
            sequences=sequences,
            dry_run=actual_dry_run,
        )

        # Run daily workflow
        summary = orchestrator.run_daily(prospects_file=file)

        # Display summary
        typer.echo("\n" + "=" * 60)
        typer.echo("Run Summary")
        typer.echo("=" * 60)
        # Use the actual dry_run value from CLI
        typer.echo(f"Mode: {'DRY RUN' if actual_dry_run else 'LIVE'}")
        typer.echo("\nIngestion:")
        typer.echo(f"  Created: {summary['ingested']['created']}")
        typer.echo(f"  Updated: {summary['ingested']['updated']}")
        if summary["ingested"]["errors"]:
            typer.echo(f"  Errors: {len(summary['ingested']['errors'])}")

        typer.echo(f"\nReplies Detected: {summary['replies_detected']}")
        typer.echo("\nEmails:")
        typer.echo(f"  Sent: {summary['emails_sent']}")
        typer.echo(f"  Failed: {summary['emails_failed']}")
        if summary["throttled"] > 0:
            typer.echo(f"  Throttled: {summary['throttled']}")

        if "exported" in summary:
            typer.echo("\nExported to Excel:")
            typer.echo(f"  RESPONSE sheet: {summary['exported']['replied']}")
            typer.echo(f"  NO RESPONSE sheet: {summary['exported']['completed']}")

        typer.echo("=" * 60)

    except Exception as e:
        logger.error("Failed to run automation", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def status(
    limit: int = typer.Option(
        50,
        "--limit",
        "-l",
        help="Maximum number of prospects to show",
    ),
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
) -> None:
    """Show status of prospects."""
    logger.info("Showing status", limit=limit, command="status")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(db_path=settings.database.path, echo=settings.database.echo)
        # Ensure schema exists so status works on fresh installs
        init_database(engine)

        with get_session(engine) as session:
            repo = ProspectRepository(session)
            try:
                prospects = repo.get_all(limit=limit)
            except Exception:
                prospects = []

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
        raise typer.Exit(1) from e


@app.command()
def export_events(
    out: Path = typer.Option(
        Path("logs/events.jsonl"),
        "--out",
        "-o",
        help="Output file path",
    ),
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        help="Maximum number of events to export",
    ),
) -> None:
    """Export message events to JSONL file."""
    logger.info("Exporting events", output=str(out), command="export-events")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(db_path=settings.database.path, echo=settings.database.echo)

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
        raise typer.Exit(1) from e


@app.command()
def export_prospects(
    out: Path = typer.Option(
        Path("data/prospects.xlsx"),
        "--out",
        "-o",
        help="Output Excel file path",
    ),
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
    status_filter: str | None = typer.Option(
        None,
        "--status",
        "-s",
        help="Filter by status (REPLIED, COMPLETED, etc.). If not specified, exports all completed/replied prospects.",
    ),
) -> None:
    """Export prospects to Excel with NO RESPONSE and RESPONSE sheets."""
    logger.info("Exporting prospects", output=str(out), command="export-prospects")
    try:
        settings = load_config(str(config))
        engine = create_database_engine(db_path=settings.database.path, echo=settings.database.echo)

        # Ensure output directory exists
        out.parent.mkdir(parents=True, exist_ok=True)

        with get_session(engine) as session:
            repo = ProspectRepository(session)

            # Get prospects based on filter
            if status_filter:
                prospects = repo.get_by_status(status_filter)
            else:
                # Get all REPLIED and COMPLETED prospects
                replied = repo.get_by_status(ProspectStatus.REPLIED)
                completed = repo.get_by_status(ProspectStatus.COMPLETED)
                prospects = replied + completed

            if not prospects:
                typer.echo("No prospects found to export.")
                return

            # Export to Excel
            export_prospects_to_excel(prospects, out, preserve_existing=True)

            # Count by category
            replied_count = sum(1 for p in prospects if p.status == ProspectStatus.REPLIED.value)
            completed_count = sum(
                1 for p in prospects if p.status == ProspectStatus.COMPLETED.value
            )

            typer.echo(f"\n✓ Exported {len(prospects)} prospects to {out}")
            typer.echo(f"  RESPONSE tab: {replied_count} prospects")
            typer.echo(f"  NO RESPONSE tab: {completed_count} prospects")
            logger.info(
                "Prospects exported successfully",
                count=len(prospects),
                path=str(out),
                replied=replied_count,
                completed=completed_count,
            )

    except Exception as e:
        logger.error("Failed to export prospects", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.command()
def check_replies(
    config: Path = typer.Option(
        Path("config/settings.yaml"),
        "--config",
        "-c",
        help="Path to config file",
    ),
) -> None:
    """Manually check for replies (works even if IMAP wasn't configured during run)."""
    logger.info("Checking for replies", command="check-replies")
    try:
        settings = load_config(str(config))
        sequences = load_sequences()
        env_settings = EnvSettings()

        # Create orchestrator (not in dry-run mode for reply detection)
        orchestrator = Orchestrator(
            settings=settings,
            env_settings=env_settings,
            sequences=sequences,
            dry_run=False,  # Must be False to detect replies
        )

        replies_detected = orchestrator.detect_replies()

        typer.echo("\n✓ Reply check complete")
        typer.echo(f"  Replies detected: {replies_detected}")

        if replies_detected > 0:
            typer.echo(f"\n  ✓ {replies_detected} prospect(s) marked as REPLIED")
            typer.echo("  These prospects will no longer receive follow-up emails.")
        else:
            typer.echo("\n  No new replies detected.")
            typer.echo("  Note: Make sure IMAP is configured in .env file")

    except Exception as e:
        logger.error("Failed to check replies", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1) from e


@app.callback()
def main(
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Enable verbose logging",
    ),
) -> None:
    """Cold Emailer - Local cold-email automation tool."""
    # Basic logging setup (detailed config loaded per-command)
    log_level = "DEBUG" if verbose else "INFO"
    setup_logging(level=log_level, format_type="text")
    logger.info("Application started")


@app.command()
def web() -> None:
    """Start the web interface."""
    try:
        logger.info("Starting web interface")
        from cold_emailer.web.app import main as web_main

        web_main()
    except Exception as e:
        logger.error("Failed to start web interface", error=str(e))
        typer.echo(f"✗ Error: {e}", err=True)
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
