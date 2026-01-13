"""SMTP email sender implementation."""

import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from cold_emailer.utils import get_logger

logger = get_logger(__name__)


class SMTPConfig:
    """SMTP configuration."""

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        use_tls: bool = True,
        from_name: str = "",
        from_email: str = "",
    ) -> None:
        """
        Initialize SMTP configuration.

        Args:
            host: SMTP server hostname
            port: SMTP server port
            user: SMTP username
            password: SMTP password
            use_tls: Use TLS encryption
            from_name: Default sender name
            from_email: Default sender email
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.use_tls = use_tls
        self.from_name = from_name
        self.from_email = from_email


class SMTPSender:
    """SMTP email sender with attachment support."""

    def __init__(self, config: SMTPConfig) -> None:
        """
        Initialize SMTP sender.

        Args:
            config: SMTP configuration
        """
        self.config = config

    def _create_connection(self) -> smtplib.SMTP:
        """
        Create SMTP connection.

        Returns:
            SMTP connection object

        Raises:
            smtplib.SMTPException: If connection fails
        """
        try:
            smtp = smtplib.SMTP(self.config.host, self.config.port, timeout=30)
            if self.config.use_tls:
                smtp.starttls()
            if self.config.user and self.config.password:
                smtp.login(self.config.user, self.config.password)
            return smtp
        except Exception as e:
            logger.error("Failed to create SMTP connection", error=str(e))
            raise

    def attach_file(self, msg: EmailMessage, file_path: Path, filename: str | None = None) -> None:
        """
        Attach a file to email message.

        Args:
            msg: EmailMessage object
            file_path: Path to file to attach
            filename: Optional filename override

        Raises:
            FileNotFoundError: If file doesn't exist
            IOError: If file cannot be read
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Attachment file not found: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")

        with open(file_path, "rb") as f:
            file_data = f.read()
            filename = filename or file_path.name
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="pdf",
                filename=filename,
            )

        logger.debug("Attached file to email", file=str(file_path), filename=filename)

    def send(
        self,
        msg: EmailMessage,
        dry_run: bool = False,
    ) -> tuple[bool, str | None, str | None]:
        """
        Send email message via SMTP.

        Args:
            msg: EmailMessage object to send
            dry_run: If True, don't actually send (just validate)

        Returns:
            Tuple of (success, message_id, error_message)
            - success: True if sent successfully (or dry-run)
            - message_id: Outbound Message-ID header value
            - error_message: Error description if failed

        Raises:
            ValueError: If message is invalid
        """
        # Extract Message-ID
        message_id = msg.get("Message-ID", "").strip("<>")

        if dry_run:
            logger.info(
                "DRY RUN: Would send email",
                to=msg.get("To"),
                subject=msg.get("Subject"),
                message_id=message_id,
            )
            return True, message_id, None

        # Validate message
        if not msg.get("To"):
            return False, message_id, "Missing 'To' address"
        if not msg.get("Subject"):
            return False, message_id, "Missing 'Subject'"

        try:
            smtp = self._create_connection()
            try:
                # Send message
                send_result = smtp.send_message(msg)
                smtp.quit()

                # Extract provider message ID if available
                provider_message_id = None
                if send_result:
                    # Some SMTP servers return message ID
                    provider_message_id = str(send_result) if send_result else None

                logger.info(
                    "Email sent successfully",
                    to=msg.get("To"),
                    subject=msg.get("Subject"),
                    message_id=message_id,
                    provider_id=provider_message_id,
                )

                return True, message_id, None

            except smtplib.SMTPException as e:
                smtp.quit()
                error_msg = f"SMTP error: {e}"
                logger.error("Failed to send email", error=error_msg, message_id=message_id)
                return False, message_id, error_msg

        except Exception as e:
            error_msg = f"Connection error: {e}"
            logger.error("Failed to connect to SMTP server", error=error_msg)
            return False, message_id, error_msg

    def send_with_attachment(
        self,
        msg: EmailMessage,
        attachment_path: Path | None = None,
        attachment_filename: str | None = None,
        dry_run: bool = False,
    ) -> tuple[bool, str | None, str | None, str | None]:
        """
        Send email with optional attachment.

        Args:
            msg: EmailMessage object
            attachment_path: Path to attachment file
            attachment_filename: Optional filename for attachment
            dry_run: If True, don't actually send

        Returns:
            Tuple of (success, message_id, attachment_sha256, error_message)
            - success: True if sent successfully
            - message_id: Outbound Message-ID
            - attachment_sha256: SHA256 of attachment if attached
            - error_message: Error description if failed
        """
        attachment_sha256 = None

        # Attach file if provided
        if attachment_path:
            try:
                from cold_emailer.attachments import compute_sha256

                self.attach_file(msg, attachment_path, attachment_filename)
                attachment_sha256 = compute_sha256(attachment_path)
            except Exception as e:
                error_msg = f"Failed to attach file: {e}"
                logger.error("Attachment error", error=error_msg)
                return False, None, None, error_msg

        success, message_id, error = self.send(msg, dry_run=dry_run)

        return success, message_id, attachment_sha256, error


def create_smtp_sender_from_config(env_settings: Any) -> SMTPSender:
    """
    Create SMTPSender from environment settings.

    Args:
        env_settings: EnvSettings object with SMTP configuration

    Returns:
        SMTPSender instance

    Raises:
        ValueError: If required SMTP settings are missing
    """
    if not env_settings.smtp_host:
        raise ValueError("SMTP_HOST not configured")
    if not env_settings.smtp_user:
        raise ValueError("SMTP_USER not configured")
    if not env_settings.smtp_password:
        raise ValueError("SMTP_PASSWORD not configured")

    config = SMTPConfig(
        host=env_settings.smtp_host,
        port=env_settings.smtp_port,
        user=env_settings.smtp_user,
        password=env_settings.smtp_password,
        use_tls=env_settings.smtp_use_tls,
        from_name=env_settings.smtp_from_name,
        from_email=env_settings.smtp_from_email,
    )

    return SMTPSender(config)
