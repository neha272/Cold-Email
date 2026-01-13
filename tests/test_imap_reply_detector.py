"""Tests for IMAP reply detector."""

from datetime import datetime
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

import pytest

from cold_emailer.mailer.imap_reply_detector import IMAPConfig, ReplyDetector


@pytest.fixture
def imap_config() -> IMAPConfig:
    """Create test IMAP configuration."""
    return IMAPConfig(
        host="imap.test.com",
        port=993,
        user="test@test.com",
        password="password",
        use_ssl=True,
    )


@pytest.fixture
def reply_detector(imap_config: IMAPConfig) -> ReplyDetector:
    """Create ReplyDetector instance."""
    return ReplyDetector(imap_config)


def test_imap_config_init(imap_config: IMAPConfig) -> None:
    """Test IMAP configuration initialization."""
    assert imap_config.host == "imap.test.com"
    assert imap_config.port == 993
    assert imap_config.user == "test@test.com"
    assert imap_config.use_ssl is True


def test_extract_message_id(reply_detector: ReplyDetector) -> None:
    """Test extracting Message-ID from email."""
    msg = EmailMessage()
    msg["Message-ID"] = "<test-123@example.com>"

    msg_id = reply_detector._extract_message_id(msg)
    assert msg_id == "test-123@example.com"


def test_extract_in_reply_to(reply_detector: ReplyDetector) -> None:
    """Test extracting In-Reply-To header."""
    msg = EmailMessage()
    msg["In-Reply-To"] = "<original-123@example.com>"

    msg_ids = reply_detector._extract_in_reply_to(msg)
    assert len(msg_ids) == 1
    assert "original-123@example.com" in msg_ids


def test_extract_references(reply_detector: ReplyDetector) -> None:
    """Test extracting References header."""
    msg = EmailMessage()
    msg["References"] = "<ref1@example.com> <ref2@example.com>"

    msg_ids = reply_detector._extract_references(msg)
    assert len(msg_ids) == 2
    assert "ref1@example.com" in msg_ids
    assert "ref2@example.com" in msg_ids


def test_is_reply_by_message_id_in_reply_to(reply_detector: ReplyDetector) -> None:
    """Test reply detection via In-Reply-To header."""
    msg = EmailMessage()
    msg["In-Reply-To"] = "<original-123@example.com>"

    is_reply = reply_detector._is_reply_by_message_id(msg, "original-123@example.com")
    assert is_reply is True


def test_is_reply_by_message_id_references(reply_detector: ReplyDetector) -> None:
    """Test reply detection via References header."""
    msg = EmailMessage()
    msg["References"] = "<original-123@example.com>"

    is_reply = reply_detector._is_reply_by_message_id(msg, "original-123@example.com")
    assert is_reply is True


def test_is_reply_by_message_id_no_match(reply_detector: ReplyDetector) -> None:
    """Test reply detection with no match."""
    msg = EmailMessage()
    msg["In-Reply-To"] = "<different-123@example.com>"

    is_reply = reply_detector._is_reply_by_message_id(msg, "original-123@example.com")
    assert is_reply is False


def test_is_reply_by_subject_and_from(reply_detector: ReplyDetector) -> None:
    """Test fallback reply detection by subject and from."""
    msg = EmailMessage()
    msg["Subject"] = "Re: Original Subject"
    msg["From"] = "sender@example.com"

    is_reply = reply_detector._is_reply_by_subject_and_from(
        msg, "Original Subject", "sender@example.com"
    )
    assert is_reply is True


def test_is_reply_by_subject_and_from_no_re_prefix(reply_detector: ReplyDetector) -> None:
    """Test fallback detection without Re: prefix."""
    msg = EmailMessage()
    msg["Subject"] = "Original Subject"
    msg["From"] = "sender@example.com"

    is_reply = reply_detector._is_reply_by_subject_and_from(
        msg, "Original Subject", "sender@example.com"
    )
    assert is_reply is True


def test_is_reply_by_subject_and_from_wrong_sender(reply_detector: ReplyDetector) -> None:
    """Test fallback detection with wrong sender."""
    msg = EmailMessage()
    msg["Subject"] = "Re: Original Subject"
    msg["From"] = "different@example.com"

    is_reply = reply_detector._is_reply_by_subject_and_from(
        msg, "Original Subject", "sender@example.com"
    )
    assert is_reply is False


@patch("cold_emailer.mailer.imap_reply_detector.imaplib.IMAP4_SSL")
def test_detect_replies_by_message_id(mock_imap_class: MagicMock, reply_detector: ReplyDetector) -> None:
    """Test detecting replies by Message-ID."""
    # Mock IMAP connection
    mock_imap = MagicMock()
    mock_imap_class.return_value = mock_imap

    # Mock search results
    mock_imap.search.return_value = ("OK", [b"1 2"])
    mock_imap.select.return_value = ("OK", [b"1"])

    # Mock fetch for message 1 (reply)
    reply_msg = EmailMessage()
    reply_msg["In-Reply-To"] = "<original-123@example.com>"
    reply_msg["From"] = "sender@example.com"
    reply_msg["Subject"] = "Re: Test"
    reply_msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    reply_msg["Message-ID"] = "<reply-123@example.com>"

    mock_imap.fetch.return_value = ("OK", [(b"1", reply_msg.as_bytes())])

    outbound_ids = ["original-123@example.com"]
    replies = reply_detector.detect_replies_by_message_id(outbound_ids)

    assert len(replies) == 1
    assert "original-123@example.com" in replies
    assert len(replies["original-123@example.com"]) == 1
    assert replies["original-123@example.com"][0]["message_id"] == "reply-123@example.com"

    mock_imap.login.assert_called_once()
    mock_imap.select.assert_called_once()
    mock_imap.logout.assert_called_once()


@patch("cold_emailer.mailer.imap_reply_detector.imaplib.IMAP4_SSL")
def test_detect_replies_no_messages(mock_imap_class: MagicMock, reply_detector: ReplyDetector) -> None:
    """Test detecting replies when no messages found."""
    mock_imap = MagicMock()
    mock_imap_class.return_value = mock_imap
    mock_imap.search.return_value = ("OK", [b""])
    mock_imap.select.return_value = ("OK", [b"1"])

    outbound_ids = ["original-123@example.com"]
    replies = reply_detector.detect_replies_by_message_id(outbound_ids)

    assert len(replies) == 1
    assert len(replies["original-123@example.com"]) == 0


@patch("cold_emailer.mailer.imap_reply_detector.imaplib.IMAP4_SSL")
def test_detect_reply_fallback(mock_imap_class: MagicMock, reply_detector: ReplyDetector) -> None:
    """Test fallback reply detection."""
    mock_imap = MagicMock()
    mock_imap_class.return_value = mock_imap

    mock_imap.search.return_value = ("OK", [b"1"])
    mock_imap.select.return_value = ("OK", [b"1"])

    # Mock reply message
    reply_msg = EmailMessage()
    reply_msg["Subject"] = "Re: Original Subject"
    reply_msg["From"] = "sender@example.com"
    reply_msg["Date"] = "Mon, 1 Jan 2024 12:00:00 +0000"
    reply_msg["Message-ID"] = "<reply-123@example.com>"

    mock_imap.fetch.return_value = ("OK", [(b"1", reply_msg.as_bytes())])

    replies = reply_detector.detect_reply_fallback(
        prospect_email="sender@example.com",
        original_subject="Original Subject",
    )

    assert len(replies) == 1
    assert replies[0]["from"] == "sender@example.com"
    assert "Original Subject" in replies[0]["subject"]
