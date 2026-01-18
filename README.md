# Cold Emailer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/poetry-1.5+-blue.svg)](https://python-poetry.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Docker Image](https://img.shields.io/badge/docker%20image-ghcr.io%2Fneha272%2Fcold--email-blue)](https://github.com/neha272/Cold-Email/pkgs/container/cold-email)

A production-quality local cold-email automation tool (Hunter-like) built in Python with robust state tracking, dynamic per-contact PDF resume attachments, and follow-up sequencing that automatically stops when a reply is detected.

## ✨ Features

- **📊 State Tracking**: SQLite database tracks all prospect interactions and email events with full audit trail
- **📎 Dynamic Attachments**: Unique PDF resume per prospect with SHA256 checksum validation (fail-closed safety)
- **🔄 Follow-up Sequencing**: Configurable multi-step follow-up sequences that automatically stop on reply detection
- **📬 Reply Detection**: IMAP-based detection using Message-ID threading headers with fallback matching
- **🛡️ Safety First**: Fail-closed on attachment mismatches, dry-run mode, confirmation flags, throttling
- **🏭 Production Quality**: Fully typed (mypy), tested (pytest), documented, and linted (black + ruff)
- **⚡ Idempotent**: Running twice in a day never double-sends
- **📈 Throttling**: Daily max and per-minute limits with send window support

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI Interface                           │
│                    (Typer-based commands)                       │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Orchestrator                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │   Ingest     │  │   Detect    │  │     Send     │          │
│  │  Prospects   │→ │   Replies   │→ │    Emails    │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│  Ingestion   │   │   Composer   │   │  SMTP Sender  │
│  (CSV/Excel) │   │   (Jinja2)   │   │   + IMAP     │
└──────────────┘   └──────────────┘   └──────────────┘
        │                    │                    │
        ▼                    ▼                    ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Resume     │   │   Templates   │   │   Reply      │
│   Manifest   │   │   (Markdown) │   │   Detector   │
└──────────────┘   └──────────────┘   └──────────────┘
                             │
                             ▼
                    ┌──────────────┐
                    │  State Store │
                    │   (SQLite)   │
                    │  - Prospects │
                    │  - Events    │
                    └──────────────┘
```

## 📋 Requirements

- **Docker** (recommended) - Docker 20.10+ and Docker Compose 2.0+
- **OR** Python 3.11+ with Poetry 1.5+ for local development
- SMTP server access (Gmail, Outlook, etc.)
- IMAP server access (for reply detection)

## 🚀 Quick Start

### 🐳 Docker Quickstart (Recommended)

The fastest way to get started is using Docker. The application runs as a web interface accessible in your browser.

1. **Clone the repository**
   ```bash
   git clone https://github.com/neha272/Cold-Email.git
   cd Cold-Email
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your SMTP/IMAP credentials
   ```

3. **Start the application**
   ```bash
   docker compose up --build
   ```

4. **Access the web interface**
   - Open your browser to `http://localhost:5000`
   - The web interface provides a complete UI for managing prospects, running campaigns, and viewing statistics

5. **Initialize the database** (first time only)
   ```bash
   docker compose exec cold-emailer cold-emailer init-db
   ```

6. **Prepare your data**
   - Add prospects to `data/prospects.xlsx` (or use the web interface)
   - Add resumes to `data/resumes/`
   - Configure email sequences via the web interface or edit `config/sequences.yaml`

The Docker setup automatically:
- ✅ Builds an optimized production image
- ✅ Runs as a non-root user for security
- ✅ Persists data in `./data` and `./logs` directories
- ✅ Includes health checks
- ✅ Restarts automatically on failure

**Stop the application:**
```bash
docker compose down
```

### 📦 Using Prebuilt Image

You can use the prebuilt image from GitHub Container Registry without building locally:

```bash
# Pull the latest image
docker pull ghcr.io/neha272/cold-email:latest

# Run with docker-compose (update image in docker-compose.yml)
# Or run directly:
docker run -d \
  --name cold-emailer \
  -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/templates:/app/templates:ro \
  --env-file .env \
  ghcr.io/neha272/cold-email:latest
```

**Image Location:** `ghcr.io/neha272/cold-email:latest`

