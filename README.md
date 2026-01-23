# Cold Emailer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

A production-ready cold email automation tool with state tracking, dynamic PDF attachments, follow-up sequencing, and automatic reply detection.

## ✨ Features

- **State Tracking**: SQLite database with full audit trail
- **Dynamic Attachments**: Unique PDF resume per prospect with SHA256 validation
- **Follow-up Sequencing**: Configurable multi-step sequences with automatic stop on reply
- **Reply Detection**: IMAP-based with Message-ID threading
- **Safety First**: Fail-closed validation, dry-run mode, throttling
- **Email Verification**: Syntax validation, DNS MX lookup, optional SMTP probing (free, no paid APIs)
- **Web Interface**: Complete UI for managing campaigns
- **Production Ready**: Fully typed, tested, and Docker-ready

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone and configure
git clone https://github.com/neha272/Cold-Email.git
cd Cold-Email
cp .env.example .env
# Edit .env with your email credentials

# Start application
docker compose up -d --build

# Access web interface at http://localhost:5000
```

### Local Installation

```bash
# Install dependencies
poetry install

# Configure and start
cp .env.example .env
poetry run cold-emailer web
```

## ⚙️ Configuration

### 1. Email Provider Setup

Update `.env` with your email credentials:

**Gmail:**
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password  # Generate at myaccount.google.com/security
SMTP_FROM_NAME=Your Name

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=your-email@gmail.com
IMAP_PASSWORD=your-app-password
```

**Other Providers:**

| Provider | SMTP Host | SMTP Port | IMAP Host | IMAP Port |
|----------|-----------|-----------|-----------|-----------|
| Outlook | smtp-mail.outlook.com | 587 | outlook.office365.com | 993 |
| Yahoo | smtp.mail.yahoo.com | 587 | imap.mail.yahoo.com | 993 |
| iCloud | smtp.mail.me.com | 587 | imap.mail.me.com | 993 |

### 2. Email Templates

Edit templates in `templates/` directory:

- `initial.md` - First contact
- `followup_1.md` - First follow-up
- `followup_2.md` - Second follow-up

**Available variables:** `{{ full_name }}`, `{{ company }}`, `{{ role_title }}`, `{{ sender.from_name }}`

### 3. Sequences Configuration

Edit `config/sequences.yaml`:

```yaml
sequences:
  default:
    name: "Default Sequence"
    steps:
      - step: 0
        template: "Initial"
        wait_days: 0
        subject: "Quick question about {{ company }}"
      - step: 1
        template: "Followup 1"
        wait_days: 3
        subject: "Following up - {{ company }}"
```

### 4. Throttling & Safety

Edit `config/settings.yaml`:

```yaml
throttling:
  daily_max_emails: 50          # Adjust based on your email provider
  per_minute_limit: 5           # Gmail allows ~10/min
  send_window_start: "09:00"
  send_window_end: "17:00"
  timezone: "America/Chicago"

safety:
  safe_mode: true
  require_confirm_send: false
```

### 5. Prepare Data

**Add resumes:**
```bash
mkdir -p data/resumes
cp your-resume.pdf data/resumes/my-resume.pdf
```

**Create prospects file** (`data/prospects.xlsx` or `.csv`):

| email | full_name | company | resume_id | role_title | sequence_id |
|-------|-----------|---------|-----------|------------|-------------|
| john@acme.com | John Doe | Acme Corp | my-resume | Software Engineer | default |

**Required columns:** `email`, `full_name`, `company`, `resume_id`

**Optional columns:** `role_title`, `sequence_id`, `timezone`, `variables_json`

## 📊 Usage

### Web Interface

Access at `http://localhost:5000` for:
- Dashboard with statistics
- Prospect management
- Campaign execution
- Sequence configuration

### CLI Commands

**Docker:**
```bash
# Dry run (test without sending)
docker compose exec cold-emailer cold-emailer run --file data/prospects.xlsx --dry-run

# Live run
docker compose exec cold-emailer cold-emailer run --file data/prospects.xlsx --confirm-send

# Check status
docker compose exec cold-emailer cold-emailer status

# Import prospects
docker compose exec cold-emailer cold-emailer ingest --file data/prospects.xlsx
```

**Local:**
```bash
# Replace "docker compose exec cold-emailer" with "poetry run"
poetry run cold-emailer run --file data/prospects.xlsx --dry-run
poetry run cold-emailer run --file data/prospects.xlsx --confirm-send
poetry run cold-emailer status
```

## 🛡️ Safety Features

- **Fail-Closed Validation**: Missing or mismatched resumes prevent sending
- **Dry Run Mode**: Test without sending emails
- **Idempotent**: Never double-sends
- **Reply Detection**: Automatically stops follow-ups when reply detected
- **Throttling**: Daily max and per-minute limits
- **Send Window**: Time-based restrictions

## 🔄 Automated Runs

**Docker cron:**
```bash
# Add to crontab (run daily at 9 AM)
0 9 * * * cd /path/to/cold-emailer && docker compose exec -T cold-emailer cold-emailer run --file data/prospects.xlsx --confirm-send >> logs/cron.log 2>&1
```

**Local cron:**
```bash
0 9 * * * cd /path/to/cold-emailer && poetry run cold-emailer run --file data/prospects.xlsx --confirm-send >> logs/cron.log 2>&1
```

## 📁 Project Structure

