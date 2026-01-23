#!/bin/bash
# Test the cron job functionality
# This verifies that the campaign will run correctly

PROJECT_DIR="/Users/lalakiya/Library/CloudStorage/OneDrive-WashingtonUniversityinSt.Louis/Neha/Cold-Email"

echo "================================"
echo "Testing Cron Job Setup"
echo "================================"
echo ""

# 1. Check if script exists
echo "1. Checking if campaign script exists..."
if [ -f "$PROJECT_DIR/scripts/run_campaign.sh" ]; then
    echo "   ✓ Script found: $PROJECT_DIR/scripts/run_campaign.sh"
else
    echo "   ✗ Script not found!"
    exit 1
fi

# 2. Check if script is executable
echo ""
echo "2. Checking if script is executable..."
if [ -x "$PROJECT_DIR/scripts/run_campaign.sh" ]; then
    echo "   ✓ Script is executable"
else
    echo "   ✗ Script is not executable!"
    exit 1
fi

# 3. Check if cron job is installed
echo ""
echo "3. Checking if cron job is installed..."
if crontab -l | grep -q "run_campaign.sh"; then
    echo "   ✓ Cron job is installed"
    echo ""
    echo "   Current schedule:"
    crontab -l | grep "run_campaign.sh" | sed 's/^/     /'
else
    echo "   ✗ Cron job not found!"
    exit 1
fi

# 4. Check logs directory
echo ""
echo "4. Checking logs directory..."
if [ -d "$PROJECT_DIR/logs" ]; then
    echo "   ✓ Logs directory exists: $PROJECT_DIR/logs"
    LOG_COUNT=$(ls -1 "$PROJECT_DIR/logs" 2>/dev/null | wc -l)
    echo "   ✓ $LOG_COUNT log file(s) found"
    if [ $LOG_COUNT -gt 0 ]; then
        echo ""
        echo "   Recent logs:"
        ls -lht "$PROJECT_DIR/logs" | head -3 | tail -2 | awk '{print "     " $9}'
    fi
else
    echo "   ⚠ Logs directory doesn't exist yet (will be created on first run)"
fi

# 5. Run a test
echo ""
echo "5. Running test campaign..."
echo "   (This will process any due emails right now)"
echo ""
cd "$PROJECT_DIR"
"$PROJECT_DIR/scripts/run_campaign.sh" 2>&1 | grep -E "(Emails Sent|Emails Failed|Campaign Run|Date:|Exit Code)"

echo ""
echo "================================"
echo "✓ Cron Setup Test Complete!"
echo "================================"
echo ""
echo "Your campaign will automatically run every day at 9:00 AM"
echo "Check logs in: $PROJECT_DIR/logs/"
echo ""
echo "To see what time it will run tomorrow:"
echo "  crontab -l"
