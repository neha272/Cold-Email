"""Tests for email composition."""

from pathlib import Path

import pytest
from cold_emailer.composer import EmailComposer


@pytest.fixture
def templates_dir(tmp_path: Path) -> Path:
    """Create a temporary templates directory with sample templates."""
    templates = tmp_path / "templates"
    templates.mkdir()

    # Create Initial template
    (templates / "Initial.md").write_text(
        """Subject: Quick question about {{ company }}

Hi {{ full_name }},

I hope this email finds you well. I came across {{ company }} and was impressed.

Best regards,
{{ sender_name }}"""
    )

    # Create followup template
    (templates / "Followup 1.md").write_text(
        """Subject: Following up

Hi {{ full_name }},

Just following up on my previous message.

Thanks,
{{ sender_name }}"""
    )

    return templates


def test_email_composer_init(templates_dir: Path) -> None:
    """Test EmailComposer initialization."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    assert composer.templates_dir == templates_dir
    assert composer.sender_name == "Test Sender"
    assert composer.sender_email == "sender@example.com"


def test_load_template(templates_dir: Path) -> None:
    """Test loading a template."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    template = composer.load_template("Initial")
    assert template is not None


def test_load_template_not_found(templates_dir: Path) -> None:
    """Test loading a non-existent template."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    with pytest.raises(FileNotFoundError):
        composer.load_template("nonexistent")


def test_parse_template_content() -> None:
    """Test parsing template content."""
    composer = EmailComposer(
        templates_dir=Path("/tmp"),
        sender_name="Test",
        sender_email="test@example.com",
    )

    content = """Subject: Test Subject

This is the body content.
It has multiple lines."""
    subject, body = composer.parse_template_content(content)

    assert subject == "Test Subject"
    assert "This is the body content" in body


def test_parse_template_content_no_subject() -> None:
    """Test parsing template without explicit subject."""
    composer = EmailComposer(
        templates_dir=Path("/tmp"),
        sender_name="Test",
        sender_email="test@example.com",
    )

    content = """First line as subject

This is the body."""
    subject, body = composer.parse_template_content(content)

    assert subject == "First line as subject"
    assert "This is the body" in body


def test_render_template(templates_dir: Path) -> None:
    """Test template rendering."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    template = composer.load_template("Initial")
    variables = {
        "full_name": "John Doe",
        "company": "Acme Corp",
    }

    rendered = composer.render_template(template, variables)
    assert "John Doe" in rendered
    assert "Acme Corp" in rendered
    assert "Test Sender" in rendered


def test_compose_email(templates_dir: Path) -> None:
    """Test composing an email."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    variables = {
        "full_name": "John Doe",
        "company": "Acme Corp",
    }

    msg = composer.compose_email(
        template_name="Initial",
        to_email="recipient@example.com",
        to_name="John Doe",
        variables=variables,
    )

    assert msg["To"] == "John Doe <recipient@example.com>"
    assert msg["From"] == "Test Sender <sender@example.com>"
    assert "Acme Corp" in msg["Subject"]
    assert "John Doe" in msg.get_content()
    assert msg["Message-ID"] is not None


def test_compose_email_subject_override(templates_dir: Path) -> None:
    """Test composing email with subject override."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    variables = {
        "full_name": "John Doe",
        "company": "Acme Corp",
    }

    msg = composer.compose_email(
        template_name="Initial",
        to_email="recipient@example.com",
        to_name="John Doe",
        variables=variables,
        subject_override="Custom Subject for {{ company }}",
    )

    assert "Custom Subject for Acme Corp" in msg["Subject"]


def test_compose_email_reply_to(templates_dir: Path) -> None:
    """Test composing email with reply-to."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    msg = composer.compose_email(
        template_name="Initial",
        to_email="recipient@example.com",
        to_name="John Doe",
        reply_to="reply@example.com",
    )

    assert msg["Reply-To"] == "reply@example.com"


def test_get_template_variables_from_prospect(templates_dir: Path) -> None:
    """Test extracting variables from prospect."""
    composer = EmailComposer(
        templates_dir=templates_dir,
        sender_name="Test Sender",
        sender_email="sender@example.com",
    )

    # Mock prospect object
    class MockProspect:
        email = "test@example.com"
        full_name = "Test User"
        company = "Test Corp"
        role_title = "Engineer"
        timezone = "UTC"
        variables_json = '{"custom_var": "value"}'

    prospect = MockProspect()
    variables = composer.get_template_variables_from_prospect(prospect)

    assert variables["email"] == "test@example.com"
    assert variables["full_name"] == "Test User"
    assert variables["company"] == "Test Corp"
    assert variables["role_title"] == "Engineer"
    assert variables["custom_var"] == "value"


def test_get_sequence_step() -> None:
    """Test getting sequence step configuration."""
    composer = EmailComposer(
        templates_dir=Path("/tmp"),
        sender_name="Test",
        sender_email="test@example.com",
    )

    sequences = {
        "sequences": {
            "default": {
                "steps": [
                    {"step": 0, "template": "Initial", "wait_days": 3},
                    {"step": 1, "template": "Followup 1", "wait_days": 5},
                ]
            }
        }
    }

    step = composer.get_sequence_step(sequences, "default", 0)
    assert step is not None
    assert step["template"] == "Initial"
    assert step["wait_days"] == 3

    step = composer.get_sequence_step(sequences, "default", 1)
    assert step is not None
    assert step["template"] == "Followup 1"

    step = composer.get_sequence_step(sequences, "default", 99)
    assert step is None

    step = composer.get_sequence_step(sequences, "nonexistent", 0)
    assert step is None
