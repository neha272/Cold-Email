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
cold_emailer/
├── config/
│   ├── settings.yaml        # Main configuration
│   └── sequences.yaml       # Email sequences
├── data/
│   ├── prospects.xlsx       # Input file
│   ├── resumes/             # PDF resumes
│   └── state.db             # SQLite database
├── templates/
│   ├── initial.md           # Email templates
│   ├── followup_1.md
│   └── followup_2.md
├── src/cold_emailer/
│   ├── cli.py               # CLI interface
│   ├── orchestrator.py      # Main logic
│   ├── composer.py          # Email composition
│   ├── mailer/
│   │   ├── smtp_sender.py
│   │   └── imap_reply_detector.py
│   ├── state_store/         # Database layer
│   └── web/                 # Flask web app
└── tests/
```

## 🚢 Deployment

### Production Deployment

**Using prebuilt image:**
```bash
docker pull ghcr.io/neha272/cold-email:latest

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

**With reverse proxy (Nginx):**
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Monitoring

```bash
# View logs
docker compose logs -f cold-emailer

# Check status
docker compose ps

# Container stats
docker stats cold-emailer
```

### Backup

```bash
# Backup database
docker compose exec -T cold-emailer sqlite3 /app/data/state.db ".backup '/app/data/backup.db'"

# Backup data directory
tar -czf backup_$(date +%Y%m%d).tar.gz data/
```

## 🧪 Development

```bash
# Format code
poetry run black src tests

# Lint
poetry run ruff check src tests

# Type check
poetry run mypy src

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=cold_emailer --cov-report=html
```

## 🔒 Security Best Practices

- ✅ Use app-specific passwords (never main account password)
- ✅ Never commit `.env` file (already in `.gitignore`)
- ✅ Always test with `--dry-run` first
- ✅ Review email templates before sending
- ✅ Set appropriate throttling limits
- ✅ Keep dependencies updated
- ✅ Secure database file permissions
- ✅ Comply with CAN-SPAM Act and GDPR

## ⚠️ Important Notes

1. **Email Provider Limits:**
   - Gmail: 500 emails/day (regular), 2000/day (Workspace)
   - Most providers: ~10 emails/minute
   
2. **Compliance:** Ensure compliance with email regulations (CAN-SPAM, GDPR, etc.)

3. **Testing:** Always use `--dry-run` before live campaigns

4. **Resume Files:** The `resume_id` in prospects file must match the PDF filename (without `.pdf`)

## 📄 License

MIT License

## 🤝 Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new features
4. Submit a pull request

## 📧 Support

For issues or questions, open an issue on GitHub.

---

**Made with ❤️ for efficient and safe cold email automation**
