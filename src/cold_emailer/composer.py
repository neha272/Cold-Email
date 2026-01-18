"""Email composition using Jinja2 templates."""

import json
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, Template, select_autoescape

from cold_emailer.utils import get_logger

logger = get_logger(__name__)


class EmailComposer:
    """Composes emails from Jinja2 templates."""

    def __init__(self, templates_dir: Path, sender_name: str, sender_email: str) -> None:
        """
        Initialize email composer.

        Args:
            templates_dir: Directory containing email templates
            sender_name: Default sender name
            sender_email: Default sender email
        """
        self.templates_dir = Path(templates_dir)
        self.sender_name = sender_name
        self.sender_email = sender_email

        # Setup Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def load_template(self, template_name: str) -> Template:
        """
        Load a template by name.

        Args:
            template_name: Template name (without extension)

        Returns:
            Jinja2 Template object

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        template_path = self.templates_dir / f"{template_name}.md"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        return self.env.get_template(f"{template_name}.md")

    def render_template(self, template: Template, variables: dict[str, Any]) -> str:
        """
        Render template with variables.

        Args:
            template: Jinja2 Template object
            variables: Dictionary of template variables

        Returns:
            Rendered template string
        """
        # Add default variables
        context = {
            "sender_name": self.sender_name,
            "sender_email": self.sender_email,
            **variables,
        }
        return template.render(**context)

    def parse_template_content(self, content: str) -> tuple[str, str]:
        """
        Parse template content to extract subject and body.

        Template format:
        Subject: <subject line>
        <blank line>
        <body content>

        Args:
            content: Template content string

        Returns:
            Tuple of (subject, body)
        """
        lines = content.strip().split("\n")
        subject = ""
        body_start = 0

        # Look for "Subject:" line
        for i, line in enumerate(lines):
            if line.startswith("Subject:"):
                subject = line[8:].strip()  # Remove "Subject:" prefix
                body_start = i + 1
                # Skip blank line after subject if present
                if body_start < len(lines) and not lines[body_start].strip():
                    body_start += 1
                break

        # If no subject found, use first line as subject
        if not subject and lines:
            subject = lines[0].strip()
            body_start = 1
            # Skip blank line if present
            if body_start < len(lines) and not lines[body_start].strip():
                body_start += 1

        body = "\n".join(lines[body_start:]).strip()
        return subject, body

    def compose_email(
        self,
        template_name: str,
        to_email: str,
        to_name: str,
        variables: dict[str, Any] | None = None,
        subject_override: str | None = None,
        from_name: str | None = None,
        from_email: str | None = None,
        reply_to: str | None = None,
    ) -> EmailMessage:
        """
        Compose an email message from a template.

        Args:
            template_name: Name of template to use
            to_email: Recipient email address
            to_name: Recipient name
            variables: Template variables (merged with prospect data)
            subject_override: Override subject line (optional)
            from_name: Sender name (defaults to composer's sender_name)
            from_email: Sender email (defaults to composer's sender_email)
            reply_to: Reply-to address (optional)

        Returns:
            EmailMessage object ready to send

        Raises:
            FileNotFoundError: If template doesn't exist
        """
        template = self.load_template(template_name)

        # Merge variables
        template_vars: dict[str, Any] = {
            "email": to_email,
            "full_name": to_name,
            **(variables or {}),
        }

        # Render template
        rendered = self.render_template(template, template_vars)

        # Parse subject and body
        subject, body = self.parse_template_content(rendered)

        # Use override if provided
        if subject_override:
            # Render subject override as template too
            subject_template = self.env.from_string(subject_override)
            subject = subject_template.render(**template_vars)

        # Create email message
        msg = EmailMessage()
        msg["From"] = f"{from_name or self.sender_name} <{from_email or self.sender_email}>"
        msg["To"] = f"{to_name} <{to_email}>"
        msg["Subject"] = subject
        if reply_to:
            msg["Reply-To"] = reply_to

        # Set body (plain text)
        msg.set_content(body)

        # Generate Message-ID for tracking
        import email.utils

        msg["Message-ID"] = email.utils.make_msgid(domain=self.sender_email.split("@")[1])

        return msg

    def get_template_variables_from_prospect(
        self, prospect: Any, sequences: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Extract template variables from prospect object.

        Args:
            prospect: Prospect model instance
            sequences: Sequence definitions (optional, for sequence-specific vars)

        Returns:
            Dictionary of template variables
        """
        variables: dict[str, Any] = {
            "email": prospect.email,
            "full_name": prospect.full_name,
            "company": prospect.company,
            "role_title": prospect.role_title or "",
            "timezone": prospect.timezone or "",
        }

        # Parse variables_json if present
        if prospect.variables_json:
            try:
                custom_vars = json.loads(prospect.variables_json)
                if isinstance(custom_vars, dict):
                    variables.update(custom_vars)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(
                    "Failed to parse variables_json",
                    prospect_id=str(prospect.id),
                    error=str(e),
                )

        return variables

    def get_sequence_step(
        self, sequences: dict[str, Any], sequence_id: str, step: int
    ) -> dict[str, Any] | None:
        """
        Get sequence step configuration.

        Args:
            sequences: Sequence definitions dictionary
            sequence_id: Sequence identifier
            step: Step number

        Returns:
            Step configuration dictionary or None if not found
        """
        sequence = sequences.get("sequences", {}).get(sequence_id)
        if not sequence:
            return None

        steps = sequence.get("steps", [])
        for step_config in steps:
            if step_config.get("step") == step:
                return step_config  # type: ignore[no-any-return]

        return None


def create_composer_from_config(
    settings: Any, sequences: dict[str, Any] | None = None
) -> EmailComposer:
    """
    Create EmailComposer from configuration.

    Args:
        settings: Settings object from load_config
        sequences: Optional sequence definitions

    Returns:
        EmailComposer instance
    """
    templates_dir = Path(settings.paths.templates_dir)
    sender_name = settings.email.default_from_name
    sender_email = settings.email.default_from_email

    return EmailComposer(
        templates_dir=templates_dir,
        sender_name=sender_name,
        sender_email=sender_email,
    )
