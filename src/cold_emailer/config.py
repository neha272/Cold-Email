"""Configuration management for cold-emailer."""

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseModel):
    """Email configuration."""

    default_from_name: str
    default_from_email: str
    reply_to: str | None = None
    encoding: str = "utf-8"


class ThrottlingSettings(BaseModel):
    """Throttling configuration."""

    daily_max: int
    per_minute_limit: int
    send_window_start: str
    send_window_end: str


class SafetySettings(BaseModel):
    """Safety settings."""

    require_confirm_send: bool = False
    safe_mode: bool = True
    validate_email_domain: bool = True
    max_attachment_size_mb: int = 10


class PathsSettings(BaseModel):
    """Path configuration."""

    prospects_dir: str
    resumes_dir: str
    templates_dir: str
    logs_dir: str


class LoggingSettings(BaseModel):
    """Logging configuration."""

    level: str = "INFO"
    format: str = "json"
    file: str | None = None
    max_bytes: int = 10485760
    backup_count: int = 5


class DatabaseSettings(BaseModel):
    """Database configuration."""

    path: str
    echo: bool = False


class AppSettings(BaseModel):
    """Application settings."""

    name: str
    version: str
    timezone: str = "UTC"


class Settings(BaseModel):
    """Main application settings."""

    app: AppSettings
    database: DatabaseSettings
    email: EmailSettings
    throttling: ThrottlingSettings
    safety: SafetySettings
    paths: PathsSettings
    logging: LoggingSettings


class EnvSettings(BaseSettings):
    """Environment variable settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SMTP
    smtp_host: str = Field(alias="SMTP_HOST", default="")
    smtp_port: int = Field(alias="SMTP_PORT", default=587)
    smtp_user: str = Field(alias="SMTP_USER", default="")
    smtp_password: str = Field(alias="SMTP_PASSWORD", default="")
    smtp_use_tls: bool = Field(alias="SMTP_USE_TLS", default=True)
    smtp_from_name: str = Field(alias="SMTP_FROM_NAME", default="")
    smtp_from_email: str = Field(alias="SMTP_FROM_EMAIL", default="")

    # IMAP
    imap_host: str = Field(alias="IMAP_HOST", default="")
    imap_port: int = Field(alias="IMAP_PORT", default=993)
    imap_user: str = Field(alias="IMAP_USER", default="")
    imap_password: str = Field(alias="IMAP_PASSWORD", default="")
    imap_use_ssl: bool = Field(alias="IMAP_USE_SSL", default=True)

    # Throttling
    daily_max_emails: int = Field(alias="DAILY_MAX_EMAILS", default=50)
    per_minute_limit: int = Field(alias="PER_MINUTE_LIMIT", default=5)

    # Safety
    safe_mode: bool = Field(alias="SAFE_MODE", default=True)
    require_confirm_send: bool = Field(alias="REQUIRE_CONFIRM_SEND", default=False)


def load_config(config_path: str = "config/settings.yaml") -> Settings:
    """
    Load configuration from YAML file and environment variables.

    Args:
        config_path: Path to settings YAML file

    Returns:
        Loaded Settings object

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If required settings are missing
    """
    # Load environment variables
    load_dotenv()

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_file, encoding="utf-8") as f:
            config_data = yaml.safe_load(f)
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(config_file, encoding="utf-8-sig") as f:
            config_data = yaml.safe_load(f)

    # Simple template substitution for environment variables
    # This is a basic implementation - could be enhanced
    def substitute_env_vars(obj: Any) -> Any:
        """Recursively substitute environment variable references."""
        if isinstance(obj, dict):
            return {k: substitute_env_vars(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [substitute_env_vars(item) for item in obj]
        elif isinstance(obj, str):
            if obj.startswith("{{ env.") and obj.endswith(" }}"):
                var_name = obj[7:-3].strip()
                default = None
                if "|" in var_name:
                    parts = var_name.split("|")
                    var_name = parts[0].strip()
                    if len(parts) > 1:
                        default_part = parts[1].strip()
                        if default_part.startswith("default("):
                            default = default_part[8:-1].strip().strip("'\"")
                        elif "int" in default_part:
                            try:
                                default = int(os.getenv(var_name, "0"))  # type: ignore[assignment]
                            except ValueError:
                                default = 0  # type: ignore[assignment]
                        elif "bool" in default_part:
                            default = os.getenv(var_name, "false").lower() == "true"  # type: ignore[assignment]
                # If no default was specified and the env var is missing, fall back to empty
                # string so Pydantic string fields don't crash on None.
                return os.getenv(var_name, default if default is not None else "")
            return obj
        return obj

    config_data = substitute_env_vars(config_data)

    return Settings(**config_data)


def load_sequences(sequences_path: str = "config/sequences.yaml") -> dict[str, Any]:
    """
    Load sequence definitions from YAML file.

    Args:
        sequences_path: Path to sequences YAML file

    Returns:
        Dictionary of sequence definitions

    Raises:
        FileNotFoundError: If sequences file doesn't exist
    """
    seq_file = Path(sequences_path)
    if not seq_file.exists():
        raise FileNotFoundError(f"Sequences file not found: {sequences_path}")

    try:
        with open(seq_file, encoding="utf-8") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]
    except UnicodeDecodeError:
        # Try with different encoding if UTF-8 fails
        with open(seq_file, encoding="utf-8-sig") as f:
            return yaml.safe_load(f)  # type: ignore[no-any-return]


def validate_env_on_startup(skip_email_check: bool = False) -> tuple[bool, list[str]]:
    """
    Validate required environment variables on startup.

    Args:
        skip_email_check: Skip SMTP/IMAP validation (useful for web-only mode)

    Returns:
        Tuple of (is_valid, list of error messages)
    """
    errors = []

    try:
        env_settings = EnvSettings()

        # Check SMTP settings (required for sending emails)
        if not skip_email_check:
            if not env_settings.smtp_host:
                errors.append("SMTP_HOST is not set")
            if not env_settings.smtp_user:
                errors.append("SMTP_USER is not set")
            if not env_settings.smtp_password:
                errors.append("SMTP_PASSWORD is not set")
            if not env_settings.smtp_from_email:
                errors.append("SMTP_FROM_EMAIL is not set")

            # Check IMAP settings (required for reply detection)
            if not env_settings.imap_host:
                errors.append("IMAP_HOST is not set")
            if not env_settings.imap_user:
                errors.append("IMAP_USER is not set")
            if not env_settings.imap_password:
                errors.append("IMAP_PASSWORD is not set")

        return len(errors) == 0, errors

    except Exception as e:
        errors.append(f"Failed to load environment settings: {str(e)}")
        return False, errors
