"""Tests for state transitions."""

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from cold_emailer.state_store.db import get_session_factory, init_database
from cold_emailer.state_store.models import MessageEvent, MessageEventType, Prospect, ProspectStatus
from cold_emailer.state_store.repo import MessageEventRepository, ProspectRepository


@pytest.fixture
def db_session(tmp_path) -> Session:
    """Create a temporary database session for testing."""
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    init_database(engine)
    SessionLocal = get_session_factory(engine)
    session = SessionLocal()
    yield session
    session.close()


def test_prospect_creation(db_session: Session) -> None:
    """Test creating a new prospect."""
    repo = ProspectRepository(db_session)
    prospect_data = {
        "email": "test@example.com",
        "full_name": "Test User",
        "company": "Test Corp",
        "resume_id": "RES-001",
        "status": ProspectStatus.NEW.value,
    }
    prospect = repo.create(prospect_data)
    db_session.commit()

    assert prospect.id is not None
    assert prospect.email == "test@example.com"
    assert prospect.status == ProspectStatus.NEW.value
    assert prospect.followup_step == 0


def test_prospect_upsert_create(db_session: Session) -> None:
    """Test upsert creates new prospect when email doesn't exist."""
    repo = ProspectRepository(db_session)
    prospect_data = {
        "email": "new@example.com",
        "full_name": "New User",
        "company": "New Corp",
        "resume_id": "RES-001",
    }
    prospect = repo.upsert(prospect_data)
    db_session.commit()

    assert prospect.id is not None
    assert prospect.email == "new@example.com"


def test_prospect_upsert_update(db_session: Session) -> None:
    """Test upsert updates existing prospect."""
    repo = ProspectRepository(db_session)
    # Create initial prospect
    prospect_data = {
        "email": "existing@example.com",
        "full_name": "Existing User",
        "company": "Existing Corp",
        "resume_id": "RES-001",
    }
    original = repo.create(prospect_data)
    db_session.commit()
    original_id = original.id

    # Update via upsert
    updated_data = {
        "email": "existing@example.com",
        "full_name": "Updated User",
        "company": "Updated Corp",
        "resume_id": "RES-002",
    }
    updated = repo.upsert(updated_data)
    db_session.commit()

    assert updated.id == original_id
    assert updated.full_name == "Updated User"
    assert updated.company == "Updated Corp"
    assert updated.resume_id == "RES-002"


def test_prospect_terminal_status(db_session: Session) -> None:
    """Test terminal status detection."""
    repo = ProspectRepository(db_session)
    prospect_data = {
        "email": "replied@example.com",
        "full_name": "Replied User",
        "company": "Replied Corp",
        "resume_id": "RES-001",
        "status": ProspectStatus.REPLIED.value,
    }
    prospect = repo.create(prospect_data)
    db_session.commit()

    assert prospect.is_terminal_status() is True
    assert prospect.is_eligible_for_sending() is False


def test_prospect_eligible_for_sending(db_session: Session) -> None:
    """Test eligibility for sending."""
    repo = ProspectRepository(db_session)
    prospect_data = {
        "email": "new@example.com",
        "full_name": "New User",
        "company": "New Corp",
        "resume_id": "RES-001",
        "status": ProspectStatus.NEW.value,
    }
    prospect = repo.create(prospect_data)
    db_session.commit()

    assert prospect.is_terminal_status() is False
    assert prospect.is_eligible_for_sending() is True


def test_get_due_prospects(db_session: Session) -> None:
    """Test getting prospects due for action."""
    repo = ProspectRepository(db_session)
    now = datetime.utcnow()

    # Create prospect with past next_action_at
    past_prospect = repo.create(
        {
            "email": "past@example.com",
            "full_name": "Past User",
            "company": "Past Corp",
            "resume_id": "RES-001",
            "status": ProspectStatus.NEW.value,
            "next_action_at": now - timedelta(hours=1),
        }
    )

    # Create prospect with future next_action_at
    future_prospect = repo.create(
        {
            "email": "future@example.com",
            "full_name": "Future User",
            "company": "Future Corp",
            "resume_id": "RES-001",
            "status": ProspectStatus.NEW.value,
            "next_action_at": now + timedelta(hours=1),
        }
    )

    # Create prospect with terminal status
    terminal_prospect = repo.create(
        {
            "email": "terminal@example.com",
            "full_name": "Terminal User",
            "company": "Terminal Corp",
            "resume_id": "RES-001",
            "status": ProspectStatus.REPLIED.value,
            "next_action_at": now - timedelta(hours=1),
        }
    )

    db_session.commit()

    due = repo.get_due_prospects(now)
    assert len(due) == 1
    assert due[0].id == past_prospect.id


