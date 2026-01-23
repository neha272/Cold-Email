#!/bin/bash
# Install cron job for cold-email campaign

PROJECT_DIR="/Users/lalakiya/Library/CloudStorage/OneDrive-WashingtonUniversityinSt.Louis/Neha/Cold-Email"
SCRIPT_PATH="$PROJECT_DIR/scripts/run_campaign.sh"

echo "================================"
echo "Cold Email Campaign - Cron Setup"
echo "================================"
echo ""
echo "This will set up automatic campaign runs at 9:00 AM daily"
echo ""

# Create temporary crontab file
TEMP_CRON=$(mktemp)

# Get existing crontab
crontab -l > "$TEMP_CRON" 2>/dev/null

# Check if job already exists
if grep -q "run_campaign.sh" "$TEMP_CRON"; then
    echo "✓ Cron job already installed!"
    echo ""
    echo "Current cron schedule:"
    grep "run_campaign.sh" "$TEMP_CRON"
else
    # Add the new cron job
    echo "0 9 * * * $SCRIPT_PATH" >> "$TEMP_CRON"
    
    # Install the updated crontab
    crontab "$TEMP_CRON"
    
    echo "✓ Cron job installed successfully!"
    echo ""
    echo "Schedule: Every day at 9:00 AM"
    echo "Command: $SCRIPT_PATH"
    echo ""
    echo "Logs will be saved to: $PROJECT_DIR/logs/"
    echo ""
    echo "To view installed cron jobs:"
    echo "  crontab -l"
    echo ""
    echo "To remove the cron job:"
    echo "  crontab -e"
    echo "  (then delete the run_campaign.sh line)"
fi

# Clean up
rm -f "$TEMP_CRON"
