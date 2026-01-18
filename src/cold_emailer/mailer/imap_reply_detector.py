"""IMAP-based reply detection."""

import email
import imaplib
from datetime import datetime
from typing import Any

from cold_emailer.utils import get_logger

logger = get_logger(__name__)


class IMAPConfig:
    """IMAP configuration."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        use_ssl: bool = True,
        mailbox: str = "INBOX",
    ) -> None:
        """
        Initialize IMAP configuration.

        Args:
            host: IMAP server hostname
            port: IMAP server port
            user: IMAP username
            password: IMAP password
            use_ssl: Use SSL/TLS
            mailbox: Mailbox to search (default: INBOX)
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_ssl = use_ssl
        self.mailbox = mailbox


class ReplyDetector:
    """Detects email replies using IMAP."""

    def __init__(self, config: IMAPConfig) -> None:
        """
        Initialize reply detector.

        Args:
            config: IMAP configuration
        """
        self.config = config

    def _create_connection(self) -> imaplib.IMAP4 | imaplib.IMAP4_SSL:
        """
        Create IMAP connection.

        Returns:
            IMAP connection object

        Raises:
            imaplib.IMAP4.error: If connection fails
        """
        try:
            if self.config.use_ssl:
                imap = imaplib.IMAP4_SSL(self.config.host, self.config.port, timeout=30)
            else:
                imap = imaplib.IMAP4(self.config.host, self.config.port, timeout=30)
            imap.login(self.config.user, self.config.password)
            return imap
        except Exception as e:
            logger.error("Failed to create IMAP connection", error=str(e))
            raise

    def _parse_message(self, msg_data: tuple[bytes, bytes]) -> email.message.EmailMessage | None:
        """
        Parse email message from IMAP data.

        Args:
            msg_data: Tuple of (message number, message data) from IMAP

        Returns:
            Parsed EmailMessage or None if parsing fails
        """
        try:
            _, data = msg_data
            if isinstance(data[0], bytes):
                msg_bytes = data[0]
            else:
                msg_bytes = data[0][1]

            return email.message_from_bytes(msg_bytes)
        except Exception as e:
            logger.warning("Failed to parse message", error=str(e))
            return None

    def _extract_message_id(self, msg: email.message.EmailMessage) -> str | None:
        """
        Extract Message-ID from email.

        Args:
            msg: EmailMessage object

        Returns:
            Message-ID string (without <>) or None
        """
        msg_id = msg.get("Message-ID", "")
        if msg_id:
            return msg_id.strip("<>")
        return None

    def _extract_in_reply_to(self, msg: email.message.EmailMessage) -> list[str]:
        """
        Extract In-Reply-To header values.

        Args:
            msg: EmailMessage object

        Returns:
            List of Message-IDs this message is replying to
        """
        in_reply_to = msg.get("In-Reply-To", "")
        if not in_reply_to:
            return []

        # Parse multiple Message-IDs if present
        msg_ids = []
        for part in in_reply_to.split():
            msg_id = part.strip("<>,")
            if msg_id:
                msg_ids.append(msg_id)

        return msg_ids

    def _extract_references(self, msg: email.message.EmailMessage) -> list[str]:
        """
        Extract References header values.

        Args:
            msg: EmailMessage object

        Returns:
            List of Message-IDs in References header
        """
        references = msg.get("References", "")
        if not references:
            return []

        # Parse multiple Message-IDs if present
        msg_ids = []
        for part in references.split():
            msg_id = part.strip("<>,")
            if msg_id:
                msg_ids.append(msg_id)

        return msg_ids

    def _is_reply_by_message_id(
        self, msg: email.message.EmailMessage, outbound_message_id: str
    ) -> bool:
        """
        Check if message is a reply to outbound message by Message-ID.

        Args:
            msg: EmailMessage to check
            outbound_message_id: Outbound Message-ID to match

        Returns:
            True if message is a reply
        """
        # Check In-Reply-To header
        in_reply_to = self._extract_in_reply_to(msg)
        if outbound_message_id in in_reply_to:
            return True

        # Check References header
        references = self._extract_references(msg)
        if outbound_message_id in references:
            return True

        return False

    def _is_reply_by_subject_and_from(
        self, msg: email.message.EmailMessage, original_subject: str, from_email: str
    ) -> bool:
        """
        Fallback: Check if message is a reply by subject and from address.

        Args:
            msg: EmailMessage to check
            original_subject: Original email subject
            from_email: Expected sender email address

        Returns:
            True if message appears to be a reply
        """
        subject = msg.get("Subject", "")
        from_addr = msg.get("From", "")

        # Check if subject contains "Re:" or "RE:" followed by original subject
        subject_lower = subject.lower()
        original_lower = original_subject.lower()

        # Remove "Re:" prefix if present
        if subject_lower.startswith("re:"):
            subject_clean = subject_lower[3:].strip()
        elif subject_lower.startswith("re "):
            subject_clean = subject_lower[3:].strip()
        else:
            subject_clean = subject_lower

        # Check if cleaned subject matches original (allowing for some variation)
        if original_lower in subject_clean or subject_clean in original_lower:
            # Check from address matches
            if from_email.lower() in from_addr.lower():
                return True

        return False

    def detect_replies_by_message_id(
        self, outbound_message_ids: list[str], since_date: datetime | None = None
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Detect replies by Message-ID threading.

        Args:
            outbound_message_ids: List of outbound Message-IDs to check
            since_date: Only check messages since this date (defaults to Jan 1, 2026)

        Returns:
            Dictionary mapping outbound_message_id -> list of reply info dicts
        """
        if not outbound_message_ids:
            return {}

        # Default to January 1, 2026 if no date specified (optimization: skip older emails)
        if since_date is None:
            since_date = datetime(2026, 1, 1)

        replies: dict[str, list[dict[str, Any]]] = {msg_id: [] for msg_id in outbound_message_ids}

        try:
            imap = self._create_connection()
            try:
                imap.select(self.config.mailbox)

                # Build search criteria - check ALL messages since the specified date
                # This ensures we detect replies even if they've been read, but only checks recent emails
                search_criteria = ["ALL"]
                # Format date for IMAP: DD-MMM-YYYY
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria.append(f"SINCE {date_str}")

                # Search for messages
                status, message_numbers = imap.search(None, *search_criteria)
                if status != "OK" or not message_numbers[0]:
                    logger.info("No messages found in IMAP search")
                    return replies

                # Process each message
                for msg_num in message_numbers[0].split():
                    try:
                        status, msg_data = imap.fetch(msg_num, "(RFC822)")
                        if status != "OK":
                            continue

                        msg = self._parse_message((msg_num, msg_data))
                        if not msg:
                            continue

                        # Check each outbound message ID
                        for outbound_id in outbound_message_ids:
                            if self._is_reply_by_message_id(msg, outbound_id):
                                message_id = self._extract_message_id(msg)
                                # Deduplicate replies (some IMAP servers / mocks can surface
                                # the same message multiple times across message numbers).
                                if message_id and any(
                                    r.get("message_id") == message_id for r in replies[outbound_id]
                                ):
                                    continue

                                reply_info = {
                                    "message_id": message_id,
                                    "from": msg.get("From", ""),
                                    "subject": msg.get("Subject", ""),
                                    "date": msg.get("Date", ""),
                                    "message_number": msg_num.decode(),
                                }
                                replies[outbound_id].append(reply_info)
                                logger.info(
                                    "Reply detected by Message-ID",
                                    outbound_id=outbound_id,
                                    reply_from=reply_info["from"],
                                )

                    except Exception as e:
                        logger.warning(
                            "Error processing message", message_num=msg_num, error=str(e)
                        )
                        continue

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to detect replies", error=str(e))
            # Return empty results on error (fail gracefully)

        return replies

    def detect_reply_fallback(
        self,
        prospect_email: str,
        original_subject: str,
        since_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """
        Fallback reply detection by subject and from address.

        Args:
            prospect_email: Expected sender email address
            original_subject: Original email subject
            since_date: Only check messages since this date (defaults to Jan 1, 2026)

        Returns:
            List of reply info dicts
        """
        # Default to January 1, 2026 if no date specified (optimization: skip older emails)
        if since_date is None:
            since_date = datetime(2026, 1, 1)

        replies: list[dict[str, Any]] = []

        try:
            imap = self._create_connection()
            try:
                imap.select(self.config.mailbox)

                # Build search criteria - check ALL messages since the specified date
                # This ensures we detect replies even if they've been read, but only checks recent emails
                search_criteria = ["ALL"]
                # Format date for IMAP: DD-MMM-YYYY
                date_str = since_date.strftime("%d-%b-%Y")
                search_criteria.append(f"SINCE {date_str}")

                # Search for messages
                status, message_numbers = imap.search(None, *search_criteria)
                if status != "OK" or not message_numbers[0]:
                    return replies

                # Process each message
                for msg_num in message_numbers[0].split():
                    try:
                        status, msg_data = imap.fetch(msg_num, "(RFC822)")
                        if status != "OK":
                            continue

                        msg = self._parse_message((msg_num, msg_data))
                        if not msg:
                            continue

                        if self._is_reply_by_subject_and_from(
                            msg, original_subject, prospect_email
                        ):
                            reply_info = {
                                "message_id": self._extract_message_id(msg),
                                "from": msg.get("From", ""),
                                "subject": msg.get("Subject", ""),
                                "date": msg.get("Date", ""),
                                "message_number": msg_num.decode(),
                            }
                            replies.append(reply_info)
                            logger.info(
                                "Reply detected by fallback method",
                                from_email=prospect_email,
                                reply_from=reply_info["from"],
                            )

                    except Exception as e:
                        logger.warning(
                            "Error processing message", message_num=msg_num, error=str(e)
                        )
                        continue

            finally:
                imap.logout()

        except Exception as e:
            logger.error("Failed to detect replies (fallback)", error=str(e))

        return replies


def create_reply_detector_from_config(env_settings: Any) -> ReplyDetector:
    """
    Create ReplyDetector from environment settings.

    Args:
        env_settings: EnvSettings object with IMAP configuration

    Returns:
        ReplyDetector instance

    Raises:
        ValueError: If required IMAP settings are missing
    """
    if not env_settings.imap_host:
        raise ValueError("IMAP_HOST not configured")
    if not env_settings.imap_user:
        raise ValueError("IMAP_USER not configured")
    if not env_settings.imap_password:
        raise ValueError("IMAP_PASSWORD not configured")

    config = IMAPConfig(
        host=env_settings.imap_host,
        port=env_settings.imap_port,
        user=env_settings.imap_user,
        password=env_settings.imap_password,
        use_ssl=env_settings.imap_use_ssl,
    )

    return ReplyDetector(config)