def test_message_event_creation(db_session: Session) -> None:
    """Test creating a message event."""
    # First create a prospect
    prospect_repo = ProspectRepository(db_session)
    prospect = prospect_repo.create(
        {
            "email": "test@example.com",
            "full_name": "Test User",
            "company": "Test Corp",
            "resume_id": "RES-001",
        }
    )
    db_session.commit()

    # Create event
    event_repo = MessageEventRepository(db_session)
    event_data = {
        "prospect_id": prospect.id,
        "event_type": MessageEventType.SEND_SUCCESS.value,
        "subject": "Test Subject",
        "template_id": "Initial",
        "outbound_message_id": "msg-123",
    }
    event = event_repo.create(event_data)
    db_session.commit()

    assert event.id is not None
    assert event.prospect_id == prospect.id
    assert event.event_type == MessageEventType.SEND_SUCCESS.value


def test_update_prospect_status(db_session: Session) -> None:
    """Test updating prospect status."""
    repo = ProspectRepository(db_session)
    prospect = repo.create(
        {
            "email": "test@example.com",
            "full_name": "Test User",
            "company": "Test Corp",
            "resume_id": "RES-001",
            "status": ProspectStatus.NEW.value,
        }
    )
    db_session.commit()

    updated = repo.update_status(prospect.id, ProspectStatus.SENT_INITIAL)
    db_session.commit()

    assert updated is not None
    assert updated.status == ProspectStatus.SENT_INITIAL.value


def test_update_next_action(db_session: Session) -> None:
    """Test updating next action time."""
    repo = ProspectRepository(db_session)
    prospect = repo.create(
        {
            "email": "test@example.com",
            "full_name": "Test User",
            "company": "Test Corp",
            "resume_id": "RES-001",
        }
    )
    db_session.commit()

    next_action = datetime.utcnow() + timedelta(days=3)
    updated = repo.update_next_action(prospect.id, next_action)
    db_session.commit()

    assert updated is not None
    assert updated.next_action_at == next_action


def test_get_events_by_prospect(db_session: Session) -> None:
    """Test getting events for a prospect."""
    # Create prospect
    prospect_repo = ProspectRepository(db_session)
    prospect = prospect_repo.create(
        {
            "email": "test@example.com",
            "full_name": "Test User",
            "company": "Test Corp",
            "resume_id": "RES-001",
        }
    )
    db_session.commit()

    # Create multiple events
    event_repo = MessageEventRepository(db_session)
    for i in range(3):
        event_repo.create(
            {
                "prospect_id": prospect.id,
                "event_type": MessageEventType.SEND_SUCCESS.value,
                "subject": f"Test {i}",
            }
        )
    db_session.commit()

    events = event_repo.get_by_prospect_id(prospect.id)
    assert len(events) == 3


def test_get_replies_for_prospect(db_session: Session) -> None:
    """Test getting reply events for a prospect."""
    # Create prospect
    prospect_repo = ProspectRepository(db_session)
    prospect = prospect_repo.create(
        {
            "email": "test@example.com",
            "full_name": "Test User",
            "company": "Test Corp",
            "resume_id": "RES-001",
        }
    )
    db_session.commit()

    # Create various events
    event_repo = MessageEventRepository(db_session)
    event_repo.create(
        {
            "prospect_id": prospect.id,
            "event_type": MessageEventType.SEND_SUCCESS.value,
            "subject": "Test",
        }
    )
    event_repo.create(
        {
            "prospect_id": prospect.id,
            "event_type": MessageEventType.REPLY_DETECTED.value,
            "subject": "Re: Test",
        }
    )
    db_session.commit()

    replies = event_repo.get_replies_for_prospect(prospect.id)
    assert len(replies) == 1
    assert replies[0].event_type == MessageEventType.REPLY_DETECTED.value
