# Cold Emailer

A local cold-email automation tool (Hunter-like) built in Python with robust state tracking, dynamic per-contact PDF resume attachments, and follow-up sequencing that stops when a reply is detected.

## Features

- **State Tracking**: SQLite database tracks all prospect interactions and email events
- **Dynamic Attachments**: Unique PDF resume per prospect with checksum validation
- **Follow-up Sequencing**: Configurable multi-step follow-up sequences that stop on reply
- **Reply Detection**: IMAP-based detection using Message-ID threading headers
- **Safety First**: Fail-closed on attachment mismatches, dry-run mode, confirmation flags
- **Production Quality**: Fully typed, tested, and documented code

## Requirements

- Python 3.11+
- Poetry for dependency management

## Installation

1. Clone this repository
2. Install dependencies:
   ```bash
   poetry install
   ```
3. Copy `.env.example` to `.env` and configure your SMTP/IMAP settings:
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

## Project Structure

```
cold_emailer/
  README.md
  pyproject.toml
  .env.example
  .gitignore
  config/
    settings.yaml          # Main configuration
    sequences.yaml         # Follow-up sequence definitions
  data/
    prospects.csv          # Input prospects file
    resume_manifest.csv    # Resume mapping and checksums
    state.db              # SQLite database (created at runtime)
  assets/
    resumes/               # PDF resumes directory
  templates/
    initial.md            # Initial email template
    followup_1.md         # First follow-up template
    followup_2.md         # Second follow-up template
  logs/                   # Runtime logs (not committed)
  src/
    cold_emailer/
      cli.py              # CLI interface
      config.py           # Configuration management
      ingestion.py        # CSV/Excel ingestion
      attachments.py      # Resume attachment validation
      composer.py         # Email composition
      orchestrator.py     # Main orchestration logic
      utils.py            # Utilities (logging)
      mailer/
        smtp_sender.py    # SMTP email sender
        imap_reply_detector.py  # Reply detection
      state_store/
        models.py         # SQLAlchemy models
        db.py             # Database setup
        repo.py           # Repository layer
  tests/
    test_ingestion.py
    test_attachments.py
    test_state_transitions.py
    test_orchestrator_dry_run.py
```

## Configuration

### Settings (`config/settings.yaml`)

Main application settings including:
- Email configuration
- Throttling limits (daily max, per-minute)
- Safety settings
- Paths and logging

### Sequences (`config/sequences.yaml`)

Define follow-up sequences with:
- Step templates
- Wait periods between steps
- Subject line templates

### Environment Variables (`.env`)

Required variables:
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`
- `IMAP_HOST`, `IMAP_PORT`, `IMAP_USER`, `IMAP_PASSWORD`
- `DAILY_MAX_EMAILS`, `PER_MINUTE_LIMIT`
- `SAFE_MODE`, `REQUIRE_CONFIRM_SEND`

## Usage

### Initialize Database

```bash
poetry run cold-emailer init-db
```

### Ingest Prospects

```bash
poetry run cold-emailer ingest --file data/prospects.csv
```

### Run Automation (Dry Run)

```bash
poetry run cold-emailer run --file data/prospects.csv --dry-run
```

### Run Automation (Live)

```bash
poetry run cold-emailer run --file data/prospects.csv --confirm-send
```

### Check Status

```bash
poetry run cold-emailer status --limit 50
```

### Export Events

```bash
poetry run cold-emailer export-events --out logs/events.jsonl
```

## Data Format

### Prospects CSV

Required columns:
- `email` (required)
- `full_name` (required)
- `company` (required)
- `resume_id` (required)

Optional columns:
- `prospect_id` (auto-generated if missing)
- `role_title`
- `timezone`
- `sequence_id` (defaults to "default")
- `variables_json` (JSON string for template variables)

### Resume Manifest CSV

Required columns:
- `resume_id` (unique identifier)
- `relative_path` (path relative to repo root)
- `sha256` (checksum, computed if blank)
- `version` (optional)

## Safety Features

- **Checksum Validation**: Resume files are validated before sending. Mismatches prevent sending.
- **Dry Run Mode**: Test without sending emails
- **Confirmation Flag**: Require explicit confirmation for live sends
- **State Tracking**: Never double-send due to idempotent state management
- **Reply Detection**: Automatically stops follow-ups when replies are detected

## Development

### Code Quality

```bash
# Format code
poetry run black src tests

# Lint code
poetry run ruff check src tests

# Type checking
poetry run mypy src

# Run tests
poetry run pytest
```

### Project Status

This project is being implemented in phases:

- ✅ **Phase 1**: Project scaffolding (current)
- ⏳ **Phase 2**: SQLite + models + repository layer
- ⏳ **Phase 3**: Ingestion + resume manifest + checksum validator
- ⏳ **Phase 4**: Templating + email composer
- ⏳ **Phase 5**: SMTP sender + dry-run support
- ⏳ **Phase 6**: IMAP reply detector
- ⏳ **Phase 7**: Orchestrator end-to-end
- ⏳ **Phase 8**: Polish for GitHub + LinkedIn

## Security Notes

⚠️ **IMPORTANT**: 
- Never commit `.env` file or any files containing secrets
- Use app-specific passwords for Gmail/email providers
- Review all email content before sending
- Start with dry-run mode to verify behavior
- The tool validates attachments before sending to prevent wrong-file mistakes

## License

[Add your license here]

## Contributing

[Add contribution guidelines here]