Images are automatically published to GitHub Container Registry on:
- Pushes to `main` branch (tagged as `latest`)
- New releases/tags (tagged with version)

### 💻 No-Docker Installation (Local Development)

For local development without Docker:

1. **Clone the repository**
   ```bash
   git clone https://github.com/neha272/Cold-Email.git
   cd Cold-Email
   ```

2. **Install dependencies**
   ```bash
   poetry install
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your SMTP/IMAP credentials
   ```

4. **Initialize database**
   ```bash
   poetry run cold-emailer init-db
   ```

5. **Start web interface**
   ```bash
   poetry run cold-emailer web
   # Or use the CLI directly
   poetry run cold-emailer run --file data/prospects.xlsx --dry-run
   ```

6. **Prepare your data**
   - Add prospects to `data/prospects.xlsx` (or CSV)
   - Add resumes to `data/resumes/`
   - Update email sequences in `config/sequences.yaml`

## 📁 Project Structure

```
cold_emailer/
├── README.md                 # This file
├── pyproject.toml           # Poetry configuration
├── .env.example             # Environment variable template
├── .gitignore               # Git ignore rules
│
├── config/
│   ├── settings.yaml        # Main application configuration
│   └── sequences.yaml       # Follow-up sequence definitions
│
├── data/
│   ├── prospects.xlsx       # Input prospects file (example, Excel or CSV)
│   ├── resume_manifest.xlsx # Resume mapping and checksums (Excel or CSV)
│   └── state.db             # SQLite database (created at runtime)
│
├── assets/
│   └── resumes/            # PDF resumes directory
│
├── templates/
│   ├── initial.md          # Initial email template
│   ├── followup_1.md       # First follow-up template
│   └── followup_2.md       # Second follow-up template
│
├── logs/                   # Runtime logs (not committed)
│
├── src/
│   └── cold_emailer/
│       ├── cli.py           # CLI interface
│       ├── config.py        # Configuration management
│       ├── ingestion.py     # CSV/Excel ingestion
│       ├── attachments.py   # Resume attachment validation
│       ├── composer.py      # Email composition
│       ├── orchestrator.py  # Main orchestration logic
│       ├── utils.py          # Utilities (logging)
│       ├── mailer/
│       │   ├── smtp_sender.py         # SMTP email sender
│       │   └── imap_reply_detector.py # Reply detection
│       └── state_store/
│           ├── models.py    # SQLAlchemy models
│           ├── db.py        # Database setup
│           └── repo.py      # Repository layer
│
└── tests/
    ├── test_ingestion.py
    ├── test_attachments.py
    ├── test_state_transitions.py
    ├── test_composer.py
    ├── test_smtp_sender.py
    ├── test_imap_reply_detector.py
    └── test_orchestrator_dry_run.py
```

## ⚙️ Configuration

### Settings (`config/settings.yaml`)

Main application settings including:
- Email configuration (from name, reply-to)
- Throttling limits (daily max, per-minute, send window)
- Safety settings (require confirmation, safe mode)
- Paths and logging configuration

### Sequences (`config/sequences.yaml`)

Define follow-up sequences with:
- Step templates (which template to use)
- Wait periods between steps (in days)
- Subject line templates (Jinja2 syntax)

Example:
```yaml
sequences:
  default:
    name: "Default Sequence"
    steps:
      - step: 0
        template: "initial"
        wait_days: 3
        subject: "Quick question about {{ company }}"
      - step: 1
        template: "followup_1"
        wait_days: 5
        subject: "Following up on my message"
```

### Environment Variables (`.env`)

**Required variables:**
```bash
# SMTP Configuration
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
SMTP_FROM_NAME=Your Name
SMTP_FROM_EMAIL=your-email@gmail.com

# IMAP Configuration (for reply detection)
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-app-password
IMAP_USE_SSL=true

# Throttling
DAILY_MAX_EMAILS=50
PER_MINUTE_LIMIT=5

# Safety
SAFE_MODE=true
REQUIRE_CONFIRM_SEND=false
```

**⚠️ Security Note**: Never commit `.env` file. Use app-specific passwords for Gmail/email providers.

## 📊 Usage

### Web Interface (Docker)

When running with Docker, access the web interface at `http://localhost:5000`:

- **Dashboard**: View statistics and run campaigns
- **Prospects**: Add, edit, import, and manage prospects
- **Sequences**: Configure email follow-up sequences
- **Statistics**: View campaign analytics and performance
- **Settings**: View application configuration

### CLI Commands

#### Initialize Database

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer init-db
```

**Local:**
```bash
poetry run cold-emailer init-db
```

#### Ingest Prospects

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer ingest --file data/prospects.xlsx
```

**Local:**
```bash
poetry run cold-emailer ingest --file data/prospects.xlsx
# or
poetry run cold-emailer ingest --file data/prospects.csv
```

Options:
- `--manifest`: Path to resume manifest (default: `data/resume_manifest.xlsx`)
- `--reset-state`: Reset state for existing prospects

#### Run Automation (Dry Run)

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer run --file data/prospects.xlsx --dry-run
```

**Local:**
```bash
poetry run cold-emailer run --file data/prospects.xlsx --dry-run
```

#### Run Automation (Live)

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer run --file data/prospects.xlsx --confirm-send
```

**Local:**
```bash
poetry run cold-emailer run --file data/prospects.xlsx --confirm-send
```

#### Check Status

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer status --limit 50
```

**Local:**
```bash
poetry run cold-emailer status --limit 50
```

#### Export Events

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer export-events --out logs/events.jsonl
```

**Local:**
```bash
poetry run cold-emailer export-events --out logs/events.jsonl
```

## 📝 Data Format

### Prospects File (Excel or CSV)

**Required columns:**
- `email` - Recipient email address
- `full_name` - Recipient full name
- `company` - Company name
- `resume_id` - Resume identifier (must exist in manifest)

**Optional columns:**
- `prospect_id` - Unique ID (auto-generated if missing)
- `role_title` - Job title/role
- `timezone` - Timezone
- `sequence_id` - Follow-up sequence to use (default: "default")
- `variables_json` - JSON string for custom template variables

**Example (Excel/CSV):**
| email | full_name | company | resume_id | role_title | sequence_id |
|-------|-----------|---------|-----------|------------|-------------|
| john@acme.com | John Doe | Acme Corp | RES-00042 | Software Engineer | default |
| jane@tech.com | Jane Smith | TechStart | RES-00042 | Product Manager | aggressive |

**File:** `data/prospects.xlsx` (or `prospects.csv`)

### Resume Manifest File (Excel or CSV)

**Required columns:**
- `resume_id` - Unique identifier
- `relative_path` - Path relative to repo root
- `sha256` - SHA256 checksum (computed automatically if blank)
- `version` - Optional version string

**Example (Excel/CSV):**
| resume_id | relative_path | sha256 | version |
|-----------|---------------|--------|---------|
| RES-00042 | assets/resumes/RES-00042.pdf | (auto-computed) | 1.0 |
| RES-00043 | assets/resumes/RES-00043.pdf | (auto-computed) | 1.0 |

**File:** `data/resume_manifest.xlsx` (or `resume_manifest.csv`)

## 🛡️ Safety Features

### Fail-Closed Validation

- **Resume Checksum**: Resume files are validated before sending. Mismatches prevent sending.
- **File Existence**: Missing resume files prevent sending.
- **Email Validation**: Invalid email addresses are rejected during ingestion.

### Dry Run Mode

Test without sending emails:
```bash
poetry run cold-emailer run --file data/prospects.csv --dry-run
```

### Confirmation Flag

Require explicit confirmation for live sends:
```bash
poetry run cold-emailer run --file data/prospects.csv --confirm-send
```

### State Tracking

- Never double-send due to idempotent state management
- Tracks all email events with full audit trail
- Automatic reply detection stops follow-ups

### Throttling

- Daily maximum email limit
- Per-minute rate limiting
- Send window (time-based restrictions)

## 🔄 Automated Daily Runs

### Docker Cron Setup

For Docker deployments, use a cron job to run campaigns:

```bash
# Add to your crontab
0 9 * * * cd /path/to/cold-emailer && docker compose exec -T cold-emailer cold-emailer run --file data/prospects.xlsx --confirm-send >> logs/cron.log 2>&1
```

### Local Cron Setup

For local deployments:

