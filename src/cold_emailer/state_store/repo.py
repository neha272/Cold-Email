"""Repository layer for database operations."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from cold_emailer.state_store.models import MessageEvent, MessageEventType, Prospect, ProspectStatus


class ProspectRepository:
    """Repository for prospect operations."""

    def __init__(self, session: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def create(self, prospect_data: dict[str, Any]) -> Prospect:
        """
        Create a new prospect.

        Args:
            prospect_data: Dictionary with prospect fields

        Returns:
            Created Prospect instance
        """
        prospect = Prospect(**prospect_data)
        self.session.add(prospect)
        return prospect

    def get_by_id(self, prospect_id: uuid.UUID) -> Prospect | None:
        """
        Get prospect by ID.

        Args:
            prospect_id: Prospect UUID

        Returns:
            Prospect instance or None
        """
        return self.session.get(Prospect, prospect_id)

    def get_by_email(self, email: str) -> Prospect | None:
        """
        Get prospect by email address.

        Args:
            email: Email address

        Returns:
            Prospect instance or None
        """
        return self.session.query(Prospect).filter(Prospect.email == email).first()

    def upsert(self, prospect_data: dict[str, Any]) -> Prospect:
        """
        Upsert prospect (create or update).

        Args:
            prospect_data: Dictionary with prospect fields (must include 'email')

        Returns:
            Prospect instance (created or updated)
        """
        email = prospect_data.get("email")
        if not email:
            raise ValueError("Email is required for upsert")

        existing = self.get_by_email(email)
        if existing:
            # Update existing prospect (but preserve state if not explicitly reset)
            for key, value in prospect_data.items():
                if key != "id" and hasattr(existing, key):
                    setattr(existing, key, value)
            return existing
        else:
            # Create new prospect
            return self.create(prospect_data)

    def get_due_prospects(
        self, cutoff_time: datetime, limit: int | None = None
    ) -> list[Prospect]:
        """
        Get prospects that are due for action (next_action_at <= cutoff_time).

        Args:
            cutoff_time: Maximum next_action_at time
            limit: Optional limit on number of results

        Returns:
            List of eligible prospects
        """
        query = (
            self.session.query(Prospect)
            .filter(
                and_(
                    Prospect.next_action_at <= cutoff_time,
                    Prospect.is_eligible_for_sending(),
                )
            )
            .order_by(Prospect.next_action_at.asc())
        )

        if limit:
            query = query.limit(limit)

        return list(query.all())

    def get_by_status(self, status: ProspectStatus | str) -> list[Prospect]:
        """
        Get all prospects with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of prospects
        """
        status_str = status.value if isinstance(status, ProspectStatus) else status
        return list(self.session.query(Prospect).filter(Prospect.status == status_str).all())

    def update_status(
        self,
        prospect_id: uuid.UUID,
        status: ProspectStatus | str,
        error_message: str | None = None,
    ) -> Prospect | None:
        """
        Update prospect status.

        Args:
            prospect_id: Prospect UUID
            status: New status
            error_message: Optional error message

        Returns:
            Updated Prospect instance or None if not found
        """
        prospect = self.get_by_id(prospect_id)
        if not prospect:
            return None

        status_str = status.value if isinstance(status, ProspectStatus) else status
        prospect.status = status_str
        if error_message:
            prospect.last_error = error_message

        return prospect

    def update_next_action(
        self, prospect_id: uuid.UUID, next_action_at: datetime | None
    ) -> Prospect | None:
        """
        Update prospect's next action time.

        Args:
            prospect_id: Prospect UUID
            next_action_at: Next action datetime or None

        Returns:
            Updated Prospect instance or None if not found
        """
        prospect = self.get_by_id(prospect_id)
        if not prospect:
            return None

        prospect.next_action_at = next_action_at
        return prospect

    def update_followup_step(self, prospect_id: uuid.UUID, step: int) -> Prospect | None:
        """
        Update prospect's follow-up step.

        Args:
            prospect_id: Prospect UUID
            step: New follow-up step number

        Returns:
            Updated Prospect instance or None if not found
        """
        prospect = self.get_by_id(prospect_id)
        if not prospect:
            return None

        prospect.followup_step = step
        return prospect

    def get_all(self, limit: int | None = None, offset: int = 0) -> list[Prospect]:
        """
        Get all prospects with optional pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of prospects
        """
        query = self.session.query(Prospect).order_by(Prospect.created_at.desc())
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        return list(query.all())


class MessageEventRepository:
    """Repository for message event operations."""

    def __init__(self, session: Session) -> None:
        """
        Initialize repository with database session.

        Args:
            session: SQLAlchemy session
        """
        self.session = session

    def create(self, event_data: dict[str, Any]) -> MessageEvent:
        """
        Create a new message event.

        Args:
            event_data: Dictionary with event fields

        Returns:
            Created MessageEvent instance
        """
        event = MessageEvent(**event_data)
        self.session.add(event)
        return event

    def get_by_prospect_id(
        self, prospect_id: uuid.UUID, limit: int | None = None
    ) -> list[MessageEvent]:
        """
        Get all events for a prospect.

        Args:
            prospect_id: Prospect UUID
            limit: Optional limit on number of results

        Returns:
            List of message events
        """
        query = (
            self.session.query(MessageEvent)
            .filter(MessageEvent.prospect_id == prospect_id)
            .order_by(MessageEvent.occurred_at.desc())
        )
        if limit:
            query = query.limit(limit)
        return list(query.all())

    def get_by_outbound_message_id(self, message_id: str) -> MessageEvent | None:
        """
        Get event by outbound message ID.

        Args:
            message_id: Outbound message ID

        Returns:
            MessageEvent instance or None
        """
        return (
            self.session.query(MessageEvent)
            .filter(MessageEvent.outbound_message_id == message_id)
            .first()
        )

    def get_replies_for_prospect(self, prospect_id: uuid.UUID) -> list[MessageEvent]:
        """
        Get all reply events for a prospect.

        Args:
            prospect_id: Prospect UUID

        Returns:
            List of reply events
        """
        return list(
            self.session.query(MessageEvent)
            .filter(
                and_(
                    MessageEvent.prospect_id == prospect_id,
                    MessageEvent.event_type == MessageEventType.REPLY_DETECTED.value,
                )
            )
            .order_by(MessageEvent.occurred_at.desc())
            .all()
        )

    def get_all_events(
        self, limit: int | None = None, offset: int = 0
    ) -> list[MessageEvent]:
        """
        Get all events with optional pagination.

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of message events
        """
        query = self.session.query(MessageEvent).order_by(MessageEvent.occurred_at.desc())
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        return list(query.all())
