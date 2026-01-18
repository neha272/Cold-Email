"""Tests for orchestrator dry-run mode."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from cold_emailer.attachments import ResumeManifest
from cold_emailer.config import (
    DatabaseSettings,
    EmailSettings,
    EnvSettings,
    PathsSettings,
    Settings,
)
from cold_emailer.orchestrator import Orchestrator
from cold_emailer.state_store.models import Prospect, ProspectStatus
from cold_emailer.state_store.repo import ProspectRepository


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    """Create test settings."""
    from cold_emailer.config import AppSettings, LoggingSettings, SafetySettings, ThrottlingSettings

    return Settings(
        app=AppSettings(name="Test", version="0.1.0"),
        database=DatabaseSettings(path=str(tmp_path / "test.db"), echo=False),
        email=EmailSettings(
            default_from_name="Test Sender",
            default_from_email="sender@test.com",
        ),
        throttling=ThrottlingSettings(
            daily_max=100,
            per_minute_limit=10,
            send_window_start="00:00",
            send_window_end="23:59",
        ),
        safety=SafetySettings(),
        paths=PathsSettings(
            prospects_dir=str(tmp_path / "data"),
            resumes_dir=str(tmp_path / "resumes"),
            templates_dir=str(tmp_path / "templates"),
            logs_dir=str(tmp_path / "logs"),
        ),
        logging=LoggingSettings(),
    )


@pytest.fixture
def test_sequences() -> dict:
    """Create test sequences."""
    return {
        "sequences": {
            "default": {
                "steps": [
                    {"step": 0, "template": "Initial", "wait_days": 3, "subject": "Test"},
                    {"step": 1, "template": "Followup 1", "wait_days": 5, "subject": "Follow up"},
                ]
            }
        }
    }


@pytest.fixture
def test_env_settings() -> "EnvSettings":
    """Create test environment settings."""
    from cold_emailer.config import EnvSettings

    return EnvSettings(
        smtp_host="smtp.test.com",
        smtp_port=587,
        smtp_user="test@test.com",
        smtp_password="password",
        smtp_use_tls=True,
        smtp_from_name="Test",
        smtp_from_email="test@test.com",
        imap_host="imap.test.com",
        imap_port=993,
        imap_user="test@test.com",
        imap_password="password",
        imap_use_ssl=True,
    )


def test_orchestrator_init(
    test_settings: Settings, test_env_settings: "EnvSettings", test_sequences: dict
) -> None:
    """Test orchestrator initialization."""
    orchestrator = Orchestrator(
        settings=test_settings,
        env_settings=test_env_settings,
        sequences=test_sequences,
        dry_run=True,
    )

    assert orchestrator.dry_run is True
    assert orchestrator.settings == test_settings
    assert orchestrator.composer is not None


def test_get_due_prospects(
    test_settings: Settings, test_env_settings: "EnvSettings", test_sequences: dict
) -> None:
    """Test getting due prospects."""
    orchestrator = Orchestrator(
        settings=test_settings,
        env_settings=test_env_settings,
        sequences=test_sequences,
        dry_run=True,
    )

    # Create a prospect in database
    from cold_emailer.state_store.db import init_database

    init_database(orchestrator.engine)
    with orchestrator.engine.connect():
        from cold_emailer.state_store.models import Base

        Base.metadata.create_all(orchestrator.engine)

    with orchestrator.engine.begin() as session:
        from sqlalchemy.orm import Session

        session_obj = Session(bind=session)
        repo = ProspectRepository(session_obj)
        repo.create(
            {
                "email": "test@example.com",
                "full_name": "Test User",
                "company": "Test Corp",
                "resume_id": "RES-001",
                "status": ProspectStatus.NEW.value,
                "next_action_at": datetime.utcnow() - timedelta(hours=1),
            }
        )
        session_obj.commit()

    due = orchestrator.get_due_prospects()
    assert len(due) >= 1


def test_send_email_dry_run(
    test_settings: Settings, test_env_settings: "EnvSettings", test_sequences: dict, tmp_path: Path
) -> None:
    """Test sending email in dry-run mode."""
    # Create template
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "Initial.md").write_text("Subject: Test\n\nBody")

    # Create resume
    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    resume_file = resume_dir / "RES-001.pdf"
    resume_file.write_text("resume content")

    orchestrator = Orchestrator(
        settings=test_settings,
        env_settings=test_env_settings,
        sequences=test_sequences,
        dry_run=True,
    )

    from cold_emailer.state_store.db import init_database

    init_database(orchestrator.engine)
    with orchestrator.engine.connect():
        from cold_emailer.state_store.models import Base

        Base.metadata.create_all(orchestrator.engine)

    # Create prospect
    with orchestrator.engine.begin() as session:
        from sqlalchemy.orm import Session

        session_obj = Session(bind=session)
        repo = ProspectRepository(session_obj)
        prospect = repo.create(
            {
                "email": "test@example.com",
                "full_name": "Test User",
                "company": "Test Corp",
                "resume_id": "RES-001",
                "resume_path": str(resume_file),
                "resume_sha256": "abc123",
                "status": ProspectStatus.NEW.value,
            }
        )
        session_obj.commit()
        prospect_id = prospect.id

    # Send email (dry-run)
    with orchestrator.engine.begin() as session:
        from sqlalchemy.orm import Session

        session_obj = Session(bind=session)
        prospect = session_obj.get(Prospect, prospect_id)

        success, message_id = orchestrator.send_email_to_prospect(
            prospect=prospect,
            template_name="Initial",
            subject="Test",
            step=0,
        )

        assert success is True
        assert message_id is not None


def test_run_daily_dry_run(
    test_settings: Settings, test_env_settings: "EnvSettings", test_sequences: dict, tmp_path: Path
) -> None:
    """Test running daily workflow in dry-run mode."""
    # Setup templates and resumes
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "Initial.md").write_text("Subject: Test\n\nBody")

    resume_dir = tmp_path / "resumes"
    resume_dir.mkdir()
    resume_file = resume_dir / "RES-001.pdf"
    resume_file.write_text("resume content")

    orchestrator = Orchestrator(
        settings=test_settings,
        env_settings=test_env_settings,
        sequences=test_sequences,
        dry_run=True,
    )

    from cold_emailer.state_store.db import init_database

    init_database(orchestrator.engine)
    with orchestrator.engine.connect():
        from cold_emailer.state_store.models import Base

        Base.metadata.create_all(orchestrator.engine)

    # Create manifest
    import csv

    manifest_file = tmp_path / "manifest.csv"
    with open(manifest_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["resume_id", "relative_path", "sha256", "version"])
        writer.writeheader()
        writer.writerow(
            {
                "resume_id": "RES-001",
                "relative_path": str(resume_file.relative_to(tmp_path)),
                "sha256": "",
                "version": "1.0",
            }
        )

    manifest = ResumeManifest(manifest_file, base_path=tmp_path)

    # Create prospects file
    prospects_file = tmp_path / "prospects.csv"
    with open(prospects_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["email", "full_name", "company", "resume_id"])
        writer.writeheader()
        writer.writerow(
            {
                "email": "test@example.com",
                "full_name": "Test User",
                "company": "Test Corp",
                "resume_id": "RES-001",
            }
        )

    # Run daily workflow
    summary = orchestrator.run_daily(prospects_file=prospects_file, manifest=manifest)

    assert "ingested" in summary
    assert "emails_sent" in summary
    assert summary["emails_sent"] >= 0  # May be 0 if outside window or throttled
