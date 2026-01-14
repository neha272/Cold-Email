"""SQLAlchemy models for state management."""

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class ProspectStatus(str, Enum):
    """Prospect status enumeration."""

    NEW = "NEW"
    SENT_INITIAL = "SENT_INITIAL"
    FOLLOWUP_1_SENT = "FOLLOWUP_1_SENT"
    FOLLOWUP_2_SENT = "FOLLOWUP_2_SENT"
    REPLIED = "REPLIED"
    BOUNCED = "BOUNCED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    COMPLETED = "COMPLETED"
    ERROR = "ERROR"


class MessageEventType(str, Enum):
    """Message event type enumeration."""

    SEND_ATTEMPT = "SEND_ATTEMPT"
    SEND_SUCCESS = "SEND_SUCCESS"
    SEND_FAIL = "SEND_FAIL"
    REPLY_DETECTED = "REPLY_DETECTED"
    BOUNCE = "BOUNCE"
    MANUAL_STOP = "MANUAL_STOP"


class Prospect(Base):
    """Prospect model representing a contact in the system."""

    __tablename__ = "prospects"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    resume_id: Mapped[str] = mapped_column(String(100), nullable=False)
    resume_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resume_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sequence_id: Mapped[str] = mapped_column(String(100), nullable=False, default="default")
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=ProspectStatus.NEW.value, index=True
    )
    followup_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    thread_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    variables_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    message_events: Mapped[list["MessageEvent"]] = relationship(
        "MessageEvent", back_populates="prospect", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Prospect(id={self.id}, email={self.email}, status={self.status})>"

    def is_terminal_status(self) -> bool:
        """Check if prospect is in a terminal status (no more emails sent)."""
        return self.status in (
            ProspectStatus.REPLIED,
            ProspectStatus.BOUNCED,
            ProspectStatus.UNSUBSCRIBED,
            ProspectStatus.COMPLETED,
        )

    def is_eligible_for_sending(self) -> bool:
        """Check if prospect is eligible for sending emails."""
        if self.is_terminal_status():
            return False
        if self.status == ProspectStatus.ERROR:
            return False
        return True


class MessageEvent(Base):
    """Message event model for tracking all email-related events."""

    __tablename__ = "message_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    prospect_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("prospects.id"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), index=True
    )
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    template_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    outbound_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attachment_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    prospect: Mapped["Prospect"] = relationship("Prospect", back_populates="message_events")

    def __repr__(self) -> str:
        return (
            f"<MessageEvent(id={self.id}, prospect_id={self.prospect_id}, "
            f"event_type={self.event_type})>"
        )
