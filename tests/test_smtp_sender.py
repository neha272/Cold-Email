"""Tests for SMTP sender."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cold_emailer.mailer.smtp_sender import SMTPConfig, SMTPSender


@pytest.fixture
def smtp_config() -> SMTPConfig:
    """Create test SMTP configuration."""
    return SMTPConfig(
        host="smtp.test.com",
        port=587,
        user="test@test.com",
        password="password",
        use_tls=True,
        from_name="Test Sender",
        from_email="test@test.com",
    )


@pytest.fixture
def email_message() -> "EmailMessage":
    """Create test email message."""
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["From"] = "test@test.com"
    msg["To"] = "recipient@test.com"
    msg["Subject"] = "Test Subject"
    msg.set_content("Test body")
    msg["Message-ID"] = "<test-123@test.com>"
    return msg


def test_smtp_config_init(smtp_config: SMTPConfig) -> None:
    """Test SMTP configuration initialization."""
    assert smtp_config.host == "smtp.test.com"
    assert smtp_config.port == 587
    assert smtp_config.user == "test@test.com"
    assert smtp_config.use_tls is True


def test_smtp_sender_init(smtp_config: SMTPConfig) -> None:
    """Test SMTP sender initialization."""
    sender = SMTPSender(smtp_config)
    assert sender.config == smtp_config


def test_attach_file(smtp_config: SMTPConfig, email_message: "EmailMessage") -> None:
    """Test attaching file to email."""
    sender = SMTPSender(smtp_config)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        sender.attach_file(email_message, temp_path, "test.pdf")

        # Check attachment was added
        assert len(email_message.get_payload()) > 1  # Should have text + attachment
    finally:
        temp_path.unlink()


def test_attach_file_not_found(smtp_config: SMTPConfig, email_message: "EmailMessage") -> None:
    """Test attaching non-existent file."""
    sender = SMTPSender(smtp_config)
    missing_path = Path("/nonexistent/file.pdf")

    with pytest.raises(FileNotFoundError):
        sender.attach_file(email_message, missing_path)


@patch("cold_emailer.mailer.smtp_sender.smtplib.SMTP")
def test_send_dry_run(mock_smtp: MagicMock, smtp_config: SMTPConfig, email_message: "EmailMessage") -> None:
    """Test sending email in dry-run mode."""
    sender = SMTPSender(smtp_config)

    success, message_id, error = sender.send(email_message, dry_run=True)

    assert success is True
    assert message_id == "test-123@test.com"
    assert error is None
    # Should not create SMTP connection in dry-run
    mock_smtp.assert_not_called()


@patch("cold_emailer.mailer.smtp_sender.smtplib.SMTP")
def test_send_success(mock_smtp: MagicMock, smtp_config: SMTPConfig, email_message: "EmailMessage") -> None:
    """Test successful email send."""
    sender = SMTPSender(smtp_config)

    # Mock SMTP connection
    mock_conn = MagicMock()
    mock_conn.send_message.return_value = {}
    mock_smtp.return_value = mock_conn

    success, message_id, error = sender.send(email_message, dry_run=False)

    assert success is True
    assert message_id == "test-123@test.com"
    assert error is None
    mock_conn.starttls.assert_called_once()
    mock_conn.login.assert_called_once_with("test@test.com", "password")
    mock_conn.send_message.assert_called_once()
    mock_conn.quit.assert_called_once()


@patch("cold_emailer.mailer.smtp_sender.smtplib.SMTP")
def test_send_failure(mock_smtp: MagicMock, smtp_config: SMTPConfig, email_message: "EmailMessage") -> None:
    """Test email send failure."""
    sender = SMTPSender(smtp_config)

    # Mock SMTP connection with error
    mock_conn = MagicMock()
    mock_conn.send_message.side_effect = Exception("SMTP error")
    mock_smtp.return_value = mock_conn

    success, message_id, error = sender.send(email_message, dry_run=False)

    assert success is False
    assert message_id == "test-123@test.com"
    assert error is not None
    assert "SMTP error" in error


def test_send_missing_to(smtp_config: SMTPConfig) -> None:
    """Test sending email with missing 'To' address."""
    from email.message import EmailMessage

    sender = SMTPSender(smtp_config)
    msg = EmailMessage()
    msg["Subject"] = "Test"
    msg.set_content("Body")

    success, message_id, error = sender.send(msg, dry_run=False)

    assert success is False
    assert error is not None
    assert "Missing 'To'" in error


def test_send_missing_subject(smtp_config: SMTPConfig) -> None:
    """Test sending email with missing subject."""
    from email.message import EmailMessage

    sender = SMTPSender(smtp_config)
    msg = EmailMessage()
    msg["To"] = "test@test.com"
    msg.set_content("Body")

    success, message_id, error = sender.send(msg, dry_run=False)

    assert success is False
    assert error is not None
    assert "Missing 'Subject'" in error


@patch("cold_emailer.mailer.smtp_sender.smtplib.SMTP")
def test_send_with_attachment(
    mock_smtp: MagicMock, smtp_config: SMTPConfig, email_message: "EmailMessage"
) -> None:
    """Test sending email with attachment."""
    sender = SMTPSender(smtp_config)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        # Mock SMTP connection
        mock_conn = MagicMock()
        mock_conn.send_message.return_value = {}
        mock_smtp.return_value = mock_conn

        success, message_id, sha256, error = sender.send_with_attachment(
            email_message, attachment_path=temp_path, dry_run=False
        )

        assert success is True
        assert message_id == "test-123@test.com"
        assert sha256 is not None
        assert len(sha256) == 64  # SHA256 hex length
        assert error is None
    finally:
        temp_path.unlink()


@patch("cold_emailer.mailer.smtp_sender.smtplib.SMTP")
def test_send_with_attachment_dry_run(
    mock_smtp: MagicMock, smtp_config: SMTPConfig, email_message: "EmailMessage"
) -> None:
    """Test sending email with attachment in dry-run mode."""
    sender = SMTPSender(smtp_config)

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".pdf") as f:
        f.write("test content")
        temp_path = Path(f.name)

    try:
        success, message_id, sha256, error = sender.send_with_attachment(
            email_message, attachment_path=temp_path, dry_run=True
        )

        assert success is True
        assert message_id == "test-123@test.com"
        assert sha256 is not None
        assert error is None
        # Should not create SMTP connection
        mock_smtp.assert_not_called()
    finally:
        temp_path.unlink()


def test_send_with_attachment_missing_file(
    smtp_config: SMTPConfig, email_message: "EmailMessage"
) -> None:
    """Test sending with non-existent attachment file."""
    sender = SMTPSender(smtp_config)
    missing_path = Path("/nonexistent/file.pdf")

    success, message_id, sha256, error = sender.send_with_attachment(
        email_message, attachment_path=missing_path, dry_run=False
    )

    assert success is False
    assert error is not None
    assert "not found" in error.lower()
