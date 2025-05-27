#!/bin/bash

# Cron job setup script for review processing
# This script sets up the cron job for automated review analysis

# Set environment variables
DJANGO_PROJECT_PATH=${DJANGO_PROJECT_PATH:-"C:\Users\Minjire Victor\Desktop\udemy\recipie-app-api\recepie-app-api/app"}
PYTHON_PATH=${PYTHON_PATH:-"python"}
ENVIRONMENT=${ENVIRONMENT:-"development"}

# Determine cron frequency based on environment
if [ "$ENVIRONMENT" = "production" ]; then
    CRON_SCHEDULE="0 2 * * *"  # Daily at 2 AM
    echo "Setting up PRODUCTION cron job (daily at 2 AM)"
else
    CRON_SCHEDULE="*/5 * * * *"  # Every 5 minutes for development
    echo "Setting up DEVELOPMENT cron job (every 5 minutes)"
fi

# Create log directory
LOG_DIR="$DJANGO_PROJECT_PATH/logs"
mkdir -p "$LOG_DIR"

# Create the cron job command
CRON_COMMAND="cd $DJANGO_PROJECT_PATH && $PYTHON_PATH manage.py process_reviews >> $LOG_DIR/review_processing.log 2>&1"

# Create temporary cron file
TEMP_CRON_FILE="/tmp/review_cron_$$.txt"

# Get existing cron jobs (excluding our review processing job)
crontab -l 2>/dev/null | grep -v "manage.py process_reviews" > "$TEMP_CRON_FILE"

# Add our cron job
echo "$CRON_SCHEDULE $CRON_COMMAND" >> "$TEMP_CRON_FILE"

# Install the new cron job
crontab "$TEMP_CRON_FILE"

# Clean up
rm "$TEMP_CRON_FILE"

# Verify installation
echo "Cron job installed successfully!"
echo "Current crontab:"
crontab -l | grep "manage.py process_reviews"

echo ""
echo "Log files will be written to: $LOG_DIR/review_processing.log"
echo "To view logs: tail -f $LOG_DIR/review_processing.log"
echo ""
echo "To remove the cron job later, run:"
echo "crontab -l | grep -v 'manage.py process_reviews' | crontab -"