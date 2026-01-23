#!/bin/bash
# Script to run the cold-email campaign
# This script is meant to be run by cron for automated email sending

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Change to project directory
cd "$PROJECT_DIR" || exit 1

# Create logs directory if it doesn't exist
mkdir -p logs

# Log file with timestamp
LOG_FILE="logs/campaign_run_$(date +%Y%m%d_%H%M%S).log"

# Run the campaign
{
    echo "=== Campaign Run Started ==="
    echo "Date: $(date)"
    echo "Working Directory: $PROJECT_DIR"
    echo ""
    
    # Run the campaign directly with poetry
    echo "Running email campaign..."
    cd "$PROJECT_DIR"
    poetry run python -c "
import sys
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path.cwd()))

from cold_emailer.config import load_config, EnvSettings, load_sequences
from cold_emailer.orchestrator import Orchestrator

settings = load_config()
env_settings = EnvSettings()
sequences = load_sequences(Path('config/sequences.yaml'))

orchestrator = Orchestrator(
    settings=settings,
    env_settings=env_settings,
    sequences=sequences,
    dry_run=False,
)

summary = orchestrator.run_daily()

print(f'Campaign Summary:')
print(f'  Emails Sent: {summary.get(\"emails_sent\")}')
print(f'  Emails Failed: {summary.get(\"emails_failed\")}')
print(f'  Replies Detected: {summary.get(\"replies_detected\")}')
" 2>&1
    
    RESULT=$?
    echo ""
    echo "=== Campaign Run Completed ==="
    echo "Date: $(date)"
    echo "Exit Code: $RESULT"
} | tee -a "$LOG_FILE"

exit 0