```
├── config/           # Configuration files (settings.yaml, sequences.yaml)
├── data/             # Data directory (prospects.xlsx, resumes/, state.db)
├── templates/        # Email templates (Initial.md, Followup 1.md, Followup 2.md)
├── src/cold_emailer/ # Source code (CLI, web app, orchestrator, mailer)
└── tests/            # Test suite
```

## 🚢 Deployment

**Using Docker (recommended):**
```bash
# Pull prebuilt image
docker pull ghcr.io/neha272/cold-email:latest

# Run with environment file
docker run -d --name cold-emailer -p 5000:5000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config:ro \
  --env-file .env \
  ghcr.io/neha272/cold-email:latest
```

**Monitoring & Backup:**
```bash
# View logs
docker compose logs -f

# Backup database
tar -czf backup_$(date +%Y%m%d).tar.gz data/
```

## 📧 Email Verification

Cold Emailer includes a **free, built-in email verification system** with three tiers:

### Tier 1: Syntax Validation
Validates email format using industry-standard `email-validator` library.
- Catches obvious mistakes (missing @, invalid TLDs, etc.)
- Returns `syntax_invalid` if email fails basic format rules.
- **Always active** — no configuration needed.

### Tier 2: DNS Validation (Default, Always Active)
Checks if the domain has valid MX or A/AAAA records:
- **MX Found**: `mx_found` → confidence 0.5 (likely valid, but not verified)
- **No MX, but A/AAAA**: `risky` → confidence 0.35 (email might exist, but domain lacks proper mail setup)
- **Domain invalid**: `invalid` → confidence 0.9 (domain does not resolve)

### Tier 3: SMTP Probing (Optional, Disabled by Default)
Advanced SMTP handshake verification that **does not send any email**:
- Connects to MX server on port 25 with 8-second timeout
- Sends: `EHLO`, `MAIL FROM:<verifier@ourdomain.invalid>`, `RCPT TO:<target>`
- **Interprets responses:**
  - `250/251` → `likely_valid` → final status `valid` (confidence 0.9)
  - `550/551/553` → `invalid_mailbox` (confidence 0.95)
  - `450/451/452, 421, timeout` → `unknown` (confidence 0.3)
- **Catch-all detection**: Probes a random address; if also accepted → `accept_all` (confidence 0.6)
- **Rate limiting**: Per-domain throttling prevents server hammering
- **Caching**: Results cached for TTL (default 60 minutes)

### Result Statuses

| Status | Confidence | Action | Notes |
|--------|-----------|--------|-------|
| `valid` | 0.9 | ✓ Send | SMTP probe accepted |
| `invalid` | 0.9-0.95 | ✗ Block | Domain invalid or mailbox rejected |
| `syntax_invalid` | 1.0 | ✗ Block | Email format invalid |
| `accept_all` | 0.6 | ⚠️ Warn | Domain accepts all addresses; may bounce |
| `unknown` | 0.3 | ⚠️ Warn | Temporary error or SMTP probe disabled |
| `risky` | 0.35 | ⚠️ Warn | Domain has no MX record; falls back to A/AAAA |
| `smtp_probe_disabled` | 0.5 | ⚠️ Warn | MX found but SMTP probing is off |

### Enabling SMTP Probing

**Option 1: Environment variable** (recommended)
```bash
export ENABLE_SMTP_PROBE=true
```

**Option 2: Edit `config/settings.yaml`**
```yaml
email_verification:
  smtp_probe_enabled: true
  probe_cache_minutes: 60
  probe_rate_limit_seconds: 60
  smtp_timeout_seconds: 8
```

### Ethical Use Notes

⚠️ **Important:** SMTP probing is powerful but must be used responsibly:

1. **No Spam**: We use a benign `MAIL FROM:<verifier@ourdomain.invalid>` and do NOT send actual emails.
2. **Respect Rate Limits**: Per-domain throttling prevents server hammering (default: 60 sec between probes per domain).
3. **Transparent**: Users see warnings for risky addresses; results are not hidden.
4. **Compliance**: Use results only for improving email list quality, not harvesting valid addresses.
5. **Opt-in**: SMTP probing is disabled by default; users must explicitly enable it.
6. **Timeout Handling**: 8-second socket timeouts prevent long-running probes.

### How Verification Integrates

**In the web UI (add/edit prospect):**
- Tier 1+2 runs automatically on prospect submission
- Blocks submission on `syntax_invalid` or `invalid`
- Shows warning for `risky`, `unknown`, `accept_all`, `smtp_probe_disabled`

**Before sending emails (CLI/orchestrator):**
- Runs verification again (Tier 1+2, SMTP optional if enabled)
- Blocks sending on `syntax_invalid` or `invalid`
- Logs warnings for risky statuses
- Never sends to blocked addresses

## 🧪 Development

```bash
# Run all checks and tests
make all

# Individual commands
make format    # Format code
make lint      # Run linters
make test      # Run tests

# Run email verification tests specifically
poetry run pytest tests/test_email_verification.py -v
```

## 🔒 Security & Best Practices

- Use app-specific passwords (never main account password)
- Always test with `--dry-run` before live campaigns
- Set appropriate throttling limits for your email provider
- Comply with email regulations (CAN-SPAM, GDPR)
- Resume filename must match `resume_id` in prospects file (without `.pdf`)

**Email Provider Limits:** Gmail: 500/day (regular), 2000/day (Workspace) | Most: ~10/minute

## 📄 License

MIT License - See [LICENSE](LICENSE) for details

---

**Made with ❤️ for efficient and safe cold email automation**