```bash
# Run at 9 AM daily
0 9 * * * cd /path/to/cold-emailer && poetry run cold-emailer run --file data/prospects.xlsx --confirm-send >> logs/cron.log 2>&1
```

### Manual Run

**Docker:**
```bash
docker compose exec cold-emailer cold-emailer run --file data/prospects.xlsx --confirm-send
```

**Local:**
```bash
poetry run cold-emailer run --file data/prospects.csv --confirm-send
```

## 🧪 Development

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

# Run tests with coverage
poetry run pytest --cov=cold_emailer --cov-report=html
```

### Project Status

This project is implemented in phases:

- ✅ **Phase 1**: Project scaffolding
- ✅ **Phase 2**: SQLite + models + repository layer
- ✅ **Phase 3**: Ingestion + resume manifest + checksum validator
- ✅ **Phase 4**: Templating + email composer
- ✅ **Phase 5**: SMTP sender + dry-run support
- ✅ **Phase 6**: IMAP reply detector
- ✅ **Phase 7**: Orchestrator end-to-end
- ✅ **Phase 8**: Polish for GitHub + LinkedIn

## 🐳 Docker Details

### Image Information

- **Registry**: GitHub Container Registry (GHCR)
- **Image**: `ghcr.io/neha272/cold-email:latest`
- **Architecture**: Multi-arch (linux/amd64, linux/arm64)
- **Base Image**: `python:3.11-slim`
- **Size**: ~200MB (optimized with multi-stage build)

### Building Locally

```bash
# Build the image
docker build -t cold-emailer:local .

# Run the container
docker run -d \
  --name cold-emailer \
  -p 5000:5000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/config:/app/config:ro \
  -v $(pwd)/templates:/app/templates:ro \
  cold-emailer:local
```

### Docker Troubleshooting

**Container won't start:**
```bash
# Check logs
docker compose logs cold-emailer

# Check if port is already in use
lsof -i :5000
```

**Permission issues:**
```bash
# Ensure data directories are writable
chmod -R 755 data logs
```

**Database initialization:**
```bash
# Initialize database inside container
docker compose exec cold-emailer cold-emailer init-db
```

**Update to latest image:**
```bash
# Pull latest image
docker compose pull

# Restart with new image
docker compose up -d
```

### Environment Variables

All configuration is done via environment variables. See `.env.example` for all available options.

**Required for email sending:**
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`
- `IMAP_HOST`, `IMAP_USER`, `IMAP_PASSWORD`

**Optional:**
- `PORT` - Web interface port (default: 5000)
- `FLASK_SECRET_KEY` - Secret key for Flask sessions
- `DAILY_MAX_EMAILS` - Daily email limit (default: 50)
- `PER_MINUTE_LIMIT` - Rate limit (default: 5)

## 🔒 Security Notes

⚠️ **IMPORTANT SECURITY CONSIDERATIONS**:

1. **Never commit secrets**: The `.env` file is in `.gitignore`. Never commit it or any files containing credentials.

2. **Use app-specific passwords**: For Gmail and other providers, use app-specific passwords, not your main account password.

3. **Review email content**: Always review email templates and test with dry-run before sending to real prospects.

4. **Start with dry-run**: Always test with `--dry-run` flag first to verify behavior.

5. **Attachment validation**: The tool validates attachments before sending to prevent wrong-file mistakes. This is fail-closed: if validation fails, no email is sent.

6. **Rate limiting**: Respect email provider limits and use throttling settings appropriately.

7. **Compliance**: Ensure compliance with CAN-SPAM Act, GDPR, and other applicable regulations in your jurisdiction.

8. **Data privacy**: The SQLite database contains personal information. Secure it appropriately and follow data protection regulations.

## 📄 License

[Add your license here - MIT, Apache 2.0, etc.]

## 🤝 Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Ensure all tests pass and code is formatted
5. Submit a pull request

## 📧 Support

For issues, questions, or contributions, please open an issue on GitHub.

## 🙏 Acknowledgments

- Built with [Poetry](https://python-poetry.org/) for dependency management
- Uses [SQLAlchemy](https://www.sqlalchemy.org/) for database operations
- Email composition powered by [Jinja2](https://jinja.palletsprojects.com/)
- CLI built with [Typer](https://typer.tiangolo.com/)

---

**Made with ❤️ for efficient and safe cold email automation**
